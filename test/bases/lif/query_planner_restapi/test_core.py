import asyncio
import datetime as dt
import importlib
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
    @patch.dict(os.environ, _ENV, clear=True)
    def test_default_query_timeout_when_env_absent(self):
        core = importlib.import_module("lif.query_planner_restapi.core")
        importlib.reload(core)
        self.assertEqual(core.DEFAULT_QUERY_TIMEOUT_SECONDS, 300)
        self.assertEqual(core.LIF_QUERY_TIMEOUT_SECONDS, 300)
        self.assertEqual(core.config.query_timeout_seconds, 300)

    @patch.dict(os.environ, {**_ENV, "LIF_QUERY_TIMEOUT_SECONDS": "42"}, clear=True)
    def test_query_timeout_reads_env_var(self):
        core = importlib.import_module("lif.query_planner_restapi.core")
        importlib.reload(core)
        self.assertEqual(core.LIF_QUERY_TIMEOUT_SECONDS, 42)
        self.assertEqual(core.config.query_timeout_seconds, 42)


class TestQueryPlannerSyncQueryTimeout(unittest.TestCase):
    def test_sync_query_polls_past_timeout_and_returns_408(self):
        from lif.query_planner_restapi import core

        # Set a small timeout so the test does not wait on real orchestration.
        core.config.query_timeout_seconds = 5
        pending = LIFQueryStatusResponse(query_id="123", status="PENDING")
        core.service.run_query = AsyncMock(return_value=pending)
        core.service.get_query_status = AsyncMock(return_value=pending)

        # One datetime.now() for start_time, then one per polling-loop timeout check.
        clock = iter(
            [
                dt.datetime(2026, 1, 1, 12, 0, 0),  # start_time
                dt.datetime(2026, 1, 1, 12, 0, 3),  # first check: 3s elapsed (not past 5s)
                dt.datetime(2026, 1, 1, 12, 0, 59),  # second check: 59s elapsed (past 5s)
            ]
        )

        class FakeDateTime:
            @staticmethod
            def now(tz=None):
                return next(clock)

        async def _run():
            with (
                patch.object(core, "datetime", FakeDateTime),
                patch.object(core, "sleep", new=AsyncMock(return_value=None)),
            ):
                return await core.do_run_query_sync(query=_make_query(), response=MagicMock())

        with self.assertRaises(HTTPException) as exc_info:
            asyncio.run(_run())
        self.assertEqual(exc_info.exception.status_code, 408)

    def test_sync_query_returns_records_when_cache_is_complete(self):
        from lif.query_planner_restapi import core

        cached_records = [{"Person": [{"Name": ["Doe"]}]}]
        core.service.run_query = AsyncMock(return_value=cached_records)

        async def _run():
            return await core.do_run_query_sync(query=_make_query(), response=MagicMock())

        results = asyncio.run(_run())
        self.assertEqual(results, cached_records)
