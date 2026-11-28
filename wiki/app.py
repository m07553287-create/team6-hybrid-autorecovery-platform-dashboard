"""figteam 구성 위키 API (FastAPI + Redis)."""
import base64
import hmac
import json
import os
import urllib.parse

from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from wiki import auth, collab, docs, store
from wiki.errors import ApiError

__all__ = ["create_app", "ApiError"]
MAX_BODY = 65536


def create_app(redis_client=None):
    app = FastAPI(title="figteam-wiki", docs_url=None, redoc_url=None, openapi_url=None)
    r = redis_client or store.connect()
    allowed_origin = os.environ.get("ALLOWED_ORIGIN", "https://figteam.ktci5.kr")
    require_key = os.environ.get("WIKI_REQUIRE_ACCESS_KEY", "1") != "0"

    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError):
        resp = JSONResponse({"error": exc.message, **exc.extra}, status_code=exc.status)
        if exc.extra.get("key_expired"):
            resp.delete_cookie(auth.COOKIE, path="/api")
        return resp

    @app.middleware("http")
    async def _guard(request: Request, call_next):
        if request.method in ("POST", "PUT", "DELETE", "PATCH"):
            p = request.url.path
            if p == "/api/ai/oauth/token":
                return await call_next(request)
            if p in ("/api/ai/share", "/api/ai/goals") and (request.headers.get("authorization") or "").startswith("Bearer "):
                return await call_next(request)
            if request.headers.get("origin") != allowed_origin:
                return JSONResponse({"error": "허용되지 않은 출처입니다"}, status_code=403)
        return await call_next(request)

    async def body_of(request):
        raw = await request.body()
        if len(raw) > MAX_BODY:
            raise ApiError(413, "내용이 너무 큽니다 (64KB 이하)")
        try:
            data = json.loads(raw or b"{}")
        except ValueError:
            raise ApiError(400, "JSON 형식이 아닙니다")
        if not isinstance(data, dict):
            raise ApiError(400, "JSON 객체가 필요합니다")
        return data

    def client_key(request):
        return request.headers.get("cf-connecting-ip") or (request.client.host if request.client else "-")

    def set_cookie(resp, token):
        resp.set_cookie(auth.COOKIE, token, max_age=auth.SESSION_TTL, httponly=True, secure=True,
                        samesite="lax", path="/api")

    def session_of(request):
        status, s = auth.get_session_detail(r, request.cookies.get(auth.COOKIE), require_key=require_key)
        if status == "no_key":
            raise ApiError(401, "접속 키가 없는 이전 세션이 만료되었습니다. 다시 로그인해 주세요.", {"key_expired": True})
        if not s:
            raise ApiError(401, "로그인이 필요합니다")
        return s

    def optional_session_of(request):
        status, s = auth.get_session_detail(r, request.cookies.get(auth.COOKIE), require_key=require_key)
        return s if status == "ok" else None

    def ai_session_of(request):
        auth_hdr = request.headers.get("authorization") or ""
        if auth_hdr.startswith("Bearer "):
            s = collab.get_bearer_session(r, auth_hdr)
            if not s:
                raise ApiError(401, "유효하지 않거나 만료된 AI 커넥터 토큰입니다")
            return s
        return session_of(request)

    def base_url_of(request):
        return (os.environ.get("PUBLIC_BASE_URL") or allowed_origin).rstrip("/")

    async def form_or_json(request):
        raw = await request.body()
        if len(raw) > MAX_BODY:
            raise ApiError(413, "내용이 너무 큽니다 (64KB 이하)")
        ctype = (request.headers.get("content-type") or "").lower()
        if "application/json" in ctype:
            try:
                parsed = json.loads(raw or b"{}")
                return parsed if isinstance(parsed, dict) else {}
            except ValueError:
                return {}
        qs = urllib.parse.parse_qs(raw.decode("utf-8", errors="replace"), keep_blank_values=True)
        return {k: (v[0] if v else "") for k, v in qs.items()}

    @app.get("/api/health")
    def health():
        return {"ok": True}

    @app.post("/api/teams", status_code=201)
    async def teams(request: Request, response: Response):
        data = await body_of(request)
        set_cookie(response, auth.create_team(r, data, os.environ.get("TEAM_CREATE_CODE", ""), client_key(request)))
        return {"ok": True}

    @app.post("/api/login")
    async def login(request: Request, response: Response):
        data = await body_of(request)
        set_cookie(response, auth.login(r, data, client_key(request), require_key=require_key))
        return {"ok": True}

    @app.post("/api/logout")
    def logout(request: Request, response: Response):
        auth.logout(r, request.cookies.get(auth.COOKIE))
        response.delete_cookie(auth.COOKIE, path="/api")
        return {"ok": True}

    @app.get("/api/me")
    def me(request: Request, response: Response):
        status, s = auth.get_session_detail(r, request.cookies.get(auth.COOKIE), require_key=require_key)
        if status == "no_key":
            auth.record_site_visit(r, path="/api/me", view="settings", auth_state="expired",
                                   client_ip=client_key(request), ua=request.headers.get("user-agent", ""),
                                   detail="키 없는 위키 세션 만료")
            raise ApiError(401, "접속 키가 없는 이전 세션이 만료되었습니다. 다시 로그인해 주세요.", {"key_expired": True})
        if not s and os.environ.get("AUTO_LOGIN_TEAM"):
            hdr_key = auth.check_access_key(request.headers.get("x-fig-access-key") or "")
            if require_key and not hdr_key:
                raise ApiError(401, "접속 키가 필요합니다. 다시 로그인해 주세요.", {"key_expired": True})
            token, s = auth.auto_session(r, os.environ["AUTO_LOGIN_TEAM"], access_key=hdr_key)
            if token:
                set_cookie(response, token)
        if not s:
            raise ApiError(401, "로그인이 필요합니다")
        out = {"slug": s.slug, "team_name": s.team_name, "member": s.member}
        if s.auto:
            out["auto"] = True
        if s.access_key:
            out["access_key"] = s.access_key
        return out

    @app.post("/api/me/name")
    async def me_name(request: Request):
        data = await body_of(request)
        return {"member": auth.rename(r, request.cookies.get(auth.COOKIE), data.get("member"),
                                      access_key=data.get("access_key"), client_ip=client_key(request))}

    @app.post("/api/access/register")
    async def access_register(request: Request):
        data = await body_of(request)
        s = session_of(request)
        return auth.register_access(r, request.cookies.get(auth.COOKIE), s, data.get("member"),
                                    data.get("access_key"), client_key(request),
                                    data.get("action") or "visit", data.get("detail") or "")

    @app.get("/api/access/logs")
    def access_logs(request: Request, limit: int = 100):
        s = session_of(request)
        return auth.get_access_logs(r, s.team_id, limit)

    @app.post("/api/visit")
    async def record_visit(request: Request):
        data = await body_of(request)
        entry = auth.record_site_visit(
            r,
            path=data.get("path") or "/",
            view=data.get("view") or "",
            auth_state=data.get("auth_state") or "visitor",
            member=data.get("member") or "",
            access_key=data.get("access_key") or "",
            client_ip=client_key(request),
            ua=request.headers.get("user-agent", ""),
            detail=data.get("detail") or "",
        )
        return {"ok": True, "visit": entry}

    @app.get("/api/access/visitors")
    def site_visitors(request: Request, limit: int = 200):
        s = session_of(request)
        return auth.get_site_visits(r, s.team_id, limit)

    @app.post("/api/access/keybook")
    async def access_keybook(request: Request):
        data = await body_of(request)
        s = session_of(request)
        kb = auth.upsert_keybook(r, s.team_id, data.get("access_key"), data.get("member"), client_key(request))
        return {"ok": True, "keybook": kb}

    @app.post("/api/team/password")
    async def team_password(request: Request, response: Response):
        data = await body_of(request)
        auth.change_password(r, session_of(request), data)
        response.delete_cookie(auth.COOKIE, path="/api")
        return {"ok": True}

    @app.get("/api/tree")
    def tree(request: Request):
        return docs.get_tree(r, session_of(request))

    @app.post("/api/docs", status_code=201)
    async def create(request: Request):
        data = await body_of(request)
        s = session_of(request)
        res = docs.create_doc(r, s, data)
        body_obj = data.get("body") or {}
        doc_title = body_obj.get("name") or body_obj.get("title") or ""
        collab.notify_wiki_change(
            s.slug, doc_title, data.get("kind") or "", res.get("rev", 1),
            s.member, s.access_key, data.get("message") or "", action="create",
        )
        return res

    @app.put("/api/docs/{doc_id}")
    async def update(doc_id: int, request: Request):
        data = await body_of(request)
        s = session_of(request)
        res = docs.update_doc(r, s, doc_id, data)
        body_obj = data.get("body") or {}
        doc_title = body_obj.get("name") or body_obj.get("title") or ""
        kind = r.hget(f"fw:doc:{doc_id}", "kind") or ""
        collab.notify_wiki_change(
            s.slug, doc_title, kind, res.get("rev", 1),
            s.member, s.access_key, data.get("message") or "", action="update",
        )
        return res

    @app.delete("/api/docs/{doc_id}")
    async def delete(doc_id: int, request: Request):
        data = await body_of(request)
        return docs.delete_doc(r, session_of(request), doc_id, data)

    @app.get("/api/docs/{doc_id}/revisions")
    def revisions(doc_id: int, request: Request):
        return docs.list_revisions(r, session_of(request), doc_id)

    @app.get("/api/docs/{doc_id}/revisions/{rev}")
    def revision(doc_id: int, rev: int, request: Request):
        return docs.get_revision(r, session_of(request), doc_id, rev)

    @app.post("/api/docs/{doc_id}/restore")
    async def restore(doc_id: int, request: Request):
        data = await body_of(request)
        return docs.restore_doc(r, session_of(request), doc_id, data)

    @app.get("/api/changes")
    def changes(request: Request, before: int = 0, limit: int = 50):
        return docs.list_changes(r, session_of(request), before or None, limit)

    @app.get("/api/scripts")
    def scripts(request: Request):
        return docs.list_scripts(r, session_of(request))

    @app.get("/api/scripts/{script_id}")
    def script(script_id: int, request: Request):
        return docs.get_script(r, session_of(request), script_id)

    # ---- AI 웹 로그인 커넥터 (OAuth 2.0) · 1클릭 Discord 공유 브리지 ----

    @app.get("/api/ai/openapi.json")
    def ai_openapi(request: Request):
        return collab.build_openapi_spec(base_url_of(request))

    @app.get("/api/ai/oauth/authorize")
    def ai_oauth_authorize(
        request: Request,
        client_id: str = "",
        redirect_uri: str = "",
        state: str = "",
        scope: str = "read write",
    ):
        expected_cid, _ = collab.oauth_client_config()
        if client_id != expected_cid:
            return HTMLResponse(
                collab.render_oauth_authorize_html(
                    optional_session_of(request),
                    {"client_id": client_id, "redirect_uri": redirect_uri, "state": state, "scope": scope},
                    error="허용되지 않은 client_id 입니다.",
                ),
                status_code=400,
            )
        if not collab.is_allowed_redirect(redirect_uri):
            return HTMLResponse(
                collab.render_oauth_authorize_html(
                    optional_session_of(request),
                    {"client_id": client_id, "redirect_uri": redirect_uri, "state": state, "scope": scope},
                    error="허용되지 않은 redirect_uri 입니다.",
                ),
                status_code=400,
            )
        return HTMLResponse(
            collab.render_oauth_authorize_html(
                optional_session_of(request),
                {"client_id": client_id, "redirect_uri": redirect_uri, "state": state, "scope": scope},
            )
        )

    @app.post("/api/ai/oauth/approve")
    async def ai_oauth_approve(request: Request):
        form = await form_or_json(request)
        client_id = str(form.get("client_id") or "")
        redirect_uri = str(form.get("redirect_uri") or "")
        state = str(form.get("state") or "")
        scope = str(form.get("scope") or "read write")
        params = {"client_id": client_id, "redirect_uri": redirect_uri, "state": state, "scope": scope}

        if not collab.is_allowed_redirect(redirect_uri):
            return HTMLResponse(
                collab.render_oauth_authorize_html(optional_session_of(request), params, error="허용되지 않은 redirect_uri 입니다."),
                status_code=400,
            )

        s = optional_session_of(request)
        new_cookie_tok = None
        if not s:
            slug = str(form.get("slug") or os.environ.get("DEFAULT_TEAM_SLUG", "figteam")).strip() or "figteam"
            try:
                new_cookie_tok = auth.login(
                    r,
                    {
                        "slug": slug,
                        "member": form.get("member") or "",
                        "access_key": form.get("access_key") or "",
                        "password": form.get("password") or "",
                    },
                    client_key(request),
                    require_key=require_key,
                )
                _, s = auth.get_session_detail(r, new_cookie_tok, require_key=require_key)
            except ApiError as exc:
                return HTMLResponse(
                    collab.render_oauth_authorize_html(None, params, error=exc.message, default_slug=slug),
                    status_code=exc.status,
                )

        try:
            code = collab.issue_oauth_code(r, s, client_id, redirect_uri)
        except ApiError as exc:
            return HTMLResponse(
                collab.render_oauth_authorize_html(s, params, error=exc.message),
                status_code=exc.status,
            )

        sep = "&" if "?" in redirect_uri else "?"
        loc = f"{redirect_uri}{sep}code={urllib.parse.quote(code)}"
        if state:
            loc += f"&state={urllib.parse.quote(state)}"
        resp = RedirectResponse(loc, status_code=302)
        if new_cookie_tok:
            set_cookie(resp, new_cookie_tok)
        return resp

    @app.post("/api/ai/oauth/token")
    async def ai_oauth_token(request: Request):
        form = await form_or_json(request)
        client_id = str(form.get("client_id") or "")
        client_secret = str(form.get("client_secret") or "")
        auth_hdr = request.headers.get("authorization") or ""
        if auth_hdr.startswith("Basic "):
            try:
                decoded = base64.b64decode(auth_hdr[6:].strip()).decode("utf-8", errors="replace")
                if ":" in decoded:
                    b_cid, b_sec = decoded.split(":", 1)
                    client_id = client_id or b_cid
                    client_secret = client_secret or b_sec
            except Exception:  # noqa: BLE001
                pass

        if str(form.get("grant_type") or "") != "authorization_code":
            return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)
        try:
            tok_resp = collab.exchange_oauth_code(
                r,
                code=str(form.get("code") or ""),
                client_id=client_id,
                redirect_uri=str(form.get("redirect_uri") or ""),
                client_secret=client_secret,
            )
            return JSONResponse(tok_resp, headers={"Cache-Control": "no-store"})
        except ValueError as exc:
            return JSONResponse({"error": "invalid_grant", "error_description": str(exc)}, status_code=400)

    @app.get("/api/ai/feed")
    def ai_feed(request: Request, limit: int = 15, area: str = ""):
        s = ai_session_of(request)
        return collab.build_ai_feed(r, s, limit=limit, area=area)

    @app.get("/api/ai/feed/internal")
    def ai_feed_internal(request: Request, team: str = "figteam", limit: int = 10):
        expected = os.environ.get("FIGTEAM_INTERNAL_KEY") or os.environ.get("FIGTEAM_AUTH_KEY") or "figteam-sec-2026-dr"
        provided = request.headers.get("x-internal-key") or ""
        if not provided or not hmac.compare_digest(provided, expected):
            raise ApiError(401, "내부 인증 키가 필요합니다")
        return collab.build_internal_feed(r, team_slug=team, limit=limit)

    @app.post("/api/ai/share")
    async def ai_share(request: Request):
        s = ai_session_of(request)
        data = await body_of(request)
        source = "ai_connector" if (request.headers.get("authorization") or "").startswith("Bearer ") else "web"
        return collab.create_share(r, s, data, source=source)

    @app.get("/api/ai/goals")
    def ai_goals_get(request: Request, limit: int = 50):
        s = ai_session_of(request)
        goals = collab.list_goals(r, s.team_id, limit=limit)
        return {"goals": goals, "summary": collab.summarize_goals(goals)}

    @app.post("/api/ai/goals")
    async def ai_goals_post(request: Request):
        s = ai_session_of(request)
        return collab.upsert_goal(r, s, await body_of(request))

    @app.get("/api/ai/prompt")
    def ai_prompt_get(request: Request, goal_id: int = 0):
        s = ai_session_of(request)
        goals = collab.list_goals(r, s.team_id, limit=50)
        shares = collab.list_shares(r, s.team_id, limit=15)
        changes = docs.list_changes(r, s, limit=8)
        full_p, short_p = collab.build_ai_launch_prompt(
            s.slug, s.member, s.access_key, goals, shares, changes, focus_goal_id=goal_id or None
        )
        return {
            "prompt": full_p,
            "short_prompt": short_p,
            "goal_summary": collab.summarize_goals(goals),
        }

    def _hub_render(s, prefill, error="", notice="", default_slug="figteam", status_code=200):
        dc_ok = bool(os.environ.get("FIGTEAM_DISCORD_WEBHOOK_URL", "").strip())
        if s:
            goals = collab.list_goals(r, s.team_id, limit=50)
            shares = collab.list_shares(r, s.team_id, limit=15)
            changes = docs.list_changes(r, s, limit=5)
            fg = collab._parse_optional_int(prefill.get("goal_id"))
            prompts = collab.build_ai_launch_prompt(
                s.slug, s.member, s.access_key, goals, shares, changes, focus_goal_id=fg
            )
        else:
            goals, shares, prompts = [], [], ("", "")
        return HTMLResponse(
            collab.render_collab_hub_html(
                s,
                prefill,
                shares,
                dc_ok,
                goals=goals,
                ai_prompts=prompts,
                error=error,
                notice=notice,
                default_slug=default_slug,
            ),
            status_code=status_code,
        )

    def _hub_session_or_login(request: Request, form: dict):
        s = optional_session_of(request)
        if s:
            return s, None
        slug = str(form.get("slug") or os.environ.get("DEFAULT_TEAM_SLUG", "figteam")).strip() or "figteam"
        tok = auth.login(
            r,
            {
                "slug": slug,
                "member": form.get("member") or "",
                "access_key": form.get("access_key") or "",
                "password": form.get("password") or "",
            },
            client_key(request),
            require_key=require_key,
        )
        _, s = auth.get_session_detail(r, tok, require_key=require_key)
        return s, tok

    @app.get("/api/ai/hub")
    @app.get("/api/ai/share-ui")
    def ai_share_ui_get(
        request: Request,
        area: str = "general",
        status: str = "info",
        title: str = "",
        summary: str = "",
        check: str = "",
        cfg_url: str = "",
        goal_id: str = "",
        goal_status: str = "",
    ):
        s = optional_session_of(request)
        prefill = {
            "area": area,
            "status": status,
            "title": title,
            "summary": summary,
            "check_request": check,
            "cfg_url": cfg_url,
            "goal_id": goal_id,
            "goal_status": goal_status,
        }
        return _hub_render(s, prefill)

    @app.post("/api/ai/hub")
    @app.post("/api/ai/share-ui")
    async def ai_share_ui_post(request: Request):
        form = await form_or_json(request)
        prefill = {
            "area": str(form.get("area") or "general"),
            "status": str(form.get("status") or "info"),
            "title": str(form.get("title") or ""),
            "summary": str(form.get("summary") or ""),
            "check_request": str(form.get("check_request") or ""),
            "cfg_url": str(form.get("cfg_url") or ""),
            "goal_id": str(form.get("goal_id") or ""),
            "goal_status": str(form.get("goal_status") or ""),
        }
        slug = str(form.get("slug") or os.environ.get("DEFAULT_TEAM_SLUG", "figteam")).strip() or "figteam"
        try:
            s, new_cookie_tok = _hub_session_or_login(request, form)
        except ApiError as exc:
            return _hub_render(None, prefill, error=exc.message, default_slug=slug, status_code=exc.status)

        try:
            res = collab.create_share(r, s, prefill, source="web_bridge")
        except ApiError as exc:
            resp = _hub_render(s, prefill, error=exc.message, status_code=exc.status)
            if new_cookie_tok:
                set_cookie(resp, new_cookie_tok)
            return resp

        dc_msg = "Discord 채널 전송 완료" if res["discord"].get("sent") else f"팀 피드 저장 완료 (Discord: {res['discord'].get('reason', '미전송')})"
        hints = res.get("crosscheck_hints") or []
        hint_msg = f" · 교차확인 힌트 {len(hints)}건" if hints else ""
        resp = _hub_render(
            s,
            {"area": prefill["area"], "status": "info", "title": "", "summary": "", "check_request": "", "cfg_url": prefill["cfg_url"], "goal_id": prefill["goal_id"]},
            notice=f"공유 #{res['share']['id']} 등록됨 — {dc_msg}{hint_msg}",
        )
        if new_cookie_tok:
            set_cookie(resp, new_cookie_tok)
        return resp

    @app.post("/api/ai/hub/goal")
    async def ai_hub_goal_post(request: Request):
        form = await form_or_json(request)
        slug = str(form.get("slug") or os.environ.get("DEFAULT_TEAM_SLUG", "figteam")).strip() or "figteam"
        try:
            s, new_cookie_tok = _hub_session_or_login(request, form)
        except ApiError as exc:
            return _hub_render(None, {"area": "general"}, error=exc.message, default_slug=slug, status_code=exc.status)

        try:
            res = collab.upsert_goal(r, s, form)
        except ApiError as exc:
            resp = _hub_render(s, {"area": "general"}, error=exc.message, status_code=exc.status)
            if new_cookie_tok:
                set_cookie(resp, new_cookie_tok)
            return resp

        g_obj = res["goal"]
        resp = _hub_render(
            s,
            {"area": g_obj.get("area") or "general", "goal_id": str(g_obj["id"])},
            notice=f"공동 목표 #{g_obj['id']} [{g_obj['status_label']}] 저장됨 (전체 달성 {res['summary']['done']}/{res['summary']['total']})",
        )
        if new_cookie_tok:
            set_cookie(resp, new_cookie_tok)
        return resp

    @app.post("/api/ai/hub/goal-status")
    async def ai_hub_goal_status_post(request: Request):
        form = await form_or_json(request)
        s = session_of(request)
        res = collab.upsert_goal(r, s, {"goal_id": form.get("goal_id"), "status": form.get("status")})
        g_obj = res["goal"]
        return _hub_render(
            s,
            {"area": g_obj.get("area") or "general", "goal_id": str(g_obj["id"])},
            notice=f"공동 목표 #{g_obj['id']} → [{g_obj['status_label']}] 변경됨 (달성 {res['summary']['done']}/{res['summary']['total']})",
        )

    static_dir = os.environ.get("SERVE_STATIC")
    if static_dir:  # 로컬 개발 전용: 화면(public/)도 같은 출처로 제공
        from fastapi.staticfiles import StaticFiles
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

    return app
