"""Tests for the api_key_auth component."""

import os
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from lif.api_key_auth import ApiKeyAuthMiddleware, ApiKeyConfig


class TestApiKeyConfig:
    """Tests for ApiKeyConfig dataclass."""

    def test_default_config(self):
        """Test default configuration values."""
        config = ApiKeyConfig()
        assert config.api_keys == {}
        assert "/health" in config.public_paths
        assert "/health-check" in config.public_paths
        assert "/docs" in config.public_path_prefixes
        assert "GET" in config.methods_requiring_auth
        assert "POST" in config.methods_requiring_auth

    def test_custom_config(self):
        """Test custom configuration values."""
        config = ApiKeyConfig(
            api_keys={"key1": "client1", "key2": "client2"},
            public_paths={"/custom-health"},
            public_path_prefixes={"/api/v1/public"},
            methods_requiring_auth={"POST", "PUT"},
        )
        assert len(config.api_keys) == 2
        assert config.api_keys["key1"] == "client1"
        assert "/custom-health" in config.public_paths
        assert "/api/v1/public" in config.public_path_prefixes
        assert "GET" not in config.methods_requiring_auth

    def test_is_enabled_with_keys(self):
        """Test is_enabled returns True when API keys are configured."""
        config = ApiKeyConfig(api_keys={"key1": "client1"})
        assert config.is_enabled is True

    def test_is_enabled_without_keys(self):
        """Test is_enabled returns False when no API keys are configured."""
        config = ApiKeyConfig()
        assert config.is_enabled is False

    def test_from_environment_with_keys(self):
        """Test loading configuration from environment variables."""
        env_vars = {
            "TEST_AUTH__API_KEYS": "key1:client1,key2:client2",
            "TEST_AUTH__PUBLIC_PATHS": "/health,/ready",
            "TEST_AUTH__PUBLIC_PATH_PREFIXES": "/docs,/swagger",
        }
        with patch.dict(os.environ, env_vars, clear=False):
            config = ApiKeyConfig.from_environment(prefix="TEST_AUTH")

        assert len(config.api_keys) == 2
        assert config.api_keys["key1"] == "client1"
        assert config.api_keys["key2"] == "client2"
        assert "/health" in config.public_paths
        assert "/ready" in config.public_paths
        assert "/docs" in config.public_path_prefixes
        assert "/swagger" in config.public_path_prefixes

    def test_from_environment_empty_keys(self):
        """Test loading configuration with empty API keys."""
        env_vars = {"TEST_AUTH__API_KEYS": ""}
        with patch.dict(os.environ, env_vars, clear=False):
            config = ApiKeyConfig.from_environment(prefix="TEST_AUTH")

        assert config.api_keys == {}
        assert config.is_enabled is False

    def test_from_environment_malformed_keys(self):
        """Test loading configuration with malformed API keys (no colon)."""
        env_vars = {"TEST_AUTH__API_KEYS": "validkey:validname,invalidkey,another:valid"}
        with patch.dict(os.environ, env_vars, clear=False):
            config = ApiKeyConfig.from_environment(prefix="TEST_AUTH")

        # Should only include valid key:name pairs
        assert len(config.api_keys) == 2
        assert "validkey" in config.api_keys
        assert "another" in config.api_keys
        assert "invalidkey" not in config.api_keys

    def test_from_environment_whitespace_handling(self):
        """Test that whitespace is properly trimmed from keys and names."""
        env_vars = {"TEST_AUTH__API_KEYS": "  key1 : client1 , key2:client2  "}
        with patch.dict(os.environ, env_vars, clear=False):
            config = ApiKeyConfig.from_environment(prefix="TEST_AUTH")

        assert "key1" in config.api_keys
        assert config.api_keys["key1"] == "client1"
        assert "key2" in config.api_keys

    def test_parse_csv_set(self):
        """Test CSV parsing utility."""
        result = ApiKeyConfig._parse_csv_set("a, b , c,  ,d")
        assert result == {"a", "b", "c", "d"}

    def test_parse_csv_set_empty(self):
        """Test CSV parsing with empty string."""
        result = ApiKeyConfig._parse_csv_set("")
        assert result == set()


