"""Pytest configuration for semantic search MCP server tests.

The semantic search MCP server initializes schema at module import time,
so we need to set environment variables before the test module is imported.
"""

import os
import pytest

# Store original value and set env var before any test imports
_original_value = os.environ.get("USE_OPENAPI_DATA_MODEL_FROM_FILE")
os.environ["USE_OPENAPI_DATA_MODEL_FROM_FILE"] = "true"


@pytest.fixture(scope="module", autouse=True)
def _cleanup_env_after_module():
    """Clean up environment variable after this test module completes."""
    yield
    # Restore original value after module tests complete
    if _original_value is None:
        os.environ.pop("USE_OPENAPI_DATA_MODEL_FROM_FILE", None)
    else:
        os.environ["USE_OPENAPI_DATA_MODEL_FROM_FILE"] = _original_value
