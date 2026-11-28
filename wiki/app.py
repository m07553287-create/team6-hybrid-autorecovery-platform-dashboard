"""figteam 구성 위키 API (FastAPI + Redis)."""
import json
import os

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from wiki import auth, docs, store
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
        if request.method in ("POST", "PUT", "DELETE", "PATCH") and request.headers.get("origin") != allowed_origin:
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
        return docs.create_doc(r, session_of(request), data)

    @app.put("/api/docs/{doc_id}")
    async def update(doc_id: int, request: Request):
        data = await body_of(request)
        return docs.update_doc(r, session_of(request), doc_id, data)

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

    static_dir = os.environ.get("SERVE_STATIC")
    if static_dir:  # 로컬 개발 전용: 화면(public/)도 같은 출처로 제공
        from fastapi.staticfiles import StaticFiles
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

    return app
