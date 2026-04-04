"""FastAPI app factory for sable serve."""
from __future__ import annotations

from fastapi import Depends, FastAPI

from sable.serve.auth import verify_token


def create_app() -> FastAPI:
    """Build and return the FastAPI application."""
    app = FastAPI(title="Sable API", version="0.1.0")

    from sable.serve.routes import vault, pulse, meta

    app.include_router(
        vault.router, prefix="/api/vault", tags=["vault"],
        dependencies=[Depends(verify_token)],
    )
    app.include_router(
        pulse.router, prefix="/api/pulse", tags=["pulse"],
        dependencies=[Depends(verify_token)],
    )
    app.include_router(
        meta.router, prefix="/api/meta", tags=["meta"],
        dependencies=[Depends(verify_token)],
    )

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app
