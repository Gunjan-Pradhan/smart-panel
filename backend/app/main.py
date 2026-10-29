"""FastAPI application entry point.

Run locally from the repository root:
    .\\.venv\\Scripts\\uvicorn.exe app.main:app --app-dir backend --reload
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, devices
from app.config import get_settings


def validate_security_settings() -> None:
    """Fail fast on unsafe authentication configuration."""

    settings = get_settings()
    secret = settings.jwt_secret.get_secret_value()
    if len(secret) < 32:
        raise RuntimeError("JWT_SECRET must be at least 32 characters")
    if settings.app_env != "development" and "change_me" in secret.lower():
        raise RuntimeError("JWT_SECRET still contains the example value")


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_security_settings()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.2.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth.router)
    app.include_router(devices.router)

    @app.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok", "phase": "2"}

    return app


app = create_app()