class TestApiKeyAuthMiddleware:
    """Tests for ApiKeyAuthMiddleware."""

    @pytest.fixture
    def app_with_auth(self):
        """Create a FastAPI app with auth middleware enabled."""
        config = ApiKeyConfig(
            api_keys={"valid-key": "test-client"}, public_paths={"/health"}, public_path_prefixes={"/docs"}
        )
        app = FastAPI()
        app.add_middleware(ApiKeyAuthMiddleware, config=config)

        @app.get("/health")
        def health():
            return {"status": "ok"}

        @app.get("/docs/openapi")
        def docs():
            return {"docs": "here"}

        @app.get("/protected")
        def protected():
            return {"data": "secret"}

        @app.post("/protected")
        def protected_post():
            return {"created": True}

        return app

    @pytest.fixture
    def app_without_auth(self):
        """Create a FastAPI app with auth middleware but no keys configured."""
        config = ApiKeyConfig(api_keys={})
        app = FastAPI()
        app.add_middleware(ApiKeyAuthMiddleware, config=config)

        @app.get("/endpoint")
        def endpoint():
            return {"data": "open"}

        return app

    def test_public_path_allows_access(self, app_with_auth):
        """Test that public paths don't require authentication."""
        client = TestClient(app_with_auth)
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_public_path_prefix_allows_access(self, app_with_auth):
        """Test that public path prefixes don't require authentication."""
        client = TestClient(app_with_auth)
        response = client.get("/docs/openapi")
        assert response.status_code == 200

    def test_protected_path_requires_key(self, app_with_auth):
        """Test that protected paths require an API key."""
        client = TestClient(app_with_auth)
        response = client.get("/protected")
        assert response.status_code == 401
        assert "Missing API key" in response.json()["detail"]

    def test_protected_path_rejects_invalid_key(self, app_with_auth):
        """Test that invalid API keys are rejected."""
        client = TestClient(app_with_auth)
        response = client.get("/protected", headers={"X-API-Key": "invalid-key"})
        assert response.status_code == 401
        assert "Invalid API key" in response.json()["detail"]

    def test_protected_path_accepts_valid_key(self, app_with_auth):
        """Test that valid API keys are accepted."""
        client = TestClient(app_with_auth)
        response = client.get("/protected", headers={"X-API-Key": "valid-key"})
        assert response.status_code == 200
        assert response.json() == {"data": "secret"}

    def test_post_request_requires_key(self, app_with_auth):
        """Test that POST requests also require authentication."""
        client = TestClient(app_with_auth)

        # Without key
        response = client.post("/protected")
        assert response.status_code == 401

        # With valid key
        response = client.post("/protected", headers={"X-API-Key": "valid-key"})
        assert response.status_code == 200

    def test_options_request_bypasses_auth(self, app_with_auth):
        """Test that OPTIONS requests bypass authentication (for CORS preflight)."""
        client = TestClient(app_with_auth)
        response = client.options("/protected")
        # OPTIONS is not in default methods_requiring_auth, so should pass
        assert response.status_code != 401

    def test_disabled_auth_allows_all(self, app_without_auth):
        """Test that when no keys are configured, all requests are allowed."""
        client = TestClient(app_without_auth)
        response = client.get("/endpoint")
        assert response.status_code == 200
        assert response.json() == {"data": "open"}

    def test_client_name_stored_in_request_state(self, app_with_auth):
        """Test that authenticated client name is available in request state."""
        from fastapi import Request

        # Create a new app to capture request state
        config = ApiKeyConfig(api_keys={"test-key": "test-client-name"})
        app = FastAPI()
        app.add_middleware(ApiKeyAuthMiddleware, config=config)

        captured_client = None

        @app.get("/check-state")
        def check_state(request: Request):
            nonlocal captured_client
            captured_client = getattr(request.state, "api_client", None)
            return {"client": captured_client}

        client = TestClient(app)
        response = client.get("/check-state", headers={"X-API-Key": "test-key"})

        assert response.status_code == 200
        assert captured_client == "test-client-name"
        assert response.json()["client"] == "test-client-name"

    def test_www_authenticate_header_on_401(self, app_with_auth):
        """Test that 401 responses include WWW-Authenticate header."""
        client = TestClient(app_with_auth)
        response = client.get("/protected")
        assert response.status_code == 401
        assert "WWW-Authenticate" in response.headers
        assert response.headers["WWW-Authenticate"] == "X-API-Key"
