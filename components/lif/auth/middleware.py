"""The one inbound auth middleware: run strategies in order, first ``Principal`` wins (ADR 0007).

Bases compose it with the strategies they need instead of carrying their own
middleware, e.g. ``app.add_middleware(AuthMiddleware, strategies=[api_key_strategy(config)])``.
"""

from collections.abc import Collection, Sequence
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from lif.auth.principal import AuthError, Strategy
from lif.auth.request import DEFAULT_PUBLIC_PATH_PREFIXES, DEFAULT_PUBLIC_PATHS, is_public_path

UNAUTHENTICATED_DETAIL = "Missing or invalid credentials"


class AuthMiddleware(BaseHTTPMiddleware):
    """Authenticate every non-public request with the first strategy that returns a ``Principal``.

    On success sets ``request.state.principal`` (the principal's id),
    ``request.state.auth_method`` and ``request.state.claims``. An ``AuthError`` from a
    strategy, or no strategy matching, returns a JSON 401 with ``WWW-Authenticate``.

    ``methods``: HTTP methods that require auth; ``None`` means all of them.
    ``public_paths`` / ``public_prefixes``: ``None`` means the shared defaults.
    """

    def __init__(
        self,
        app,
        strategies: Sequence[Strategy],
        public_paths: Optional[Collection[str]] = None,
        public_prefixes: Optional[Collection[str]] = None,
        methods: Optional[Collection[str]] = None,
        challenge: str = "Bearer",
    ) -> None:
        super().__init__(app)
        self.strategies = list(strategies)
        self.public_paths = DEFAULT_PUBLIC_PATHS if public_paths is None else public_paths
        self.public_prefixes = DEFAULT_PUBLIC_PATH_PREFIXES if public_prefixes is None else public_prefixes
        self.methods = methods
        self.challenge = challenge

    async def dispatch(self, request: Request, call_next):
        if self.methods is not None and request.method not in self.methods:
            return await call_next(request)
        if is_public_path(request.url.path, self.public_paths, self.public_prefixes):
            return await call_next(request)

        try:
            principal = next((p for p in (strategy(request) for strategy in self.strategies) if p is not None), None)
        except AuthError as error:
            return JSONResponse(status_code=error.status_code, content={"detail": error.detail}, headers=error.headers)

        if principal is None:
            return JSONResponse(
                status_code=401,
                content={"detail": UNAUTHENTICATED_DETAIL},
                headers={"WWW-Authenticate": self.challenge},
            )

        request.state.principal = principal.id
        request.state.auth_method = principal.method
        request.state.claims = principal.claims
        return await call_next(request)
