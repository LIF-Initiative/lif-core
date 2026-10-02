"""CompositeAuthMiddleware (#1034 scaffold) — pinned before the #548 auth_utils refactor."""

from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient
from lif.learner_data_export_api.core import CompositeAuthMiddleware


def _app(strategies) -> FastAPI:
    app = FastAPI()
    app.add_middleware(CompositeAuthMiddleware, strategies=strategies)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/docs-extra")
    async def docs_extra():
        return {"ok": True}

    @app.get("/protected")
    async def protected(request: Request):
        return {"auth_method": request.state.auth_method, "principal": request.state.principal}

    return app


async def _get(app: FastAPI, path: str):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.get(path)


async def test_default_public_paths_bypass_auth():
    app = _app([("never", lambda r: None)])
    assert (await _get(app, "/health")).status_code == 200
    assert (await _get(app, "/docs-extra")).status_code == 200  # "/docs" is a public prefix


async def test_no_matching_strategy_returns_401():
    resp = await _get(_app([("never", lambda r: None)]), "/protected")
    assert resp.status_code == 401
    assert resp.json() == {"detail": "Missing or invalid credentials"}


async def test_first_matching_strategy_wins():
    app = _app([("never", lambda r: None), ("first", lambda r: {"sub": "a"}), ("second", lambda r: {"sub": "b"})])
    resp = await _get(app, "/protected")
    assert resp.status_code == 200
    assert resp.json() == {"auth_method": "first", "principal": {"sub": "a"}}
