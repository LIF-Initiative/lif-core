import os
import pytest
from unittest.mock import patch

from lif.exceptions.core import MissingEnvironmentVariableException
from lif.utils.core import check_required_env_vars, get_required_env_var


class TestEnvironmentUtilities:
    """Test environment variable utilities in core module."""

    def test_get_required_env_var_success(self):
        """Test getting a required environment variable that exists."""
        with patch.dict(os.environ, {"TEST_VAR": "test_value"}):
            result = get_required_env_var("TEST_VAR")
            assert result == "test_value"

    def test_get_required_env_var_missing(self):
        """Test getting a required environment variable that doesn't exist."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(MissingEnvironmentVariableException) as exc_info:
                get_required_env_var("MISSING_VAR")
            assert "MISSING_VAR" in str(exc_info.value)

    def test_check_required_env_vars_success(self):
        """Test checking multiple required environment variables that exist."""
        test_env = {"VAR1": "value1", "VAR2": "value2", "VAR3": "value3"}
        with patch.dict(os.environ, test_env):
            result = check_required_env_vars(["VAR1", "VAR2", "VAR3"])
            assert result == test_env

    def test_check_required_env_vars_missing_single(self):
        """Test checking required environment variables with one missing."""
        with patch.dict(os.environ, {"VAR1": "value1"}, clear=True):
            with pytest.raises(MissingEnvironmentVariableException) as exc_info:
                check_required_env_vars(["VAR1", "MISSING_VAR"])
            assert "MISSING_VAR" in str(exc_info.value)

    def test_check_required_env_vars_missing_multiple(self):
        """Test checking required environment variables with multiple missing."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(Exception) as exc_info:
                check_required_env_vars(["MISSING1", "MISSING2"])
            assert "Missing required environment variables" in str(exc_info.value)
            assert "MISSING1" in str(exc_info.value)
            assert "MISSING2" in str(exc_info.value)
