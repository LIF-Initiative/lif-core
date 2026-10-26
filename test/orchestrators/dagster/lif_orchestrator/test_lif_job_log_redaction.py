"""
The Dagster LIF job keeps learner data out of its logs, step keys and stored errors (#1359, #1407).

Dagster stores every ``context.log`` message in its event log as well as printing it, a dynamic
output's mapping key becomes part of each step key, and an exception raised out of an op is stored
with its message in Dagster's own step events, so all three are checked here.

The orchestrator is its own uv project, not a Polylith brick, so the root environment can't import
it and its own ``tests/`` don't run in CI (#1341). Its source is added to ``sys.path`` instead; the
root environment already has the Dagster version it pins.
"""

import sys
from pathlib import Path
from unittest import mock

import dagster as dg
import pytest
import requests

from lif.data_source_adapters import _EXTERNAL_ADAPTERS, ADAPTER_REGISTRY

sys.path.insert(0, str(Path(__file__).parents[4] / "orchestrators/dagster/lif-orchestrator/src"))

# lif_job registers the demo adapters when imported. Undo that, so the session's registries stay
# as the demo_data_source_adapters tests expect; the tests here stub the adapter lookup anyway.
_registry, _external = dict(ADAPTER_REGISTRY), dict(_EXTERNAL_ADAPTERS)
from lif_orchestrator.defs import lif_job  # noqa: E402

ADAPTER_REGISTRY.clear()
ADAPTER_REGISTRY.update(_registry)
_EXTERNAL_ADAPTERS.clear()
_EXTERNAL_ADAPTERS.update(_external)

PERSON_ID = "SENTINEL_ID_4471"  # key-safe, so main fails on the leak and not on the key
SOURCE_VALUE = "SENTINEL-SOURCE-Marigold"
TRANSLATED_VALUE = "SENTINEL-TRANSLATED-Juniper"
ERROR_TEXT = "SENTINEL-ERROR-Larkspur"
SENTINELS = (PERSON_ID, SOURCE_VALUE, TRANSLATED_VALUE, ERROR_TEXT)


def _part(information_source_id="src1", person_id=PERSON_ID):
    return {
        "information_source_id": information_source_id,
        "adapter_id": "lif-to-lif",
        "person_id": {"identifier": person_id, "identifierType": "School-assigned number"},
        "lif_fragment_paths": ["Person.Name"],
        "translation": {"source_schema_id": "26", "target_schema_id": "17"},
    }


def _response(ok=True, body=None, text=""):
    response = mock.Mock(ok=ok, status_code=200 if ok else 400, text=text)
    response.json.return_value = body
    if not ok:
        response.raise_for_status.side_effect = RuntimeError(ERROR_TEXT)
    return response


def _run(monkeypatch, parts, adapter_run, translator_response, callback_response):
    adapter = mock.Mock()
    adapter.run.side_effect = adapter_run
    monkeypatch.setattr(lif_job, "get_adapter_by_id", lambda *args, **kwargs: adapter)
    monkeypatch.setattr(lif_job, "get_credentials_for_adapter", lambda *args: {})

    def post(url, **kwargs):
        return callback_response if url.endswith("/orchestration/results") else translator_response

    monkeypatch.setattr(lif_job.requests, "post", post)

    job = lif_job.dynamic_pipeline_graph.to_job(
        executor_def=dg.in_process_executor,
        resource_defs={"config_resource": lif_job.SharedOpConfig(lif_query_plan_parts=parts)},
    )
    instance = dg.DagsterInstance.ephemeral()
    result = job.execute_in_process(instance=instance, raise_on_error=False)
    return instance.all_logs(result.run_id)


def _stored(entries) -> str:
    # Every entry as Dagster stores it, including the error info in its own step events.
    return "\n".join(dg.serialize_value(entry) for entry in entries)


def _assert_no_learner_data(entries, capfd):
    stored = _stored(entries)
    step_keys = [entry.step_key for entry in entries if entry.step_key]
    printed = capfd.readouterr()
    for sentinel in SENTINELS:
        assert sentinel not in stored, sentinel
        assert not [k for k in step_keys if sentinel in k], sentinel
        assert sentinel not in printed.out + printed.err, sentinel


def test_successful_run_logs_no_learner_data(monkeypatch, capfd):
    # Two parts for the same source take the "Multiple results found" path too.
    entries = _run(
        monkeypatch,
        parts=[_part(), _part(person_id=PERSON_ID + "_2")],
        adapter_run=lambda: {"Person": {"Name": [{"firstName": SOURCE_VALUE}]}},
        translator_response=_response(body={"Person": [{"Name": [{"firstName": TRANSLATED_VALUE}]}]}),
        callback_response=_response(),
    )

    messages = "\n".join(entry.user_message for entry in entries)
    assert "Multiple results found" in messages
    assert "Final Orchestrator Job Results" in messages
    _assert_no_learner_data(entries, capfd)


def test_failed_translation_and_callback_log_no_learner_data(monkeypatch, capfd):
    entries = _run(
        monkeypatch,
        parts=[_part()],
        adapter_run=lambda: {"Person": {"Name": [{"firstName": SOURCE_VALUE}]}},
        translator_response=_response(ok=False, text=f'{{"detail": "{SOURCE_VALUE}"}}'),
        callback_response=_response(ok=False, text=f'{{"detail": "{TRANSLATED_VALUE}"}}'),
    )

    messages = "\n".join(entry.user_message for entry in entries)
    assert "run_translation failed" in messages
    assert "Response 400" in messages
    _assert_no_learner_data(entries, capfd)


def test_failed_adapter_logs_no_learner_data(monkeypatch, capfd):
    def fail():
        raise ValueError(f"bad record for {PERSON_ID}: {SOURCE_VALUE}")

    entries = _run(
        monkeypatch, parts=[_part()], adapter_run=fail, translator_response=_response(), callback_response=_response()
    )

    assert "run_lif_adapter failed" in "\n".join(entry.user_message for entry in entries)
    _assert_no_learner_data(entries, capfd)


def test_invalid_query_plan_part_stores_no_learner_data(monkeypatch, capfd):
    # Pydantic's message quotes the input, which holds the person identifier.
    part = _part()
    del part["lif_fragment_paths"]

    entries = _run(
        monkeypatch, parts=[part], adapter_run=dict, translator_response=_response(), callback_response=_response()
    )

    assert "create_dynamic_pipelines failed: ValidationError" in _stored(entries)
    _assert_no_learner_data(entries, capfd)


def test_failed_callback_keeps_its_http_status(monkeypatch, capfd):
    callback = _response(ok=False)
    callback.raise_for_status.side_effect = requests.HTTPError(
        f"503 Server Error for url: https://qp.example/{PERSON_ID}", response=mock.Mock(status_code=503)
    )

    entries = _run(
        monkeypatch,
        parts=[_part()],
        adapter_run=lambda: {"Person": {"Name": [{"firstName": SOURCE_VALUE}]}},
        translator_response=_response(body={"Person": [{"Name": [{"firstName": TRANSLATED_VALUE}]}]}),
        callback_response=callback,
    )

    assert "send_results_to_query_planner failed: HTTPError 503" in _stored(entries)
    _assert_no_learner_data(entries, capfd)


@pytest.mark.parametrize("person_id", ["100001", "100002"])
def test_mapping_key_leaves_out_the_person_identifier(person_id):
    key = lif_job.generate_mapping_key(_part(person_id=person_id), index=0)

    assert person_id not in key
    assert key.startswith("lif_to_lif__src1__0__")
