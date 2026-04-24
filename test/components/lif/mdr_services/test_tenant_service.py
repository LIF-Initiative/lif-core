"""Unit tests for tenant_service — the thin wrapper over clone_lif_schema."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import DBAPIError

from lif.mdr_services.tenant_service import (
    DUPLICATE_SCHEMA_SQLSTATE,
    InvalidGroupNameError,
    TenantAlreadyExistsError,
    provision_tenant,
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
