"""Sanity checks for the bundled LIF data model schema.

``reference_data/schemas/lif-schema.json`` is the documented source of truth for
the LIF data model and is loaded by ``scripts/fix_sample_data_schema.py``, but
nothing at runtime parses it — so a syntax error can sit unnoticed on ``main``
(see #1207).
"""

import json
from pathlib import Path

SCHEMA = Path(__file__).resolve().parents[2] / "reference_data" / "schemas" / "lif-schema.json"


def test_lif_schema_is_valid_json_with_expected_credential_award_key():
    with SCHEMA.open(encoding="utf-8") as f:
        schema = json.load(f)

    credential_award = schema["components"]["schemas"]["Person"]["properties"]["CredentialAward"]["properties"]
    assert "InstanceOfRefCredential" in credential_award
