"""The AuthMiddleware contract (ADR 0007): first Principal wins, None falls through, AuthError rejects."""

from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from lif.auth import AuthError, AuthMiddleware, Principal


def _never(request):
    return None


def _always(name):
    return lambda request: Principal(id=name, method=f"m-{name}", claims={"who": name})


def _reject(request):
    raise AuthError("Token has expired")


def _app(strategies, **kwargs) -> FastAPI:
    app = FastAPI()
    app.add_middleware(AuthMiddleware, strategies=strategies, **kwargs)

    @app.get("/health")
    async def health():
        return {"ok": True}

    @app.api_route("/protected", methods=["GET", "OPTIONS"])
    async def protected(request: Request):
        return {
            "principal": getattr(request.state, "principal", None),
            "auth_method": getattr(request.state, "auth_method", None),
            "claims": getattr(request.state, "claims", None),
        }

    return app


async def _call(app, path="/protected", method="GET"):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.request(method, path)


async def test_first_principal_wins_and_sets_state():
    resp = await _call(_app([_never, _always("a"), _always("b")]))
    assert resp.status_code == 200
    assert resp.json() == {"principal": "a", "auth_method": "m-a", "claims": {"who": "a"}}


async def test_no_match_is_401_with_challenge():
    resp = await _call(_app([_never], challenge="X-API-Key"))
    assert resp.status_code == 401
    assert resp.json() == {"detail": "Missing or invalid credentials"}
    assert resp.headers["www-authenticate"] == "X-API-Key"


async def test_auth_error_rejects_with_its_detail_and_stops():
    resp = await _call(_app([_reject, _always("a")]))
    assert resp.status_code == 401
    assert resp.json() == {"detail": "Token has expired"}
    assert resp.headers["www-authenticate"] == "Bearer"


async def test_default_public_paths_and_explicit_empty_allowlist():
    assert (await _call(_app([_never]), "/health")).status_code == 200
    assert (await _call(_app([_never], public_paths=set(), public_prefixes=set()), "/health")).status_code == 401


async def test_methods_filter_skips_auth_for_other_methods():
    app = _app([_never], methods={"GET"})
    assert (await _call(app, method="GET")).status_code == 401
    assert (await _call(app, method="OPTIONS")).status_code == 200
