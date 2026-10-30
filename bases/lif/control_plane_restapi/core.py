"""LIF control-plane API (EPIC #1041, ADR 0002 / ADR 0006).

The service and its own database, without the developer-key endpoints yet (#1182). The key table
waits on the workspace and owner questions in #1190.

Config: ``CONTROL_PLANE__DATABASE_URL`` (required) and Cognito via ``CONTROL_PLANE_AUTH__*``
(``lif.auth.cognito``). Nothing from the MDR domain is imported or configured here.
"""

import os

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from lif.auth import AuthMiddleware
from lif.auth.cognito import CognitoAuthConfig, cognito_strategy
from lif.logging import get_logger

logger = get_logger(__name__)

DATABASE_URL_VAR = "CONTROL_PLANE__DATABASE_URL"


def require_env(name: str) -> str:
    """Return a required setting, failing fast with the variable's name if it is missing (#1179)."""
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is not set; the control-plane API cannot start without it")
    return value


def create_app(engine: AsyncEngine, cognito_config: CognitoAuthConfig) -> FastAPI:
    app = FastAPI(title="LIF Control Plane API", description="LIF control-plane service", version="0.1.0")

    # Fail closed: without a user pool nobody can be authenticated, so with no strategies every
    # non-public path is refused. An empty pool is never handed to cognito_strategy, which would
    # try to fetch JWKS for it on every request that carries a token.
    if not cognito_config.is_enabled:
        logger.warning(
            "Cognito auth NOT configured (CONTROL_PLANE_AUTH__USER_POOL_ID unset): non-public paths return 401"
        )
    strategies = [cognito_strategy(cognito_config)] if cognito_config.is_enabled else []
    app.add_middleware(AuthMiddleware, strategies=strategies)

    @app.get("/health-check")
    async def health_check():
        """Healthy only when the control plane's own database answers."""
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        except Exception:
            logger.exception("Control-plane database is unreachable")
            return JSONResponse(status_code=503, content={"status": "unavailable"})
        return {"status": "ok"}

    return app


app = create_app(
    create_async_engine(require_env(DATABASE_URL_VAR)), CognitoAuthConfig.from_environment(prefix="CONTROL_PLANE_AUTH")
)
