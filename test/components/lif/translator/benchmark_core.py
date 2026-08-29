import pytest
from lif.translator.core import BaseTranslator, BaseTranslatorConfig

# ---------------------------------------------------------------------------
# Fixtures — reusable schemas, inputs, and mapping sets
# ---------------------------------------------------------------------------

SMALL_SOURCE_SCHEMA = {
    "type": "object",
    "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
    "required": ["name", "age"],
}

SMALL_TARGET_SCHEMA = {
    "type": "object",
    "properties": {"full_name": {"type": "string"}, "age_in_years": {"type": "integer"}},
    "required": ["full_name", "age_in_years"],
}

SMALL_INPUT = {"name": "John Doe", "age": 30}

SMALL_MAPPINGS = ['{ "full_name": name, "age_in_years": age }']

# Medium: employment preferences (mirrors existing test data)
MEDIUM_SOURCE_SCHEMA = {"type": "object"}
MEDIUM_TARGET_SCHEMA = {"type": "object"}

MEDIUM_INPUT = {
    "person": {
        "id": "100001",
        "employment": {
            "preferences": {
                "id": "employment-preferences-100001-001",
                "preferred_org_types": ["Public Sector", "Private Sector"],
                "preferred_org_names": ["Government Agencies", "Technology Companies"],
            }
        },
    }
}

MEDIUM_MAPPINGS = [
    '{ "Person": [{ "EmploymentPreferences": [{ "identifier": person.employment.preferences.id }] }] }',
    '{ "Person": [{ "EmploymentPreferences": [{ "organizationTypes": person.employment.preferences.preferred_org_types }] }] }',
    '{ "Person": [{ "EmploymentPreferences": [{ "organizationNames": person.employment.preferences.preferred_org_names }] }] }',
]

# Large: OpenBadge credential (mirrors existing test data, 9 mappings)
LARGE_SOURCE_SCHEMA = {"type": "object"}
LARGE_TARGET_SCHEMA = {"type": "object"}

LARGE_INPUT = {
    "OpenBadgeCredential": {
        "@context": [
            "https://www.w3.org/ns/credentials/v2",
            "https://purl.imsglobal.org/spec/ob/v3p0/context-3.0.3.json",
            "https://purl.imsglobal.org/spec/ob/v3p0/extensions.json",
        ],
        "id": "http://1edtech.edu/credentials/3732",
        "type": ["VerifiableCredential", "OpenBadgeCredential"],
        "name": "1EdTech University Degree for Example Student",
        "description": "1EdTech University Degree Description",
        "image": {
            "id": "https://1edtech.edu/credentials/3732/image",
            "type": "Image",
            "caption": "1EdTech University Degree for Example Student",
        },
        "credentialSubject": {"id": "did:example:ebfeb1f712ebc6f1c276e12ec21", "type": ["AchievementSubject"]},
        "issuer": {"id": "https://1edtech.edu/issuers/565049", "type": ["Profile"], "name": "1EdTech University"},
    }
}

LARGE_MAPPINGS = [
    '{ "Credential": OpenBadgeCredential.{ "format": [ ($lookup($, "@context") ? $lookup($, "@context") : [])[], (type ? type : [])[] ] } }',
    '{ "Person": OpenBadgeCredential. { "CredentialAward": [{ "id": id }] } }',
    '{ "Credential": OpenBadgeCredential. { "name": name } }',
    '{ "Credential": OpenBadgeCredential. { "description": description } }',
    '{ "Credential": OpenBadgeCredential. { "Image": [{ "imageId": image.id }] } }',
    '{ "Credential": OpenBadgeCredential. { "Image": [{ "imageType": image.type }] } }',
    '{ "Credential": OpenBadgeCredential. { "Image": [{ "caption": image.caption }] } }',
    '{ "Person": OpenBadgeCredential. { "Identifier": [{ "identifier": credentialSubject.id }] } }',
    '{ "Person": OpenBadgeCredential. { "Identifier": [{ "identifierType": credentialSubject.type }] } }',
]


def _make_translator(source_schema, target_schema, mappings):
    config = BaseTranslatorConfig(source_schema=source_schema, target_schema=target_schema, mappings=mappings)
    return BaseTranslator(config)


# ---------------------------------------------------------------------------
# Benchmarks — run with: pytest --benchmark-only
# ---------------------------------------------------------------------------


def test_bench_small(benchmark):
    """2-field doc, 1 mapping — baseline overhead."""
    translator = _make_translator(SMALL_SOURCE_SCHEMA, SMALL_TARGET_SCHEMA, SMALL_MAPPINGS)
    benchmark(translator.run, SMALL_INPUT)


def test_bench_medium(benchmark):
    """Employment preferences doc, 3 mappings."""
    translator = _make_translator(MEDIUM_SOURCE_SCHEMA, MEDIUM_TARGET_SCHEMA, MEDIUM_MAPPINGS)
    benchmark(translator.run, MEDIUM_INPUT)


def test_bench_large(benchmark):
    """OpenBadge credential doc, 9 mappings."""
    translator = _make_translator(LARGE_SOURCE_SCHEMA, LARGE_TARGET_SCHEMA, LARGE_MAPPINGS)
    benchmark(translator.run, LARGE_INPUT)


@pytest.mark.parametrize("num_mappings", [1, 5, 10, 20, 50])
def test_bench_scaling(benchmark, num_mappings):
    """Varying number of mappings to measure per-mapping marginal cost."""
    expr = '{ "Person": [{ "EmploymentPreferences": [{ "identifier": person.employment.preferences.id }] }] }'
    mappings = [expr] * num_mappings
    translator = _make_translator(MEDIUM_SOURCE_SCHEMA, MEDIUM_TARGET_SCHEMA, mappings)
    benchmark(translator.run, MEDIUM_INPUT)
