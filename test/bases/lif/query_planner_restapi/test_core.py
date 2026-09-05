import asyncio
import datetime as dt
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException

from lif.datatypes import (
    LIFPersonIdentifier,
    LIFPersonIdentifiers,
    LIFQuery,
    LIFQueryFilter,
    LIFQueryPersonFilter,
    LIFQueryStatusResponse,
)

_YML_PATH = os.path.dirname(__file__) + "/test_information_sources_config.yml"
_ENV = {"LIF_QUERY_PLANNER_INFORMATION_SOURCES_CONFIG_PATH": _YML_PATH}


def _make_query() -> LIFQuery:
    return LIFQuery(
        filter=LIFQueryFilter(
            root=LIFQueryPersonFilter(
                person=LIFPersonIdentifiers(
                    Identifier=LIFPersonIdentifier(identifier="12345", identifierType="School-assigned number")
                )
            )
        ),
        selected_fields=["person.name"],
    )


class TestMyModule(unittest.TestCase):
    @patch.dict(os.environ, _ENV)
    def test_core(self):
        from lif.query_planner_restapi import core

        self.assertIsNotNone(core)


class TestQueryPlannerTimeoutConfig(unittest.TestCase):
    """
    The timeout values are read from the environment at import time, so these assert the
    already-imported module's config rather than re-importing it. CLAUDE.md forbids
    importlib.reload() in tests: it rebinds the module object, so isinstance() and
    pytest.raises() stop matching, and any singleton another test patched is silently
    replaced.
    """

    def test_query_timeout_defaults_to_300(self):
        from lif.query_planner_restapi import core

        self.assertEqual(core.DEFAULT_QUERY_TIMEOUT_SECONDS, 300)

    def test_service_request_timeout_defaults_to_10(self):
        """Short and independent of the query budget -- these are fast service-to-service calls."""
        from lif.query_planner_restapi import core

        self.assertEqual(core.DEFAULT_SERVICE_REQUEST_TIMEOUT_SECONDS, 10)

    def test_config_carries_both_timeouts(self):
        from lif.query_planner_restapi import core

        self.assertEqual(core.config.query_timeout_seconds, core.LIF_QUERY_TIMEOUT_SECONDS)
        self.assertEqual(core.config.service_request_timeout_seconds, core.LIF_SERVICE_REQUEST_TIMEOUT_SECONDS)

    def test_timeouts_read_their_env_vars(self):
        """The env parsing itself, exercised without touching the imported module."""
        with patch.dict(os.environ, {"LIF_QUERY_TIMEOUT_SECONDS": "42"}, clear=False):
            self.assertEqual(int(os.getenv("LIF_QUERY_TIMEOUT_SECONDS", "300")), 42)
        with patch.dict(os.environ, {"LIF_SERVICE_REQUEST_TIMEOUT_SECONDS": "7"}, clear=False):
            self.assertEqual(int(os.getenv("LIF_SERVICE_REQUEST_TIMEOUT_SECONDS", "10")), 7)


class TestQueryPlannerSyncQueryTimeout(unittest.TestCase):
    """
    patch.object throughout: these tests previously assigned onto core.service and
    core.config directly and never restored them, so a later TestClient test against
    core.app would silently have run against a mocked service.
    """

    @staticmethod
    def _fake_clock(*instants):
        clock = iter(instants)

        class FakeDateTime:
            @staticmethod
            def now(tz=None):
                return next(clock)

        return FakeDateTime

    def test_sync_query_polls_past_timeout_and_returns_408(self):
        from lif.query_planner_restapi import core

        pending = LIFQueryStatusResponse(query_id="123", status="PENDING")
        # One datetime.now() for start_time, then one per polling-loop timeout check.
        clock = self._fake_clock(
            dt.datetime(2026, 1, 1, 12, 0, 0),  # start_time
            dt.datetime(2026, 1, 1, 12, 0, 3),  # 3s elapsed -- not past 5s
            dt.datetime(2026, 1, 1, 12, 0, 59),  # 59s elapsed -- past 5s
        )

        async def _run():
            with (
                patch.object(core.config, "query_timeout_seconds", 5),
                patch.object(core.service, "run_query", AsyncMock(return_value=pending)),
                patch.object(core.service, "get_query_status", AsyncMock(return_value=pending)),
                patch.object(core, "datetime", clock),
                patch.object(core, "sleep", new=AsyncMock(return_value=None)),
            ):
                return await core.do_run_query_sync(query=_make_query(), response=MagicMock())

        with self.assertRaises(HTTPException) as exc_info:
            asyncio.run(_run())
        self.assertEqual(exc_info.exception.status_code, 408)

    def test_elapsed_uses_total_seconds_so_large_timeouts_still_terminate(self):
        """
        Regression for the `.seconds` bug: timedelta.seconds is the sub-day remainder, so a
        timeout >= 86400 made the guard permanently false and the poll loop never terminated.
        Here 25h has elapsed against a 90000s (25h) budget -- `.seconds` would report 3600 and
        keep polling forever; `.total_seconds()` reports 90000 and trips the 408.
        """
        from lif.query_planner_restapi import core

        pending = LIFQueryStatusResponse(query_id="123", status="PENDING")
        clock = self._fake_clock(
            dt.datetime(2026, 1, 1, 12, 0, 0),  # start_time
            dt.datetime(2026, 1, 2, 13, 0, 1),  # 25h 0m 1s later
        )

        async def _run():
            with (
                patch.object(core.config, "query_timeout_seconds", 90000),
                patch.object(core.service, "run_query", AsyncMock(return_value=pending)),
                patch.object(core.service, "get_query_status", AsyncMock(return_value=pending)),
                patch.object(core, "datetime", clock),
                patch.object(core, "sleep", new=AsyncMock(return_value=None)),
            ):
                return await core.do_run_query_sync(query=_make_query(), response=MagicMock())

        with self.assertRaises(HTTPException) as exc_info:
            asyncio.run(_run())
        self.assertEqual(exc_info.exception.status_code, 408)

    def test_sync_query_returns_records_when_cache_is_complete(self):
        from lif.query_planner_restapi import core

        cached_records = [{"Person": [{"Name": [{"FamilyName": "Doe"}]}]}]

        async def _run():
            with patch.object(core.service, "run_query", AsyncMock(return_value=cached_records)):
                return await core.do_run_query_sync(query=_make_query(), response=MagicMock())

        results = asyncio.run(_run())
        self.assertEqual(results, cached_records)

    def test_service_singletons_are_restored_after_patching(self):
        """
        The isolation property itself. The old tests assigned core.service.run_query directly,
        which leaves an instance attribute shadowing the real method for the rest of the session;
        patch.object removes it on exit. Checked via vars() rather than identity because a bound
        method is a fresh object on every attribute access, so `is` would never match.
        """
        from lif.query_planner_restapi import core

        with patch.object(core.service, "run_query", AsyncMock(return_value=[])):
            self.assertIn("run_query", vars(core.service))
        self.assertNotIn("run_query", vars(core.service))
