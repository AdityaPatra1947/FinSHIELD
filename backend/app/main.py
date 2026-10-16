from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1 import admin, auth, routes
from app.core.config import config_report, ensure_dev_pepper, get_settings
from app.db import backend_name, init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_dev_pepper()
    init_db()
    from app.store import get_store
    get_store()
    import threading
    threading.Thread(target=admin.warm, daemon=True).start()
    yield


settings = get_settings()
app = FastAPI(title="FinShield API", version="0.2.0", lifespan=lifespan, docs_url="/api/v1/docs",
              openapi_url="/api/v1/openapi.json")
app.add_middleware(CORSMiddleware, allow_origins=settings.origins, allow_credentials=True,
                   allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"], allow_headers=["*"])


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    return resp


@app.exception_handler(RequestValidationError)
async def validation_handler(_: Request, exc: RequestValidationError):
    fields = {".".join(str(p) for p in e["loc"][1:]): e["msg"] for e in exc.errors()}
    return JSONResponse(status_code=422, content={"detail": {"error": {"code": "validation_error",
                        "message": "Invalid request", "fields": fields}}})


@app.exception_handler(Exception)
async def unhandled(_: Request, exc: Exception):  # never expose statements, DSNs or tracebacks
    return JSONResponse(status_code=500, content={"detail": {"error": {"code": "internal_error",
                        "message": "Unexpected server error"}}})


v1 = APIRouter(prefix="/api/v1")


@v1.get("/health/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@v1.get("/health/ready")
async def ready():
    from app.store import get_store
    s = get_store()
    return {"status": "ready" if s.ready else "not_ready", "database": backend_name(), "data_built": s.ready,
            "config": config_report(get_settings())}


v1.include_router(auth.router)
v1.include_router(routes.router)
v1.include_router(admin.router)
app.include_router(v1)
