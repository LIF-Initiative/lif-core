import asyncio
import datetime as dt
import json
import os
import subprocess
import sys
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


def _import_core_in_subprocess(env: dict[str, str | None]) -> subprocess.CompletedProcess:
    """Import the base in a fresh interpreter and print the timeouts its config ended up with.

    The env reads happen at module import, so nothing in-process can cover the variable
    *names*: by the time any test runs, `core` is already in sys.modules holding whatever it
    parsed at collection time. CLAUDE.md forbids importlib.reload(), which leaves a fresh
    interpreter as the only way to pin them. Mutating either string literal in `core.py`
    fails the two happy-path tests below.

    A `None` value removes that variable from the child's environment; everything else is
    inherited, which is how the child picks up the information-sources path the sibling
    conftest.py sets.
    """
    child_env = dict(os.environ)
    for name, value in env.items():
        if value is None:
            child_env.pop(name, None)
        else:
            child_env[name] = value

    code = (
        "import json;"
        "from lif.query_planner_restapi import core;"
        "print(json.dumps([core.config.query_timeout_seconds, core.config.service_request_timeout_seconds]))"
    )
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=child_env, check=False)


def _parsed_timeouts(result: subprocess.CompletedProcess) -> list[int]:
    """Last stdout line only -- logging goes to stderr, but don't depend on that."""
    return json.loads(result.stdout.strip().splitlines()[-1])


class TestMyModule(unittest.TestCase):
    @patch.dict(os.environ, _ENV)
    def test_core(self):
        from lif.query_planner_restapi import core

        self.assertIsNotNone(core)


class TestQueryPlannerTimeoutEnvReads(unittest.TestCase):
    """That `core` reads these exact variable names, and what it does with a bad value.

    The previous version of this class asserted `core.config.query_timeout_seconds ==
    core.LIF_QUERY_TIMEOUT_SECONDS` -- one value built from the other -- and re-implemented
    `int(os.getenv(...))` inline without importing `core` at all. Renaming either variable
    in `core.py` left the whole suite green, so the defect this change fixes (config that
    nothing actually reads) could have silently reappeared.
    """

    def test_both_timeouts_are_read_from_their_env_vars(self):
        result = _import_core_in_subprocess(
            {"LIF_QUERY_TIMEOUT_SECONDS": "137", "LIF_SERVICE_REQUEST_TIMEOUT_SECONDS": "7"}
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(_parsed_timeouts(result), [137, 7])

    def test_unset_timeouts_fall_back_to_the_documented_defaults(self):
        result = _import_core_in_subprocess(
            {"LIF_QUERY_TIMEOUT_SECONDS": None, "LIF_SERVICE_REQUEST_TIMEOUT_SECONDS": None}
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(_parsed_timeouts(result), [300, 10])

    def test_malformed_timeout_stops_startup_and_names_the_variable(self):
        """#1179: fail fast and loud. Silently running on 300 when the operator set "120s"
        looks healthy while behaving differently from the configuration."""
        result = _import_core_in_subprocess({"LIF_QUERY_TIMEOUT_SECONDS": "120s"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("RuntimeError", result.stderr)
        self.assertIn("LIF_QUERY_TIMEOUT_SECONDS", result.stderr)
        self.assertIn("120s", result.stderr)

    def test_zero_timeout_stops_startup_before_pydantic_sees_it(self):
        """`gt=0` on LIFQueryPlannerConfig also rejects 0, but its message doesn't name the
        variable -- and 0 is a plausible operator reading of "no timeout"."""
        result = _import_core_in_subprocess({"LIF_SERVICE_REQUEST_TIMEOUT_SECONDS": "0"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("RuntimeError", result.stderr)
        self.assertIn("LIF_SERVICE_REQUEST_TIMEOUT_SECONDS", result.stderr)
        self.assertNotIn("ValidationError", result.stderr)


class TestEnvInt(unittest.TestCase):
    """`_env_int`'s branch table, in-process because it takes no import to exercise.

    Semantics are #1179's, adopted locally in the base pending the shared helper that issue
    will add.
    """

    def test_empty_value_falls_back_to_the_default(self):
        """A CloudFormation `Value:` entry yields "" when its source is missing. Treating that
        as fatal would make the service brittle to unrelated template changes."""
        from lif.query_planner_restapi import core

        with patch.dict(os.environ, {"X_TEST_TIMEOUT": ""}):
            self.assertEqual(core._env_int("X_TEST_TIMEOUT", 42), 42)

    def test_surrounding_whitespace_is_tolerated(self):
        from lif.query_planner_restapi import core

        with patch.dict(os.environ, {"X_TEST_TIMEOUT": " 55 "}):
            self.assertEqual(core._env_int("X_TEST_TIMEOUT", 42), 55)

    def test_value_at_the_minimum_is_accepted(self):
        from lif.query_planner_restapi import core

        with patch.dict(os.environ, {"X_TEST_TIMEOUT": "1"}):
            self.assertEqual(core._env_int("X_TEST_TIMEOUT", 42, minimum=1), 1)

    def test_below_minimum_raises_naming_the_variable(self):
        from lif.query_planner_restapi import core

        with patch.dict(os.environ, {"X_TEST_TIMEOUT": "0"}):
            with self.assertRaises(RuntimeError) as exc_info:
                core._env_int("X_TEST_TIMEOUT", 42, minimum=1)
        self.assertIn("X_TEST_TIMEOUT", str(exc_info.exception))

    def test_malformed_raises_runtime_error_not_the_bare_value_error(self):
        """The point is the message: `invalid literal for int()` doesn't name the variable."""
        from lif.query_planner_restapi import core

        with patch.dict(os.environ, {"X_TEST_TIMEOUT": "300s"}):
            with self.assertRaises(RuntimeError) as exc_info:
                core._env_int("X_TEST_TIMEOUT", 42)
        message = str(exc_info.exception)
        self.assertIn("X_TEST_TIMEOUT", message)
        self.assertIn("300s", message)


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
