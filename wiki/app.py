"""figteam 구성 위키 API (FastAPI)."""
import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from wiki.errors import ApiError
from wiki.db import connect, init_schema

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

    @app.get("/api/health")
    def health():
        return {"ok": True}

    return app
