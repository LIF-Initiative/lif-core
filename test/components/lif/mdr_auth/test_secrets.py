"""MDR auth secrets fail fast, and unset service keys are not accepted (#548, ADR 0007)."""

import logging
import os
import subprocess
import sys

import pytest
from lif.mdr_auth.core import _build_api_keys


def _import_mdr_auth(**overrides: str | None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    for name, value in overrides.items():
        if value is None:
            env.pop(name, None)
        else:
            env[name] = value
    return subprocess.run([sys.executable, "-c", "import lif.mdr_auth.core"], env=env, capture_output=True, text=True)


@pytest.mark.parametrize("value", [None, "", "changeme4", "change4"])
def test_mdr_refuses_to_start_without_a_real_jwt_secret(value):
    result = _import_mdr_auth(MDR__AUTH__JWT_SECRET_KEY=value)
    assert result.returncode != 0
    assert "MDR__AUTH__JWT_SECRET_KEY" in result.stderr


def test_mdr_starts_with_a_real_jwt_secret():
    result = _import_mdr_auth(MDR__AUTH__JWT_SECRET_KEY="a-strong-test-secret")
    assert result.returncode == 0, result.stderr


def test_unset_service_keys_are_skipped_and_warned(caplog):
    configured = {
        "MDR__AUTH__SERVICE_API_KEY__GRAPHQL": ("gql-key", "graphql-service"),
        "MDR__AUTH__SERVICE_API_KEY__TRANSLATOR": (None, "translator-service"),
        "MDR__AUTH__SERVICE_API_KEY__POST_CONFIRM": ("   ", "post-confirm-service"),
    }
    with caplog.at_level(logging.WARNING):
        api_keys = _build_api_keys(configured)
    assert api_keys == {"gql-key": "graphql-service"}
    assert None not in api_keys
    assert "MDR__AUTH__SERVICE_API_KEY__TRANSLATOR" in caplog.text
    assert "MDR__AUTH__SERVICE_API_KEY__POST_CONFIRM" in caplog.text
