"""What the database tests do when PostgreSQL can't start (#1063).

Locally they skip. In CI they must fail: pr-ci.yml installs no PostgreSQL and gets one only because the
runner image ships it, so if that changed, a skip would turn every database test green, the portable
round trip included, without running them.
"""

from unittest import mock

import pytest

from . import conftest


def _start_postgres_without_a_server():
    with mock.patch.object(conftest.testing.postgresql, "Postgresql", side_effect=RuntimeError("no initdb")):
        conftest._start_postgres()


def test_a_missing_postgres_fails_in_ci(monkeypatch):
    monkeypatch.setenv("CI", "true")
    with pytest.raises(pytest.fail.Exception, match="not available in CI: no initdb"):
        _start_postgres_without_a_server()


def test_a_missing_postgres_skips_locally(monkeypatch):
    monkeypatch.delenv("CI", raising=False)
    with pytest.raises(pytest.skip.Exception, match="not available locally: no initdb"):
        _start_postgres_without_a_server()
