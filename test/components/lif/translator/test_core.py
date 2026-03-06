from lif.translator import core
import pytest


def test_sample():
    assert core is not None


def test_base_translator_config():
    config = core.BaseTranslatorConfig(source_schema={"type": "object"}, target_schema={"type": "object"}, mappings=[])
    assert config.source_schema == {"type": "object"}
    assert config.target_schema == {"type": "object"}
    assert config.mappings == []


def test_translator_config():
    config = core.TranslatorConfig(source_schema_id="source_id", target_schema_id="target_id")
    translator = core.Translator(config)
    assert translator is not None
    assert translator.source_schema_id == "source_id"
    assert translator.target_schema_id == "target_id"


def test_base_translator_run():
    source_schema = {
        "type": "object",
        "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
        "required": ["name", "age"],
    }
    target_schema = {
        "type": "object",
        "properties": {"full_name": {"type": "string"}, "age_in_years": {"type": "integer"}},
        "required": ["full_name", "age_in_years"],
    }
    mappings = ['{ "full_name": name, "age_in_years": age }']
    config = core.BaseTranslatorConfig(source_schema=source_schema, target_schema=target_schema, mappings=mappings)
    translator = core.BaseTranslator(config)
    input_data = {"name": "John Doe", "age": 30}
    result = translator.run(input_data)
    assert result == {"full_name": "John Doe", "age_in_years": 30}


def test_base_translator_skips_non_object_fragments():
    # Source schema: allow any object
    source_schema = {"type": "object"}
    # Target schema: allow object with optional integer x
    target_schema = {"type": "object", "properties": {"x": {"type": "integer"}}, "additionalProperties": True}
    # First mapping returns a scalar (should be skipped); second returns an object
    mappings = [
        "1",  # scalar fragment -> skipped
        '{ "x": 2 }',  # valid object fragment -> merged
    ]
    config = core.BaseTranslatorConfig(source_schema=source_schema, target_schema=target_schema, mappings=mappings)
    translator = core.BaseTranslator(config)
    result = translator.run({})
    assert result == {"x": 2}


def test_base_translator_skips_mapping_on_evaluation_error():
    source_schema = {"type": "object"}
    target_schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}}
    mappings = [
        "$.totallyUndefined()",  # invalid function -> evaluation error -> skipped
        '{ "ok": true }',  # valid
    ]
    config = core.BaseTranslatorConfig(source_schema=source_schema, target_schema=target_schema, mappings=mappings)
    translator = core.BaseTranslator(config)
    result = translator.run({})
    assert result == {"ok": True}


def test_base_translator_rollback_on_target_schema_violation():
    # Target schema requires that y is a string if present
    source_schema = {"type": "object"}
    target_schema = {
        "type": "object",
        "properties": {"x": {"type": "integer"}, "y": {"type": "string"}},
        "additionalProperties": False,
    }
    mappings = [
        '{ "x": 1 }',  # valid
        '{ "y": 123 }',  # invalid type for y -> should be rolled back
    ]
    # Use keyword arguments for Pydantic BaseModel (positional args are not supported in our Pydantic version)
    config = core.BaseTranslatorConfig(source_schema=source_schema, target_schema=target_schema, mappings=mappings)
    translator = core.BaseTranslator(config)
    result = translator.run({})
    assert result == {"x": 1}  # y should have been discarded


def test_base_translator_final_validation_failure():
    # Target schema requires property 'must'
    source_schema = {"type": "object"}
    target_schema = {
        "type": "object",
        "properties": {"must": {"type": "string"}},
        "required": ["must"],
        "additionalProperties": False,
    }
    # No mapping produces 'must' -> final validation should fail
    mappings = ['{ "other": 1 }']
    config = core.BaseTranslatorConfig(source_schema=source_schema, target_schema=target_schema, mappings=mappings)
    translator = core.BaseTranslator(config)
    with pytest.raises(ValueError) as exc:
        translator.run({})
    assert "does not conform" in str(exc.value)


