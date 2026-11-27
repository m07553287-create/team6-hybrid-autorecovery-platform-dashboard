"""figteam 구성 위키 API (FastAPI)."""
import os

import json

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from wiki import auth, docs
from wiki.errors import ApiError
from wiki.db import connect, init_schema

MAX_BODY = 65536

__all__ = ["create_app", "ApiError"]


def create_app():
    app = FastAPI(title="figteam-wiki", docs_url=None, redoc_url=None, openapi_url=None)
    db_path = os.environ.get("WIKI_DB", "/var/lib/figteam-wiki/wiki.db")
    conn = connect(db_path)
    init_schema(conn)
    conn.close()
    app.state.db_path = db_path

    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError):
        return JSONResponse({"error": exc.message, **exc.extra}, status_code=exc.status)

    allowed_origin = os.environ.get("ALLOWED_ORIGIN", "https://figteam.ktci5.kr")

    @app.middleware("http")
    async def _guard(request: Request, call_next):
        if request.method in ("POST", "PUT", "DELETE", "PATCH"):
            if request.headers.get("origin") != allowed_origin:
                return JSONResponse({"error": "허용되지 않은 출처입니다"}, status_code=403)
        return await call_next(request)

    def db():
        return connect(app.state.db_path)

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

    def session_of(request, conn):
        s = auth.get_session(conn, request.cookies.get(auth.COOKIE))
        if not s:
            raise ApiError(401, "로그인이 필요합니다")
        return s

    app.state.db = db
    app.state.body_of = body_of
    app.state.session_of = session_of

    @app.get("/api/health")
    def health():
        return {"ok": True}

    @app.post("/api/teams", status_code=201)
    async def teams(request: Request, response: Response):
        data = await body_of(request)
        conn = db()
        try:
            token = auth.create_team(conn, data, os.environ.get("TEAM_CREATE_CODE", ""), client_key(request))
        finally:
            conn.close()
        set_cookie(response, token)
        return {"ok": True}

    @app.post("/api/login")
    async def login(request: Request, response: Response):
        data = await body_of(request)
        conn = db()
        try:
            token = auth.login(conn, data, client_key(request))
        finally:
            conn.close()
        set_cookie(response, token)
        return {"ok": True}

    @app.post("/api/logout")
    def logout(request: Request, response: Response):
        conn = db()
        try:
            auth.logout(conn, request.cookies.get(auth.COOKIE))
        finally:
            conn.close()
        response.delete_cookie(auth.COOKIE, path="/api")
        return {"ok": True}

    @app.get("/api/me")
    def me(request: Request):
        conn = db()
        try:
            s = session_of(request, conn)
        finally:
            conn.close()
        return {"slug": s.slug, "team_name": s.team_name, "member": s.member}

    @app.post("/api/team/password")
    async def team_password(request: Request, response: Response):
        data = await body_of(request)
        conn = db()
        try:
            s = session_of(request, conn)
            auth.change_password(conn, s, data)
        finally:
            conn.close()
        response.delete_cookie(auth.COOKIE, path="/api")
        return {"ok": True}

    def with_session(fn):
        """세션 확인 후 fn(conn, session) 결과를 돌려준다."""
        def run(request):
            conn = db()
            try:
                return fn(conn, session_of(request, conn))
            finally:
                conn.close()
        return run

    @app.get("/api/tree")
    def tree(request: Request):
        return with_session(docs.get_tree)(request)

    @app.post("/api/docs", status_code=201)
    async def create(request: Request):
        data = await body_of(request)
        return with_session(lambda c, s: docs.create_doc(c, s, data))(request)

    @app.put("/api/docs/{doc_id}")
    async def update(doc_id: int, request: Request):
        data = await body_of(request)
        return with_session(lambda c, s: docs.update_doc(c, s, doc_id, data))(request)

    @app.delete("/api/docs/{doc_id}")
    async def delete(doc_id: int, request: Request):
        data = await body_of(request)
        return with_session(lambda c, s: docs.delete_doc(c, s, doc_id, data))(request)

    @app.get("/api/docs/{doc_id}/revisions")
    def revisions(doc_id: int, request: Request):
        return with_session(lambda c, s: docs.list_revisions(c, s, doc_id))(request)

    @app.get("/api/docs/{doc_id}/revisions/{rev}")
    def revision(doc_id: int, rev: int, request: Request):
        return with_session(lambda c, s: docs.get_revision(c, s, doc_id, rev))(request)

    @app.post("/api/docs/{doc_id}/restore")
    async def restore(doc_id: int, request: Request):
        data = await body_of(request)
        return with_session(lambda c, s: docs.restore_doc(c, s, doc_id, data))(request)

    @app.get("/api/changes")
    def changes(request: Request, before: int = 0, limit: int = 50):
        return with_session(lambda c, s: docs.list_changes(c, s, before or None, limit))(request)

    @app.get("/api/scripts")
    def scripts(request: Request):
        return with_session(docs.list_scripts)(request)

    @app.get("/api/scripts/{script_id}")
    def script(script_id: int, request: Request):
        return with_session(lambda c, s: docs.get_script(c, s, script_id))(request)

    static_dir = os.environ.get("SERVE_STATIC")
    if static_dir:  # 로컬 개발 전용: 화면(public/)도 같은 출처로 제공
        from fastapi.staticfiles import StaticFiles
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

    return app
