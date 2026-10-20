import pytest
from starlette.requests import Request

from lif.auth.api_key import ApiKeyConfig, api_key_strategy
from lif.auth.principal import AuthError


def _req(headers: dict[str, str]):
    raw = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    return Request({"type": "http", "method": "GET", "path": "/", "headers": raw})


def test_known_key_authenticates_as_its_client():
    principal = api_key_strategy(ApiKeyConfig(api_keys={"k1": "client-1"}))(_req({"X-API-Key": "k1"}))
    assert principal is not None
    assert (principal.id, principal.method) == ("client-1", "api_key")


def test_missing_header_falls_through():
    assert api_key_strategy(ApiKeyConfig(api_keys={"k1": "client-1"}))(_req({})) is None


def test_unknown_key_is_rejected_with_header_challenge():
    with pytest.raises(AuthError) as exc:
        api_key_strategy(ApiKeyConfig(api_keys={"k1": "client-1"}))(_req({"X-API-Key": "nope"}))
    assert exc.value.detail == "Invalid API key."
    assert exc.value.headers == {"WWW-Authenticate": "X-API-Key"}


def test_custom_header():
    config = ApiKeyConfig(api_keys={"tok": "default"}, header="x-key")
    assert api_key_strategy(config)(_req({"x-key": "tok"})) is not None
    assert api_key_strategy(config)(_req({"X-API-Key": "tok"})) is None


def test_from_environment_sets_header(monkeypatch):
    monkeypatch.setenv("SVC__API_KEYS", "tok:default")
    config = ApiKeyConfig.from_environment(prefix="SVC", header="x-key")
    assert (config.api_keys, config.header) == ({"tok": "default"}, "x-key")