# New test for Translator.run with employment preferences mapping
@pytest.mark.asyncio
async def test_translator_run_with_employment_preferences(monkeypatch):
    # Input data matching the r1_demo_data structure in example_data_source_rest_api/core.py
    input_data = {
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

    # Expected LIF output matching schemas/lif-schema.json EmploymentPreferences requirements
    expected = {
        "Person": [
            {
                "EmploymentPreferences": [
                    {
                        "identifier": "employment-preferences-100001-001",
                        "organizationTypes": ["Public Sector", "Private Sector"],
                        "organizationNames": ["Government Agencies", "Technology Companies"],
                    }
                ]
            }
        ]
    }

    # Transformation payload mimicking the MDR response
    # Maps source fields to LIF EmploymentPreferences fields:
    #   person.employment.preferences.id -> EmploymentPreferences.identifier
    #   person.employment.preferences.preferred_org_types -> EmploymentPreferences.organizationTypes
    #   person.employment.preferences.preferred_org_names -> EmploymentPreferences.organizationNames
    transformation_payload = {
        "total": 2,
        "page": 1,
        "size": 1000,
        "total_pages": 1,
        "next": None,
        "previous": None,
        "data": [
            {
                "TransformationGroupId": 26,
                "SourceDataModelId": 26,
                "TargetDataModelId": 17,
                "TransformationGroupName": "R1 Demo Source Data Model_StateU LIF",
                "TransformationGroupVersion": "1.0",
                "TransformationGroupDescription": None,
                "TransformationGroupNotes": None,
                "TransformationId": 1375,
                "TransformationExpression": '{ "Person": [{ "EmploymentPreferences": [{ "identifier": person.employment.preferences.id, "organizationTypes": person.employment.preferences.preferred_org_types, "organizationNames": person.employment.preferences.preferred_org_names }] }] }',
                "TransformationExpressionLanguage": "JSONata",
                "TransformationNotes": None,
                "TransformationAlignment": None,
                "TransformationCreationDate": None,
                "TransformationActivationDate": None,
                "TransformationDeprecationDate": None,
                "TransformationContributor": None,
                "TransformationContributorOrganization": None,
                "TransformationSourceAttributes": [
                    {
                        "AttributeId": 1896,
                        "EntityId": 377,
                        "AttributeName": "id",
                        "AttributeType": "Source",
                        "Notes": None,
                        "CreationDate": None,
                        "ActivationDate": None,
                        "DeprecationDate": None,
                        "Contributor": None,
                        "ContributorOrganization": None,
                        "EntityIdPath": "person.employment.preferences",
                    },
                    {
                        "AttributeId": 1895,
                        "EntityId": 377,
                        "AttributeName": "preferred_org_types",
                        "AttributeType": "Source",
                        "Notes": None,
                        "CreationDate": None,
                        "ActivationDate": None,
                        "DeprecationDate": None,
                        "Contributor": None,
                        "ContributorOrganization": None,
                        "EntityIdPath": "person.employment.preferences",
                    },
                    {
                        "AttributeId": 1897,
                        "EntityId": 377,
                        "AttributeName": "preferred_org_names",
                        "AttributeType": "Source",
                        "Notes": None,
                        "CreationDate": None,
                        "ActivationDate": None,
                        "DeprecationDate": None,
                        "Contributor": None,
                        "ContributorOrganization": None,
                        "EntityIdPath": "person.employment.preferences",
                    },
                ],
                "TransformationTargetAttribute": {
                    "AttributeId": 1876,
                    "EntityId": 359,
                    "AttributeName": "organizationTypes",
                    "AttributeType": "Target",
                    "Notes": None,
                    "CreationDate": None,
                    "ActivationDate": None,
                    "DeprecationDate": None,
                    "Contributor": None,
                    "ContributorOrganization": None,
                    "EntityIdPath": "Person.EmploymentPreferences",
                },
            }
        ],
    }

    # Monkeypatch Translator to return permissive schemas (accept anything)
    async def fake_fetch_schema(self, schema_id: str) -> dict:
        return {}

    # Monkeypatch Translator to return the MDR transformation payload above
    async def fake_fetch_transformation(self, source_schema_id: str, target_schema_id: str) -> dict:
        return transformation_payload

    monkeypatch.setattr(core.Translator, "_fetch_schema", fake_fetch_schema, raising=False)
    monkeypatch.setattr(core.Translator, "_fetch_transformation", fake_fetch_transformation, raising=False)

    # Configure IDs matching the transformation payload (26 -> 17)
    config = core.TranslatorConfig(source_schema_id="26", target_schema_id="17")
    translator = core.Translator(config)

    # Run the async translator and check the result
    result = await translator.run(input_data)
    assert result == expected


@pytest.mark.asyncio
async def test_translator_fetch_schema_calls_client(monkeypatch):
    # Arrange
    async def fake_get_schema(schema_id: str, include_attr_md: bool, include_entity_md: bool):
        return {"id": schema_id, "ok": True}

    monkeypatch.setattr(core, "get_data_model_schema", fake_get_schema, raising=True)

    t = core.Translator(core.TranslatorConfig(source_schema_id="S", target_schema_id="T"))

    # Act
    res = await t._fetch_schema("S")

    # Assert
    assert res == {"id": "S", "ok": True}


@pytest.mark.asyncio
async def test_translator_fetch_transformation_calls_client(monkeypatch):
    async def fake_get_xform(source_schema_id: str, target_schema_id: str):
        return {"pair": [source_schema_id, target_schema_id]}

    monkeypatch.setattr(core, "get_data_model_transformation", fake_get_xform, raising=True)

    t = core.Translator(core.TranslatorConfig(source_schema_id="A", target_schema_id="B"))
    res = await t._fetch_transformation("A", "B")
    assert res == {"pair": ["A", "B"]}


# Test for OpenBadgeCredential -> LIF Credential/Person mapping (transformation 16->17)
@pytest.mark.asyncio
async def test_translator_run_with_openbadgecredential(monkeypatch):
    # Input OpenBadgeCredential per prompt
    input_data = {
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
            "credentialSubject": {
                "id": "did:example:ebfeb1f712ebc6f1c276e12ec21",
                "type": ["AchievementSubject"],
                "activityEndDate": "2010-01-02T00:00:00Z",
                "activityStartDate": "2010-01-01T00:00:00Z",
                "creditsEarned": 42.0,
                "role": "Major Domo",
                "source": {
                    "id": "https://school.edu/issuers/201234",
                    "type": ["Profile"],
                    "name": "1EdTech College of Arts",
                },
                "term": "Fall",
                "identifier": [
                    {
                        "type": "IdentityObject",
                        "identityHash": "student@1edtech.edu",
                        "identityType": "emailAddress",
                        "hashed": False,
                        "salt": "not-used",
                    },
                    {
                        "type": "IdentityObject",
                        "identityHash": "somebody@gmail.com",
                        "identityType": "emailAddress",
                        "hashed": False,
                        "salt": "not-used",
                    },
                ],
                "achievement": {
                    "id": "https://1edtech.edu/achievements/degree",
                    "type": ["Achievement"],
                    "alignment": [
                        {
                            "type": ["Alignment"],
                            "targetCode": "degree",
                            "targetDescription": "1EdTech University Degree programs.",
                            "targetName": "1EdTech University Degree",
                            "targetFramework": "1EdTech University Program and Course Catalog",
                            "targetType": "CFItem",
                            "targetUrl": "https://1edtech.edu/catalog/degree",
                            "targetCategory": "category1",
                        },
                        {
                            "type": ["Alignment"],
                            "targetCode": "degree",
                            "targetDescription": "1EdTech University Degree programs.",
                            "targetName": "1EdTech University Degree",
                            "targetFramework": "1EdTech University Program and Course Catalog",
                            "targetType": "CTDL",
                            "targetUrl": "https://credentialengineregistry.org/resources/ce-98cb027b-95ef-4494-908d-6f7790ec6b6b",
                            "targetCategory": "category2",
                        },
                    ],
                    "achievementType": "Degree",
                    "creator": {
                        "id": "https://1edtech.edu/issuers/565049",
                        "type": ["Profile"],
                        "name": "1EdTech University",
                        "url": "https://1edtech.edu",
                        "phone": "1-222-333-4444",
                        "description": "1EdTech University provides online degree programs.",
                        "image": {
                            "id": "https://1edtech.edu/logo.png",
                            "type": "Image",
                            "caption": "1EdTech University logo",
                        },
                        "email": "registrar@1edtech.edu",
                        "address": {
                            "type": ["Address"],
                            "addressCountry": "United States",
                            "addressRegion": "TX",
                            "addressLocality": "Austin",
                            "streetAddress": "123 First St",
                            "postOfficeBoxNumber": "1",
                            "postalCode": "12345",
                            "geo": {"type": "GeoCoordinates", "latitude": 1.0, "longitude": 1.0},
                        },
                        "otherIdentifier": [
                            {"type": "IdentifierEntry", "identifier": "12345", "identifierType": "sourcedId"},
                            {
                                "type": "IdentifierEntry",
                                "identifier": "67890",
                                "identifierType": "nationalIdentityNumber",
                            },
                        ],
                        "official": "Horace Mann",
                    },
                    "creditsAvailable": 36.0,
                    "criteria": {
                        "id": "https://1edtech.edu/achievements/degree",
                        "narrative": "# Degree Requirements\nStudents must complete...",
                    },
                    "description": "1EdTech University Degree Description",
                    "fieldOfStudy": "Research",
                    "image": {
                        "id": "https://1edtech.edu/achievements/degree/image",
                        "type": "Image",
                        "caption": "1EdTech University Degree",
                    },
                    "name": "1EdTech University Degree",
                    "specialization": "Computer Science Research",
                    "tag": ["research", "computer science"],
                },
            },
            "issuer": {
                "id": "https://1edtech.edu/issuers/565049",
                "type": ["Profile"],
                "name": "1EdTech University",
                "url": "https://1edtech.edu",
                "phone": "1-222-333-4444",
                "description": "1EdTech University provides online degree programs.",
                "image": {"id": "https://1edtech.edu/logo.png", "type": "Image", "caption": "1EdTech University logo"},
                "email": "registrar@1edtech.edu",
                "address": {
                    "type": ["Address"],
                    "addressCountry": "United States",
                    "addressRegion": "TX",
                    "addressLocality": "Austin",
                    "streetAddress": "123 First St",
                    "postalCode": "12345",
                    "geo": {"type": "GeoCoordinates", "latitude": 1.0, "longitude": 1.0},
                },
                "otherIdentifier": [
                    {"type": "IdentifierEntry", "identifier": "12345", "identifierType": "sourcedId"},
                    {"type": "IdentifierEntry", "identifier": "67890", "identifierType": "nationalIdentityNumber"},
                ],
                "official": "Horace Mann",
            },
            "validFrom": "2010-01-01T00:00:00Z",
            "credentialSchema": [
                {
                    "id": "https://purl.imsglobal.org/spec/ob/v3p0/schema/json/ob_v3p0_achievementcredential_schema.json",
                    "type": "1EdTechJsonSchemaValidator2019",
                }
            ],
            "credentialStatus": {
                "id": "https://1edtech.edu/credentials/3732/revocations",
                "type": "1EdTechRevocationList",
            },
            "refreshService": {"id": "http://1edtech.edu/credentials/3732", "type": "1EdTechCredentialRefresh"},
            "information_source_id": "stateu_ob3_adapter",
            "pull_timestamp": "2024-02-29 00:00:00",
        }
    }

    # Expected output per prompt
    expected = {
        "Credential": {
            "format": [
                "https://www.w3.org/ns/credentials/v2",
                "https://purl.imsglobal.org/spec/ob/v3p0/context-3.0.3.json",
                "https://purl.imsglobal.org/spec/ob/v3p0/extensions.json",
                "VerifiableCredential",
                "OpenBadgeCredential",
            ],
            "name": "1EdTech University Degree for Example Student",
            "description": "1EdTech University Degree Description",
            "Image": [
                {
                    "imageId": "https://1edtech.edu/credentials/3732/image",
                    "imageType": "Image",
                    "caption": "1EdTech University Degree for Example Student",
                }
            ],
        },
        "Person": {
            "CredentialAward": [{"id": "http://1edtech.edu/credentials/3732"}],
            "Identifier": [
                {"identifier": "did:example:ebfeb1f712ebc6f1c276e12ec21", "identifierType": ["AchievementSubject"]}
            ],
        },
    }

    # Transformation payload: subset of entries from transformations_for_16_to_17.json
    transformation_payload = {
        "total": 9,
        "page": 1,
        "size": 1000,
        "total_pages": 1,
        "next": None,
        "previous": None,
        "data": [
            {
                "TransformationGroupId": 16,
                "SourceDataModelId": 16,
                "TargetDataModelId": 17,
                "TransformationId": 1365,
                "TransformationExpression": '{\n  "Credential": OpenBadgeCredential.{\n    "format": [\n      ($lookup($, "@context") ? $lookup($, "@context") : [])[],\n      (type ? type : [])[]\n    ]\n  }\n}',
                "TransformationExpressionLanguage": "JSONata",
            },
            {
                "TransformationGroupId": 16,
                "SourceDataModelId": 16,
                "TargetDataModelId": 17,
                "TransformationId": 1367,
                "TransformationExpression": '{ "Person": OpenBadgeCredential. { "CredentialAward": [{ "id": id }] } }',
                "TransformationExpressionLanguage": "JSONata",
            },
            {
                "TransformationGroupId": 16,
                "SourceDataModelId": 16,
                "TargetDataModelId": 17,
                "TransformationId": 1368,
                "TransformationExpression": '{ "Credential": OpenBadgeCredential. { "name": name } }',
                "TransformationExpressionLanguage": "JSONata",
            },
            {
                "TransformationGroupId": 16,
                "SourceDataModelId": 16,
                "TargetDataModelId": 17,
                "TransformationId": 1369,
                "TransformationExpression": '{ "Credential": OpenBadgeCredential. { "description": description } }',
                "TransformationExpressionLanguage": "JSONata",
            },
            {
                "TransformationGroupId": 16,
                "SourceDataModelId": 16,
                "TargetDataModelId": 17,
                "TransformationId": 1370,
                "TransformationExpression": '{ "Credential": OpenBadgeCredential. { "Image": [{ "imageId": image.id }] } }',
                "TransformationExpressionLanguage": "JSONata",
            },
            {
                "TransformationGroupId": 16,
                "SourceDataModelId": 16,
                "TargetDataModelId": 17,
                "TransformationId": 1371,
                "TransformationExpression": '{ "Credential": OpenBadgeCredential. { "Image": [{ "imageType": image.type }] } }',
                "TransformationExpressionLanguage": "JSONata",
            },
            {
                "TransformationGroupId": 16,
                "SourceDataModelId": 16,
                "TargetDataModelId": 17,
                "TransformationId": 1372,
                "TransformationExpression": '{ "Credential": OpenBadgeCredential. { "Image": [{ "caption": image.caption }] } }',
                "TransformationExpressionLanguage": "JSONata",
            },
            {
                "TransformationGroupId": 16,
                "SourceDataModelId": 16,
                "TargetDataModelId": 17,
                "TransformationId": 1373,
                "TransformationExpression": '{ "Person": OpenBadgeCredential. { "Identifier": [{ "identifier": credentialSubject.id }] } }',
                "TransformationExpressionLanguage": "JSONata",
            },
            {
                "TransformationGroupId": 16,
                "SourceDataModelId": 16,
                "TargetDataModelId": 17,
                "TransformationId": 1374,
                "TransformationExpression": '{ "Person": OpenBadgeCredential. { "Identifier": [{ "identifierType": credentialSubject.type }] } }',
                "TransformationExpressionLanguage": "JSONata",
            },
        ],
    }

    # Monkeypatch schema and transformation fetchers
    async def fake_fetch_schema(self, schema_id: str) -> dict:
        return {}

    async def fake_fetch_transformation(self, source_schema_id: str, target_schema_id: str) -> dict:
        return transformation_payload

    monkeypatch.setattr(core.Translator, "_fetch_schema", fake_fetch_schema, raising=False)
    monkeypatch.setattr(core.Translator, "_fetch_transformation", fake_fetch_transformation, raising=False)

    # Run translator 16 -> 17
    config = core.TranslatorConfig(source_schema_id="16", target_schema_id="17")
    translator = core.Translator(config)

    result = await translator.run(input_data)
    assert result == expected
