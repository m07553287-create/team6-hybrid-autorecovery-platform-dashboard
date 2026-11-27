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
    lock = Lock(os.environ.get("CONSOLE_PASS_HASH"), os.environ.get("CONSOLE_PASS_SALT"))
    origin = os.environ.get("ALLOWED_ORIGIN", "https://figteam.ktci5.kr")
    log_dir = pathlib.Path(os.environ.get("CONSOLE_LOG_DIR", "/var/log/figteam-console"))
    live = set()

    def ip_of(conn):
        return conn.headers.get("cf-connecting-ip") or (conn.client.host if conn.client else "-")

    @app.middleware("http")
    async def _origin(request: Request, call_next):
        if request.method == "POST" and request.headers.get("origin") != origin:
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

    @app.post("/console/api/lock")
    def lock_(request: Request, response: Response):
        lock.lock(request.cookies.get(COOKIE))
        response.delete_cookie(COOKIE, path="/console")
        return {"ok": True}

    @app.get("/console/api/targets")
    def list_targets(request: Request):
        if not lock.check(request.cookies.get(COOKIE), ip_of(request)):
            return JSONResponse({"error": "콘솔 잠금을 먼저 푸세요"}, status_code=401)
        return [{k: targets[i].get(k) for k in ("id", "area", "name", "desc", "disabled") if k in targets[i]} for i in order]

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
        if len(live) >= MAX_SESSIONS:
            return await ws.close(4429)
        day = log_dir / time.strftime("%Y-%m-%d")
        day.mkdir(parents=True, exist_ok=True)
        lf = open(day / f"{time.strftime('%H%M%S')}-{target_id}-{ip.replace(':', '_')}.log", "ab", buffering=0)
        lf.write(f"# figteam-console {time.strftime('%F %T')} target={target_id} ip={ip} argv={t['argv']}\n".encode())

        async def send(text):
            try:
                await ws.send_text(text)
            except Exception:
                pass

        try:
            cols = int(ws.query_params.get("cols", 100))
            rows = int(ws.query_params.get("rows", 30))
        except ValueError:
            cols, rows = 100, 30
        sess = PtySession(t["argv"], cols, rows, send, lf)
        sess.start()
        live.add(sess)
        log.info("open target=%s ip=%s", target_id, ip)

        async def pump_in():
            while True:
                msg = await ws.receive_text()
                try:
                    m = json.loads(msg)
                except ValueError:
                    continue
                if m.get("t") == "i" and isinstance(m.get("d"), str):
                    sess.write(m["d"][:8192])
                elif m.get("t") == "r":
                    try:
                        sess.resize(m.get("c", 100), m.get("r", 30))
                    except (TypeError, ValueError):
                        pass

        async def idle_guard():
            while not sess.closed.is_set():
                await asyncio.sleep(5)
                if time.time() - sess.last_input > IDLE_SECONDS:
                    await send("\r\n[30분 동안 입력이 없어 연결을 닫습니다]\r\n")
                    sess.close()

        tasks = [asyncio.ensure_future(pump_in()), asyncio.ensure_future(sess.closed.wait()),
                 asyncio.ensure_future(idle_guard())]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for x in tasks:
                x.cancel()
            sess.close()
            live.discard(sess)
            log.info("close target=%s ip=%s", target_id, ip)
            try:
                await ws.close(1000)
            except Exception:
                pass

    return app
