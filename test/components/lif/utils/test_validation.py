import os
import pytest
from unittest.mock import patch

from lif.exceptions.core import MissingEnvironmentVariableException
from lif.utils.core import (
    check_required_env_vars,
    get_required_env_var,
)
from lif.utils.validation import (
    is_truthy,
    is_falsy,
    to_bool,
)


class TestEnvironmentValidation:
    """Test environment variable validation functions."""

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
        test_env = {
            "VAR1": "value1",
            "VAR2": "value2", 
            "VAR3": "value3"
        }
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


class TestTruthyFalsy:
    """Test truthy/falsy validation functions."""

    def test_is_truthy(self):
        """Test is_truthy function with various inputs."""
        # Truthy values
        assert is_truthy("true") is True
        assert is_truthy("TRUE") is True
        assert is_truthy("yes") is True
        assert is_truthy("1") is True
        assert is_truthy("on") is True
        assert is_truthy("y") is True
        assert is_truthy(True) is True
        
        # Falsy values
        assert is_truthy("false") is False
        assert is_truthy("no") is False
        assert is_truthy("0") is False
        assert is_truthy("off") is False
        assert is_truthy(False) is False
        assert is_truthy(None) is False
        assert is_truthy("") is False

    def test_is_falsy(self):
        """Test is_falsy function with various inputs."""
        # Falsy values
        assert is_falsy("false") is True
        assert is_falsy("FALSE") is True
        assert is_falsy("no") is True
        assert is_falsy("0") is True
        assert is_falsy("off") is True
        assert is_falsy("n") is True
        assert is_falsy(False) is True
        assert is_falsy(None) is True
        
        # Truthy values
        assert is_falsy("true") is False
        assert is_falsy("yes") is False
        assert is_falsy("1") is False
        assert is_falsy(True) is False

    def test_to_bool(self):
        """Test to_bool function with various inputs."""
        # Truthy values
        assert to_bool("true") is True
        assert to_bool("yes") is True
        assert to_bool("1") is True
        
        # Falsy values
        assert to_bool("false") is False
        assert to_bool("no") is False
        assert to_bool("0") is False
        
        # Ambiguous values use default
        assert to_bool("maybe") is False  # default is False
        assert to_bool("maybe", default=True) is True
        assert to_bool("random", default=False) is False
