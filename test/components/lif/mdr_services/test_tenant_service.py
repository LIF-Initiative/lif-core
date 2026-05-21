"""Unit tests for tenant_service — the thin wrapper over clone_lif_schema."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import DBAPIError

from lif.mdr_services.tenant_service import (
    DUPLICATE_SCHEMA_SQLSTATE,
    InvalidGroupNameError,
    TenantAlreadyExistsError,
    provision_tenant,
    reset_tenant,
)

pytestmark = pytest.mark.asyncio


def _mock_session() -> MagicMock:
    session = MagicMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    return session


class TestProvisionTenant:
    async def test_happy_path_returns_tenant_schema_name(self):
        session = _mock_session()
        result = await provision_tenant(session, "eval-jsmith")
        assert result == "tenant_eval_jsmith"
        session.execute.assert_awaited_once()
        # Assert the SQL bound :target to the sanitized name
        call = session.execute.await_args
        assert call.args[1] == {"target": "tenant_eval_jsmith"}
        session.commit.assert_awaited_once()

    async def test_sanitizes_group_name_before_passing_to_sql(self):
        """`Acme University` → `tenant_acme_university`; this is the one place the
        sanitizer rules matter for the SQL call."""
        session = _mock_session()
        result = await provision_tenant(session, "Acme University")
        assert result == "tenant_acme_university"
        assert session.execute.await_args.args[1] == {"target": "tenant_acme_university"}

    async def test_invalid_group_name_raises_without_db_call(self):
        session = _mock_session()
        with pytest.raises(InvalidGroupNameError):
            await provision_tenant(session, "---")
        session.execute.assert_not_awaited()

    async def test_duplicate_schema_sqlstate_raises_tenant_exists(self):
        """The DB function raises 42P06 when the target schema is already there;
        we translate that to our own exception so the endpoint can return 200."""
        session = _mock_session()
        orig = MagicMock(sqlstate=DUPLICATE_SCHEMA_SQLSTATE, pgcode=DUPLICATE_SCHEMA_SQLSTATE)
        session.execute.side_effect = DBAPIError("statement", {}, orig)

        with pytest.raises(TenantAlreadyExistsError) as exc_info:
            await provision_tenant(session, "lif-team")
        assert exc_info.value.tenant_schema == "tenant_lif_team"

    async def test_other_db_errors_propagate_unchanged(self):
        """Constraint violations, connection errors, etc. are not our concern —
        let them bubble so the endpoint returns 500, not a misleading 409."""
        session = _mock_session()
        orig = MagicMock(sqlstate="08000", pgcode="08000")  # connection_exception
        session.execute.side_effect = DBAPIError("statement", {}, orig)

        with pytest.raises(DBAPIError):
            await provision_tenant(session, "lif-team")


class TestResetTenant:
    async def test_drops_then_clones_in_one_transaction(self):
        """The two SQL calls must run against the same session (same txn) and
        commit exactly once — if the clone fails, the drop has to roll back so
        we don't leave the user without any schema."""
        session = _mock_session()
        result = await reset_tenant(session, "lif-team")

        assert result == "tenant_lif_team"
        assert session.execute.await_count == 2
        # Drop fires first, then clone — order matters (clone would 42P06 if the
        # schema existed and we hadn't dropped it).
        drop_call, clone_call = session.execute.await_args_list
        assert "DROP SCHEMA IF EXISTS" in str(drop_call.args[0])
        assert "tenant_lif_team" in str(drop_call.args[0])
        assert "clone_lif_schema" in str(clone_call.args[0])
        assert clone_call.args[1] == {"target": "tenant_lif_team"}
        session.commit.assert_awaited_once()

    async def test_sanitizes_group_name_before_drop_and_clone(self):
        """Both SQL statements must target the sanitized schema name. If they
        diverged we'd drop one schema and clone into another — silent corruption."""
        session = _mock_session()
        result = await reset_tenant(session, "Acme University")

        assert result == "tenant_acme_university"
        drop_call, clone_call = session.execute.await_args_list
        assert "tenant_acme_university" in str(drop_call.args[0])
        assert clone_call.args[1] == {"target": "tenant_acme_university"}

    async def test_invalid_group_name_raises_without_db_call(self):
        session = _mock_session()
        with pytest.raises(InvalidGroupNameError):
            await reset_tenant(session, "---")
        session.execute.assert_not_awaited()
        session.commit.assert_not_awaited()

    async def test_missing_schema_is_idempotent(self):
        """DROP SCHEMA IF EXISTS turns a missing-schema reset into a no-op drop +
        fresh clone — same outcome as a first-time provision. Don't surface the
        difference to the caller."""
        session = _mock_session()
        # No exception from either execute — the IF EXISTS branch returns
        # success at the DB layer.
        result = await reset_tenant(session, "lif-team")
        assert result == "tenant_lif_team"

    async def test_clone_failure_propagates_and_drop_rolls_back(self):
        """If the clone raises, we must NOT commit. The endpoint will surface
        a 500 and the prior tenant data stays intact via transaction rollback."""
        session = _mock_session()
        # First execute (drop) succeeds; second (clone) fails.
        orig = MagicMock(sqlstate="42P01", pgcode="42P01")  # undefined_table
        session.execute.side_effect = [None, DBAPIError("clone failed", {}, orig)]

        with pytest.raises(DBAPIError):
            await reset_tenant(session, "lif-team")
        session.commit.assert_not_awaited()
