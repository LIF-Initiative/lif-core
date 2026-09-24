import asyncio
import datetime as dt
import json
import logging
import os
import subprocess
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException, Response

from lif.datatypes import (
    LIFPersonIdentifier,
    LIFPersonIdentifiers,
    LIFQuery,
    LIFQueryFilter,
    LIFQueryPersonFilter,
    LIFQueryStatusResponse,
    LIFRecord,
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

    class _ManualClock:
        """A clock the mocks move, so elapsed time reflects what the handler actually did.

        The fixed-sequence _fake_clock above cannot tell these cases apart: moving
        start_time across the first run_query does not change how many times now() is
        called, only when. Letting run_query and sleep advance the clock does.
        """

        def __init__(self, start):
            self.current = start

        def now(self, tz=None):
            return self.current

        def advance(self, seconds):
            self.current += dt.timedelta(seconds=seconds)

    def test_first_run_query_counts_against_the_budget(self):
        """The cache read and orchestrator submission are inside the budget, not free (#571).

        start_time used to be taken *after* the first run_query, so both round trips sat
        outside the ceiling -- the request could exceed the 150s ALB idle timeout while the
        polling loop still believed it was within budget.

        The 408 alone does not pin this: with start_time taken late the loop still times
        out, just 20s later, after burning the whole budget in sleeps. What separates the
        two is that a budget already spent before the loop starts must produce *no* sleep
        at all, so that is what is asserted.
        """
        from lif.query_planner_restapi import core

        pending = LIFQueryStatusResponse(query_id="123", status="PENDING")
        clock = self._ManualClock(dt.datetime(2026, 1, 1, 12, 0, 0))
        slept: list[float] = []

        async def slow_run_query(*args, **kwargs):
            clock.advance(30)  # cache POST + orchestrator POST
            return pending

        async def recording_sleep(seconds):
            slept.append(seconds)
            clock.advance(seconds)

        async def _run():
            with (
                patch.object(core.config, "query_timeout_seconds", 20),
                patch.object(core.service, "run_query", AsyncMock(side_effect=slow_run_query)),
                patch.object(core.service, "get_query_status", AsyncMock(return_value=pending)),
                patch.object(core, "datetime", clock),
                patch.object(core, "sleep", new=recording_sleep),
            ):
                return await core.do_run_query_sync(query=_make_query(), response=MagicMock())

        with self.assertRaises(HTTPException) as exc_info:
            asyncio.run(_run())
        self.assertEqual(exc_info.exception.status_code, 408)
        self.assertEqual(slept, [])

    def test_polling_sleep_is_clamped_to_the_remaining_budget(self):
        """The loop must not sleep past its own deadline (#571).

        The check sits at the top of the loop, so an unclamped sleep overshoots by up to a
        whole MAX_POLLING_DELAY_SECONDS before the next check can fire. With a 10s budget the
        unclamped backoff sleeps 1+2+4+8 = 15s, blowing the budget by half again.
        """
        from lif.query_planner_restapi import core

        pending = LIFQueryStatusResponse(query_id="123", status="PENDING")
        clock = self._ManualClock(dt.datetime(2026, 1, 1, 12, 0, 0))
        slept: list[float] = []

        async def recording_sleep(seconds):
            slept.append(seconds)
            clock.advance(seconds)

        async def _run():
            with (
                patch.object(core.config, "query_timeout_seconds", 10),
                patch.object(core.service, "run_query", AsyncMock(return_value=pending)),
                patch.object(core.service, "get_query_status", AsyncMock(return_value=pending)),
                patch.object(core, "datetime", clock),
                patch.object(core, "sleep", new=recording_sleep),
            ):
                return await core.do_run_query_sync(query=_make_query(), response=MagicMock())

        with self.assertRaises(HTTPException) as exc_info:
            asyncio.run(_run())
        self.assertEqual(exc_info.exception.status_code, 408)
        # Exponential backoff 1, 2, 4, then 3 rather than 8 -- the deadline, not the curve.
        self.assertEqual(slept, [1, 2, 4, 3])
        self.assertEqual(sum(slept), 10)

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


# -------------------------------------------------------------------------
# #1269 — person data must never reach the logs.
# -------------------------------------------------------------------------
def _sentinel_query() -> LIFQuery:
    return LIFQuery(
        filter=LIFQueryFilter(
            root=LIFQueryPersonFilter(
                person=LIFPersonIdentifiers(
                    Identifier=LIFPersonIdentifier(identifier="Sentinel-1234", identifierType="School-assigned number")
                )
            )
        ),
        selected_fields=["person.name"],
    )


def _sentinel_record() -> LIFRecord:
    return LIFRecord.model_validate(
        {
            "person": [
                {
                    "identifier": [{"identifier": "Sentinel-1234", "identifierType": "School-assigned number"}],
                    "name": [{"givenName": ["Bellwether"], "familyName": "Canary"}],
                }
            ]
        }
    )


@patch.dict(os.environ, _ENV)
def test_sync_query_endpoint_does_not_log_returned_records(caplog):
    from lif.query_planner_restapi import core

    mock_service = AsyncMock()
    mock_service.run_query.side_effect = [
        LIFQueryStatusResponse(query_id="run-1", status="COMPLETED"),
        [_sentinel_record()],
    ]

    with patch.object(core, "service", mock_service), caplog.at_level(logging.DEBUG):
        asyncio.run(core.do_run_query_sync(_sentinel_query(), Response()))

    assert "Canary" not in caplog.text
    assert "Bellwether" not in caplog.text
    assert "Sentinel" not in caplog.text
    # The line still reports that the query completed, and with how many records.
    assert "Query completed successfully" in caplog.text


@patch.dict(os.environ, _ENV)
def test_async_query_endpoint_does_not_log_returned_records(caplog):
    from lif.query_planner_restapi import core

    mock_service = AsyncMock()
    mock_service.run_query.return_value = [_sentinel_record()]

    with patch.object(core, "service", mock_service), caplog.at_level(logging.DEBUG):
        asyncio.run(core.do_run_query(_sentinel_query(), Response()))

    assert "Canary" not in caplog.text
    assert "Bellwether" not in caplog.text
    assert "Sentinel" not in caplog.text
    assert "Query completed successfully" in caplog.text


# -------------------------------------------------------------------------
# #1272 — the optional X-LIF-Client header, through the real HTTP layer.
# -------------------------------------------------------------------------
_FULL_CACHE_RECORD = {"person": [{"name": [{"givenName": ["John"], "familyName": "Doe"}]}]}


def _statistics_events(caplog) -> list:
    from lif.query_planner_service import statistics

    prefix = statistics.QUERY_STATISTICS_PREFIX + " "
    return [json.loads(line[line.index(prefix) + len(prefix) :]) for line in caplog.text.splitlines() if prefix in line]


def _post_query(path: str, headers: dict, caplog) -> tuple[int, list]:
    """POST a query through the app with the real service; only the planner's own outbound calls are faked."""
    from fastapi.testclient import TestClient

    from lif.query_planner_restapi import core

    cache_response = MagicMock(status_code=200)
    cache_response.json.return_value = [_FULL_CACHE_RECORD]
    cache_response.raise_for_status.return_value = None
    body = _make_query().model_dump(mode="json", by_alias=True)
    with patch("httpx.AsyncClient.post", AsyncMock(return_value=cache_response)), caplog.at_level(logging.INFO):
        response = TestClient(core.app).post(path, json=body, headers=headers)
    return response.status_code, _statistics_events(caplog)


@patch.dict(os.environ, _ENV)
def test_query_without_the_client_header_succeeds_and_still_emits_statistics(caplog):
    for path in ["/query", "/query_async"]:
        caplog.clear()
        status_code, events = _post_query(path, {}, caplog)
        assert status_code == 200, path
        assert [e["client"] for e in events] == ["unknown"], path


@patch.dict(os.environ, _ENV)
def test_query_records_the_client_header(caplog):
    for path in ["/query", "/query_async"]:
        caplog.clear()
        status_code, events = _post_query(path, {"X-LIF-Client": "learner-data-export"}, caplog)
        assert status_code == 200, path
        assert [e["client"] for e in events] == ["learner-data-export"], path
