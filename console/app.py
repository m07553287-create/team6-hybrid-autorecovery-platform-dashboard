"""figteam 통합 콘솔 (s1): 허용된 대상에 실제 터미널(PTY) 을 WebSocket 으로 잇는다.

잠금: 콘솔 비밀번호(위키 자동 입장과 별개) · 감사: 세션별 입출력 전체 기록.
"""
import asyncio
import json
import logging
import os
import pathlib
import time

from fastapi import FastAPI, Request, Response, WebSocket
from fastapi.responses import JSONResponse

from console.auth import Lock, TTL
from console.pty_session import PtySession
from console.status import Collector
from console.presets import PresetError, PresetStore
from console.session_hub import SessionHub, clean_owner
from console import store as store_mod

COOKIE = "fc_s"
MAX_SESSIONS = 6
IDLE_SECONDS = 1800
log = logging.getLogger("figteam-console")


def _load_targets(path):
    items = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    return {t["id"]: t for t in items}, [t["id"] for t in items]


def create_app():
    app = FastAPI(title="figteam-console", docs_url=None, redoc_url=None, openapi_url=None)
    targets, order = _load_targets(os.environ.get("CONSOLE_TARGETS",
                                                  str(pathlib.Path(__file__).with_name("targets.json"))))
    lock = Lock(os.environ.get("CONSOLE_PASS_HASH"), os.environ.get("CONSOLE_PASS_SALT"),
                os.environ.get("CONSOLE_SESSIONS", "/var/lib/figteam-console/sessions.json"))
    origin = os.environ.get("ALLOWED_ORIGIN", "https://figteam.ktci5.kr")
    log_dir = pathlib.Path(os.environ.get("CONSOLE_LOG_DIR", "/var/log/figteam-console"))
    hub = SessionHub(store=store_mod.from_env())
    app.state.hub = hub
    collector = Collector(targets, order, int(os.environ.get("CONSOLE_STATUS_INTERVAL", "20")))
    app.state.collector = collector

    async def _reaper():
        """살아 있는 세션 정리: 끝난 셸·30분 활동 없는 세션(분리 포함)을 닫는다."""
        while True:
            await asyncio.sleep(10)
            now = time.time()
            for s in list(hub.live.values()):
                if s.pty is None:
                    continue
                if s.pty.closed.is_set():
                    hub.drop(s)
                    continue
                if now - s.last_at > IDLE_SECONDS:
                    if s.ws is not None:
                        try:
                            await s.ws.send_text("\r\n[30분 동안 활동이 없어 세션을 닫습니다]\r\n")
                        except Exception:
                            pass
                    s.pty.close()
                    hub.drop(s)

    @app.on_event("startup")
    async def _start_bg():
        loop = asyncio.get_running_loop()
        if collector.interval > 0:
            loop.create_task(collector.loop())
        loop.create_task(_reaper())

    @app.get("/console/api/status")
    def status():
        """읽기 전용 실측 상태(잠금 불필요). 명령·argv 는 내보내지 않는다."""
        return collector.snapshot

    def ip_of(conn):
        return conn.headers.get("cf-connecting-ip") or (conn.client.host if conn.client else "-")

    @app.middleware("http")
    async def _origin(request: Request, call_next):
        if request.method in ("POST", "PUT", "DELETE") and request.headers.get("origin") != origin:
            return JSONResponse({"error": "허용되지 않은 출처입니다"}, status_code=403)
        return await call_next(request)

    @app.post("/console/api/unlock")
    async def unlock(request: Request, response: Response):
        ip = ip_of(request)
        if lock.limited(ip):
            return JSONResponse({"error": "시도가 많습니다. 10분 뒤 다시 시도하세요"}, status_code=429)
        try:
            data = await request.json()
        except ValueError:
            data = {}
        token = lock.unlock(str(data.get("password") or ""), ip)
        if not token:
            log.warning("unlock failed ip=%s", ip)
            return JSONResponse({"error": "콘솔 비밀번호가 맞지 않습니다"}, status_code=401)
        log.info("unlock ok ip=%s", ip)
        response.set_cookie(COOKIE, token, max_age=TTL, httponly=True, secure=True, samesite="strict", path="/console")
        return {"ok": True, "ttl": TTL}

    presets = PresetStore(os.environ.get("CONSOLE_PRESETS", "/var/lib/figteam-console/presets.json"), targets)

    def unlocked(request):
        return lock.check(request.cookies.get(COOKIE), ip_of(request))

    @app.get("/console/api/presets")
    def get_presets(request: Request):
        if not unlocked(request):
            return JSONResponse({"error": "로그인이 필요합니다"}, status_code=401)
        return presets.all()

    @app.put("/console/api/presets/{target_id}")
    async def put_presets(target_id: str, request: Request):
        if not unlocked(request):
            return JSONResponse({"error": "로그인이 필요합니다"}, status_code=401)
        if target_id not in targets or targets[target_id].get("disabled"):
            return JSONResponse({"error": "없는 대상입니다"}, status_code=404)
        try:
            data = await request.json()
            items = presets.put(target_id, data.get("items"))
        except (ValueError, AttributeError) as e:
            return JSONResponse({"error": str(e) if isinstance(e, PresetError) else "형식이 올바르지 않습니다"}, status_code=422)
        log.info("presets saved target=%s ip=%s count=%d", target_id, ip_of(request), len(items))
        return {"ok": True, "items": items}

    @app.delete("/console/api/presets/{target_id}")
    def reset_presets(target_id: str, request: Request):
        if not unlocked(request):
            return JSONResponse({"error": "로그인이 필요합니다"}, status_code=401)
        if target_id not in targets:
            return JSONResponse({"error": "없는 대상입니다"}, status_code=404)
        presets.reset(target_id)
        log.info("presets reset target=%s ip=%s", target_id, ip_of(request))
        return {"ok": True}

    @app.get("/console/api/me")
    def me(request: Request):
        """사이트 입장 로그인 상태 (서버 확인). 대시보드 첫 화면이 이걸로 로그인 여부를 판단한다."""
        if lock.check(request.cookies.get(COOKIE), ip_of(request)):
            return {"unlocked": True, "ttl": TTL}
        return {"unlocked": False}

    @app.post("/console/api/lock")
    def lock_(request: Request, response: Response):
        lock.lock(request.cookies.get(COOKIE))
        response.delete_cookie(COOKIE, path="/console")
        return {"ok": True}

    @app.get("/console/api/targets")
    def list_targets(request: Request):
        if not lock.check(request.cookies.get(COOKIE), ip_of(request)):
            return JSONResponse({"error": "콘솔 잠금을 먼저 푸세요"}, status_code=401)
        keys = ("id", "area", "name", "desc", "host", "disabled", "check", "fix", "parent", "kubectl", "role")
        return [{k: targets[i].get(k) for k in keys if k in targets[i]} for i in order]

    @app.get("/console/api/sessions")
    def my_sessions(request: Request):
        """이 이름으로 아직 살아 있는 터미널 세션 목록 — 새로고침 후 자동 재접속에 쓴다."""
        if not unlocked(request):
            return JSONResponse({"error": "로그인이 필요합니다"}, status_code=401)
        owner = clean_owner(request.query_params.get("u"))
        return [s.meta() for s in hub.list(owner) if s.pty and not s.pty.closed.is_set()]

    @app.websocket("/console/ws/{target_id}")
    async def ws_term(ws: WebSocket, target_id: str):
        await ws.accept()
        ip = ip_of(ws)
        if ws.headers.get("origin") != origin:
            return await ws.close(4403)
        if not lock.check(ws.cookies.get(COOKIE), ip):
            return await ws.close(4401)
        t = targets.get(target_id)
        if not t:
            return await ws.close(4404)
        if t.get("disabled"):
            return await ws.close(4409)
        owner = clean_owner(ws.query_params.get("u"))
        sess = hub.get(owner, target_id)
        reattach = bool(sess and sess.pty and not sess.pty.closed.is_set())
        if not reattach and len(hub.live) >= MAX_SESSIONS:
            return await ws.close(4429)

        if reattach:
            sess.ws = ws                       # 출력은 항상 현재 붙은 ws 로 나간다(세션 객체가 추적)
            await ws.send_text("\x1b[2J\x1b[3J\x1b[H")   # 화면 지우고 스크롤백 재생 → 복원
            if sess.buf:
                await ws.send_text(sess.buf)
            await ws.send_text(f"\r\n\x1b[2m[{owner} 세션에 다시 연결했습니다]\x1b[0m\r\n")
            log.info("reattach target=%s owner=%s ip=%s", target_id, owner, ip)
        else:
            day = log_dir / time.strftime("%Y-%m-%d")
            day.mkdir(parents=True, exist_ok=True)
            safe = clean_owner(owner).replace(" ", "_")
            lf = open(day / f"{time.strftime('%H%M%S')}-{target_id}-{safe}.log", "ab", buffering=0)
            lf.write(f"# figteam-console {time.strftime('%F %T')} target={target_id} owner={owner} ip={ip} argv={t['argv']}\n".encode())
            try:
                cols = int(ws.query_params.get("cols", 100))
                rows = int(ws.query_params.get("rows", 30))
            except ValueError:
                cols, rows = 100, 30
            sess = hub.create(owner, target_id, pty=None, log=lf)
            sess.ws = ws

            async def out(text):
                sess.append_out(text)
                w = sess.ws
                if w is not None:
                    try:
                        await w.send_text(text)
                    except Exception:
                        pass

            sess.pty = PtySession(t["argv"], cols, rows, out, lf)
            sess.pty.start()
            log.info("open target=%s owner=%s ip=%s", target_id, owner, ip)

        async def pump_in():
            while True:
                msg = await ws.receive_text()
                try:
                    m = json.loads(msg)
                except ValueError:
                    continue
                if m.get("t") == "i" and isinstance(m.get("d"), str):
                    d = m["d"][:8192]
                    sess.feed_in(d)
                    sess.pty.write(d)
                    hub.save(sess)
                elif m.get("t") == "r":
                    try:
                        sess.pty.resize(m.get("c", 100), m.get("r", 30))
                    except (TypeError, ValueError):
                        pass

        tasks = [asyncio.ensure_future(pump_in()), asyncio.ensure_future(sess.pty.closed.wait())]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for x in tasks:
                x.cancel()
            if sess.pty.closed.is_set():        # 셸이 끝남 → 세션 제거
                try:
                    await ws.send_text("\r\n[세션이 종료되었습니다]\r\n")
                except Exception:
                    pass
                hub.drop(sess)
                log.info("close target=%s owner=%s", target_id, owner)
            else:                                # ws 만 끊김 → 셸은 유지(분리), 새로고침 때 재접속
                if sess.ws is ws:
                    sess.ws = None
                hub.save(sess)
                log.info("detach target=%s owner=%s", target_id, owner)
            try:
                await ws.close(1000)
            except Exception:
                pass

    return app
