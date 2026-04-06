"""FastAPI app factory for sable serve."""
from __future__ import annotations

import logging
import sqlite3

from fastapi import Depends, FastAPI, Request, Response
from fastapi.responses import JSONResponse

from sable.serve.auth import resolve_client, verify_token  # noqa: F401 — verify_token used as Depends()
from sable.serve.rate_limit import RateLimiter

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Build and return the FastAPI application."""
    app = FastAPI(title="Sable API", version="0.1.0")

    from sable.serve.routes import vault, pulse, meta

    # Rate limiter (in-process, no external deps)
    from sable.serve.auth import get_serve_cfg
    serve_cfg = get_serve_cfg()
    rpm = serve_cfg.get("rate_limit_rpm", 60)
    limiter = RateLimiter(requests_per_minute=rpm)

    @app.middleware("http")
    async def rate_limit_middleware(request: Request, call_next):
        # Skip rate limiting for health endpoint
        if request.url.path == "/health":
            return await call_next(request)

        # Resolve client identity *before* rate accounting so anonymous
        # traffic cannot consume an authenticated client's budget.
        client = resolve_client(request)

        retry_after = limiter.check(request.url.path, client=client)
        if retry_after is not None:
            return Response(
                content='{"detail":"Rate limit exceeded"}',
                status_code=429,
                media_type="application/json",
                headers={"Retry-After": str(retry_after)},
            )
        return await call_next(request)

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

    @app.exception_handler(Exception)
    async def _global_exception_handler(request: Request, exc: Exception):
        logger.error("Unhandled error on %s: %s", request.url.path, exc, exc_info=True)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    @app.get("/health")
    def health():
        checks = _run_health_checks()
        status = "ok" if all(checks.values()) else "degraded"
        return {"status": status, "checks": checks}

    return app


def _run_health_checks() -> dict[str, bool]:
    """Run lightweight dependency checks for the health endpoint."""
    from sable.shared.paths import pulse_db_path, meta_db_path, vault_dir

    checks: dict[str, bool] = {}

    # pulse.db readable
    try:
        p = pulse_db_path()
        if p.exists():
            conn = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
            conn.execute("SELECT 1")
            conn.close()
            checks["pulse_db"] = True
        else:
            checks["pulse_db"] = False
    except Exception as e:
        logger.warning("Health check pulse_db probe failed: %s", e)
        checks["pulse_db"] = False

    # meta.db readable
    try:
        m = meta_db_path()
        if m.exists():
            conn = sqlite3.connect(f"file:{m}?mode=ro", uri=True)
            conn.execute("SELECT 1")
            conn.close()
            checks["meta_db"] = True
        else:
            checks["meta_db"] = False
    except Exception as e:
        logger.warning("Health check meta_db probe failed: %s", e)
        checks["meta_db"] = False

    # vault path exists
    try:
        v = vault_dir()
        checks["vault"] = v.exists() and v.is_dir()
    except Exception as e:
        logger.warning("Health check vault probe failed: %s", e)
        checks["vault"] = False

    return checks
