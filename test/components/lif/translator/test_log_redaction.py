"""
The Translator keeps learner values out of its per-mapping WARNINGs (#1351).

JSONata and jsonschema both quote the offending value in their error text, and a skipped
non-object fragment *is* a learner value. Each test plants one, asserts the WARNING fired, and
asserts the value appears nowhere in the captured output.
"""

import logging

from lif.translator import core

FIELD_VALUE = "SENTINEL-ID-4471"
LOGGER = "lif.translator.core"


def _run(caplog, mappings, target_schema=None):
    config = core.BaseTranslatorConfig(
        source_schema={"type": "object"}, target_schema=target_schema or {"type": "object"}, mappings=mappings
    )
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        core.BaseTranslator(config).run({"name": FIELD_VALUE})


def test_evaluation_error_logs_no_learner_value(caplog):
    # $number() on a non-numeric string raises "could not convert string to float: '<value>'".
    _run(caplog, ['{ "x": $number(name) }'])
    assert "Skipping mapping due to evaluation error" in caplog.text
    assert FIELD_VALUE not in caplog.text


def test_non_object_fragment_logs_no_learner_value(caplog):
    _run(caplog, ["name"])
    assert "Skipping non-object fragment" in caplog.text
    assert FIELD_VALUE not in caplog.text


def test_target_schema_violation_logs_path_not_value(caplog):
    # jsonschema's message is "'<value>' is not of type 'integer'"; the path and validator are enough.
    _run(caplog, ['{ "x": name }'], {"type": "object", "properties": {"x": {"type": "integer"}}})
    assert "Discarding fragment due to target schema violation" in caplog.text
    assert "$.x" in caplog.text
    assert FIELD_VALUE not in caplog.text
