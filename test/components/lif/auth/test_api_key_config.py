# cspell:ignore validkey validname invalidkey
"""Tests for lif.auth.api_key.ApiKeyConfig (moved from api_key_auth, ADR 0007)."""

import os
from unittest.mock import patch

from lif.auth.api_key import ApiKeyConfig


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
