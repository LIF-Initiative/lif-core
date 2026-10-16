import os
import subprocess
import sys

import pytest

from lif.auth.config import KNOWN_PLACEHOLDERS, require_env, resolve_secret


def test_resolve_secret_returns_stripped_value():
    assert resolve_secret("  a-strong-secret  ", "MY_SECRET") == "a-strong-secret"


@pytest.mark.parametrize("value", [None, "", "   "])
def test_resolve_secret_rejects_unset_or_blank(value):
    with pytest.raises(RuntimeError, match="MY_SECRET is not set"):
        resolve_secret(value, "MY_SECRET")


@pytest.mark.parametrize("value", sorted(KNOWN_PLACEHOLDERS))
def test_resolve_secret_rejects_known_placeholders(value):
    with pytest.raises(RuntimeError, match="MY_SECRET is set to a placeholder"):
        resolve_secret(value, "MY_SECRET")


def test_placeholder_list_covers_shipped_defaults():
    # The values that shipped as MDR defaults, compose defaults, or doc examples.
    for value in ("changeme4", "change4", "changeme1", "replace-with-a-long-random-string"):
        assert value in KNOWN_PLACEHOLDERS


def test_local_example_value_is_not_a_placeholder():
    # deployments/advisor-demo-docker/.env.example ships this for SECRET_KEY; it must keep working.
    assert resolve_secret("changeme-local-only-not-a-real-secret", "SECRET_KEY")


def test_require_env_reads_environment(monkeypatch):
    monkeypatch.setenv("MY_SECRET", "a-strong-secret")
    assert require_env("MY_SECRET") == "a-strong-secret"
    monkeypatch.delenv("MY_SECRET")
    with pytest.raises(RuntimeError, match="MY_SECRET is not set"):
        require_env("MY_SECRET")


def test_config_import_does_not_require_secret_key():
    # MDR imports lif.auth.config but never sets SECRET_KEY; importing the package
    # must not require any service's secret.
    env = {k: v for k, v in os.environ.items() if k != "SECRET_KEY"}
    result = subprocess.run(
        [sys.executable, "-c", "import lif.auth, lif.auth.config"], env=env, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


def test_shared_credentials_can_opt_out_of_the_placeholder_check(monkeypatch):
    # Shared demo credentials (e.g. the Example Data Source's API_TOKEN, which the
    # local Dagster adapter sends as "changeme") must be set, but aren't signing secrets.
    assert resolve_secret("changeme", "API_TOKEN", reject_placeholders=False) == "changeme"
    monkeypatch.setenv("API_TOKEN", "changeme")
    assert require_env("API_TOKEN", reject_placeholders=False) == "changeme"
    with pytest.raises(RuntimeError, match="API_TOKEN is not set"):
        resolve_secret("  ", "API_TOKEN", reject_placeholders=False)
