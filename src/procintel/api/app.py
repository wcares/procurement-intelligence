"""HTTP API for the web app.

    uvicorn procintel.api.app:app --port 8000        (with PYTHONPATH=src)
    then run the web app with API_URL=http://localhost:8000

Built from parts: state.py (data loaded from the database), background.py (background jobs), access.py (who may call
administrative endpoints), schemas.py (request and response models), routes/ (one module per endpoint group).
PROCINTEL_CORS_ORIGINS lists the browser origins allowed to call the API directly (the web app's own server forwards
calls, so the default only covers local development).
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from procintel.api import background, config
from procintel.api.routes import ROUTERS
from procintel.api.state import state

CORS_DEFAULT = "http://localhost:3100,http://127.0.0.1:3100"
QUIET_PATHS = {("GET", "/health"), ("GET", "/jobs")}  # requests that do not postpone background jobs


@asynccontextmanager
async def lifespan(_: FastAPI):
    for key, err in config.load_saved().items():  # saved settings from the configuration page
        print(f"config: saved value for {key} ignored: {err}")
    state()  # build the index before the first request rather than during it
    background.start()
    yield
    background.stop()


def create_app() -> FastAPI:
    api = FastAPI(title="procintel", lifespan=lifespan)
    origins = [o.strip() for o in os.environ.get("PROCINTEL_CORS_ORIGINS", CORS_DEFAULT).split(",") if o.strip()]
    api.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST", "PUT", "DELETE"],
                       allow_headers=["Content-Type"])

    @api.middleware("http")
    async def mark_activity(request: Request, call_next):
        """Every user request postpones background jobs; health checks and the jobs list itself do not."""
        if (request.method, request.url.path) not in QUIET_PATHS:
            background.touch()
        return await call_next(request)

    @api.exception_handler(RequestValidationError)
    async def bad_request(_: Request, exc: RequestValidationError) -> JSONResponse:
        # 400 like the mock routes; the client only checks res.ok
        errors = [{"loc": e["loc"], "msg": e["msg"]} for e in exc.errors()]
        return JSONResponse({"error": "invalid request", "detail": errors}, status_code=400)

    for router in ROUTERS:
        api.include_router(router)
    return api


app = create_app()
