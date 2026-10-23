"""The Translator's read: only the latest active version of a (source, target) group, and only its JSONata
rules (#1350). A group with no ActivationDate is not activated; activating one makes it the live version."""

import inspect
import logging
from datetime import datetime, timedelta, timezone

import pytest

from lif.mdr_sql_model.core import TransformationGroup
from test.utils.lif.datasets.transform_with_embeddings.loader import DatasetTransformWithEmbeddings
from test.utils.lif.mdr.api import create_transformation, import_transformation_group

ACTIVE_URL = "/transformation_groups/active_transformations_for_data_models/"
# Groups the tests set up as already live. Plain create still honors a supplied ActivationDate.
PAST = "2026-01-01T00:00:00Z"


def _iso(delta: timedelta) -> str:
    return (datetime.now(timezone.utc) + delta).isoformat()


async def _prepare(async_client_mdr, test_case_name: str) -> tuple[DatasetTransformWithEmbeddings, int]:
    """A source/target pair with a version 1.0 group (from the dataset) holding one JSONata rule.
    Returns the dataset and that rule's ID."""
    dataset = await DatasetTransformWithEmbeddings.prepare(
        async_client_mdr=async_client_mdr,
        source_data_model_name=test_case_name,
        target_data_model_name=test_case_name,
        transformation_group_name=test_case_name,
        transformation_group_activation_date=PAST,
    )
    rule = await _add_rule(async_client_mdr, dataset, dataset.transformation_group_id, name="v1.0 rule")
    return dataset, rule["Id"]


async def _add_group(async_client_mdr, dataset, headers, version: str, **dates) -> int:
    response = await async_client_mdr.post(
        "/transformation_groups/",
        headers=headers,
        json={
            "SourceDataModelId": dataset.source_data_model_id,
            "TargetDataModelId": dataset.target_data_model_id,
            "Name": f"group {version}",
            "GroupVersion": version,
            "ActivationDate": PAST,
            **dates,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["Id"]


async def _activate(async_client_mdr, headers, group_id: int, activation_date: str | None = None):
    params = {"activation_date": activation_date} if activation_date else {}
    return await async_client_mdr.post(f"/transformation_groups/{group_id}/activate", headers=headers, params=params)


async def _get_group(async_client_mdr, headers, dataset, group_id: int) -> dict:
    response = await async_client_mdr.get(
        "/transformation_groups/source_and_target/",
        headers=headers,
        params={
            "source_data_model_id": dataset.source_data_model_id,
            "target_data_model_id": dataset.target_data_model_id,
        },
    )
    assert response.status_code == 200, response.text
    return next(group for group in response.json() if group["Id"] == group_id)


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


async def _add_rule(async_client_mdr, dataset, group_id, name: str, expression_language: str = "JSONata") -> dict:
    return await create_transformation(
        async_client_mdr=async_client_mdr,
        transformation_group_id=group_id,
        source_parent_entity_id=None,
        source_attribute_id=dataset.flow1_source_attribute_id,
        source_entity_path=dataset.flow1_source_entity_id_path,
        target_parent_entity_id=None,
        target_attribute_id=dataset.flow1_target_attribute_id,
        target_entity_path=dataset.flow1_target_entity_id_path,
        mapping_expression='{ "User": { "Workplace": { "Abilities": { "Skills": { "LevelOfSkillAbility": '
        "Person.Employment.SkillsGainedFromCourses.SkillLevel } } } } }",
        transformation_name=name,
        expression_language=expression_language,
    )


async def _get_active(async_client_mdr, dataset, headers):
    return await async_client_mdr.get(
        ACTIVE_URL,
        headers=headers,
        params={
            "source_data_model_id": dataset.source_data_model_id,
            "target_data_model_id": dataset.target_data_model_id,
        },
    )


@pytest.mark.asyncio
async def test_two_active_versions_returns_only_the_higher(async_client_mdr, mdr_api_headers):
    dataset, _ = await _prepare(async_client_mdr, inspect.currentframe().f_code.co_name)
    v2_id = await _add_group(async_client_mdr, dataset, mdr_api_headers, "2.0")
    v2_rule = await _add_rule(async_client_mdr, dataset, v2_id, name="v2.0 rule")

    response = await _get_active(async_client_mdr, dataset, mdr_api_headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["TransformationGroupId"] == v2_id
    assert body["GroupVersion"] == "2.0"
    assert body["total"] == 1
    assert [row["TransformationId"] for row in body["data"]] == [v2_rule["Id"]]


@pytest.mark.asyncio
async def test_general_listing_still_returns_every_live_version(async_client_mdr, mdr_api_headers):
    """The fix is a new read; the existing listing endpoint keeps its behavior."""
    dataset, _ = await _prepare(async_client_mdr, inspect.currentframe().f_code.co_name)
    v2_id = await _add_group(async_client_mdr, dataset, mdr_api_headers, "2.0")
    await _add_rule(async_client_mdr, dataset, v2_id, name="v2.0 rule")

    response = await async_client_mdr.get(
        "/transformation_groups/transformations_for_data_models/",
        headers=mdr_api_headers,
        params={
            "source_data_model_id": dataset.source_data_model_id,
            "target_data_model_id": dataset.target_data_model_id,
            "size": 100,
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["total"] == 2


@pytest.mark.asyncio
async def test_versions_compare_as_dotted_integers(async_client_mdr, mdr_api_headers):
    """As text, "1.10" < "1.9"; as a version it is higher."""
    dataset, _ = await _prepare(async_client_mdr, inspect.currentframe().f_code.co_name)
    v1_9_id = await _add_group(async_client_mdr, dataset, mdr_api_headers, "1.9")
    await _add_rule(async_client_mdr, dataset, v1_9_id, name="v1.9 rule")
    v1_10_id = await _add_group(async_client_mdr, dataset, mdr_api_headers, "1.10")
    await _add_rule(async_client_mdr, dataset, v1_10_id, name="v1.10 rule")

    response = await _get_active(async_client_mdr, dataset, mdr_api_headers)

    assert response.status_code == 200, response.text
    assert response.json()["GroupVersion"] == "1.10"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("case", "dates"),
    [
        ("deprecated", {"DeprecationDate": timedelta(days=-1)}),
        ("not_yet_active", {"ActivationDate": timedelta(days=1)}),
        # Compared with UTC now, not a naive local time: one minute ahead is still in the future.
        ("one_minute_ahead", {"ActivationDate": timedelta(minutes=1)}),
        ("never_activated", {"ActivationDate": None}),
    ],
)
async def test_inactive_higher_version_falls_back_to_the_lower(async_client_mdr, mdr_api_headers, case, dates):
    # Offsets, not dates: a date computed at collection time goes stale before a long run reaches the test.
    dates = {field: None if delta is None else _iso(delta) for field, delta in dates.items()}
    dataset, v1_rule_id = await _prepare(async_client_mdr, f"{inspect.currentframe().f_code.co_name}_{case}")
    v2_id = await _add_group(async_client_mdr, dataset, mdr_api_headers, "2.0", **dates)
    await _add_rule(async_client_mdr, dataset, v2_id, name="v2.0 rule")

    response = await _get_active(async_client_mdr, dataset, mdr_api_headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["TransformationGroupId"] == dataset.transformation_group_id
    assert [row["TransformationId"] for row in body["data"]] == [v1_rule_id]


@pytest.mark.asyncio
async def test_bounded_dates_that_include_now_are_active(async_client_mdr, mdr_api_headers):
    dataset, _ = await _prepare(async_client_mdr, inspect.currentframe().f_code.co_name)
    v2_id = await _add_group(
        async_client_mdr,
        dataset,
        mdr_api_headers,
        "2.0",
        ActivationDate=_iso(timedelta(days=-1)),
        DeprecationDate=_iso(timedelta(days=1)),
    )
    await _add_rule(async_client_mdr, dataset, v2_id, name="v2.0 rule")

    response = await _get_active(async_client_mdr, dataset, mdr_api_headers)

    assert response.status_code == 200, response.text
    assert response.json()["TransformationGroupId"] == v2_id


@pytest.mark.asyncio
async def test_non_jsonata_rules_are_excluded(async_client_mdr, mdr_api_headers):
    dataset, v1_rule_id = await _prepare(async_client_mdr, inspect.currentframe().f_code.co_name)
    await _add_rule(
        async_client_mdr, dataset, dataset.transformation_group_id, name="draft", expression_language="LIF_Pseudo_Code"
    )

    response = await _get_active(async_client_mdr, dataset, mdr_api_headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 1
    assert [row["TransformationId"] for row in body["data"]] == [v1_rule_id]


@pytest.mark.asyncio
async def test_no_active_version_is_a_404_naming_the_pair(async_client_mdr, mdr_api_headers):
    dataset, _ = await _prepare(async_client_mdr, inspect.currentframe().f_code.co_name)
    response = await async_client_mdr.put(
        f"/transformation_groups/{dataset.transformation_group_id}",
        headers=mdr_api_headers,
        json={"DeprecationDate": _iso(timedelta(days=-1))},
    )
    assert response.status_code == 200, response.text

    response = await _get_active(async_client_mdr, dataset, mdr_api_headers)

    assert response.status_code == 404, response.text
    detail = response.json()["detail"]
    assert str(dataset.source_data_model_id) in detail
    assert str(dataset.target_data_model_id) in detail


@pytest.mark.asyncio
async def test_two_active_groups_at_the_same_version_is_a_409(async_client_mdr, mdr_api_headers):
    """ "1" and "1.0" are different strings, so both can exist, but they are the same version."""
    dataset, _ = await _prepare(async_client_mdr, inspect.currentframe().f_code.co_name)
    await _add_group(async_client_mdr, dataset, mdr_api_headers, "1")

    response = await _get_active(async_client_mdr, dataset, mdr_api_headers)

    assert response.status_code == 409, response.text
    assert "1, 1.0" in response.json()["detail"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("case", "version"),
    [("prefix", "v2"), ("suffix", "2.0-beta"), ("empty", ""), ("empty_part", "1..0"), ("padded", " 1.0")],
)
async def test_create_rejects_a_non_numeric_group_version(async_client_mdr, mdr_api_headers, case, version):
    dataset, _ = await _prepare(async_client_mdr, f"{inspect.currentframe().f_code.co_name}_{case}")
    response = await async_client_mdr.post(
        "/transformation_groups/",
        headers=mdr_api_headers,
        json={
            "SourceDataModelId": dataset.source_data_model_id,
            "TargetDataModelId": dataset.target_data_model_id,
            "Name": "bad version",
            "GroupVersion": version,
        },
    )
    assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_update_rejects_a_non_numeric_group_version(async_client_mdr, mdr_api_headers):
    dataset, _ = await _prepare(async_client_mdr, inspect.currentframe().f_code.co_name)
    response = await async_client_mdr.put(
        f"/transformation_groups/{dataset.transformation_group_id}",
        headers=mdr_api_headers,
        json={"GroupVersion": "latest"},
    )
    assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_import_rejects_a_non_numeric_version(async_client_mdr, mdr_api_headers):
    dataset, _ = await _prepare(async_client_mdr, inspect.currentframe().f_code.co_name)
    exported = (
        await async_client_mdr.get(
            f"/transformation_groups/{dataset.transformation_group_id}/export", headers=mdr_api_headers
        )
    ).json()

    result = await import_transformation_group(
        async_client_mdr=async_client_mdr,
        transformation_group_id=dataset.transformation_group_id,
        body=exported,
        version="2.0-draft",
        headers=mdr_api_headers,
        expected_status_code=422,
    )
    assert "2.0-draft" in result["detail"]


@pytest.mark.asyncio
async def test_an_undated_group_is_not_active(async_client_mdr, mdr_api_headers):
    dataset = await DatasetTransformWithEmbeddings.prepare(
        async_client_mdr=async_client_mdr,
        source_data_model_name="undated",
        target_data_model_name="undated",
        transformation_group_name="undated",
    )
    await _add_rule(async_client_mdr, dataset, dataset.transformation_group_id, name="rule")

    response = await _get_active(async_client_mdr, dataset, mdr_api_headers)

    assert response.status_code == 404, response.text


@pytest.mark.asyncio
async def test_a_free_text_version_is_skipped_with_a_warning(
    async_client_mdr, mdr_api_headers, test_db_session, caplog
):
    """A row from before #1368's validation can still hold free text; it is skipped, not a 500."""
    dataset, v1_rule_id = await _prepare(async_client_mdr, inspect.currentframe().f_code.co_name)
    legacy = TransformationGroup(
        SourceDataModelId=dataset.source_data_model_id,
        TargetDataModelId=dataset.target_data_model_id,
        GroupVersion="v1",
        Name="legacy",
        ActivationDate=_parse(PAST),
    )
    test_db_session.add(legacy)
    await test_db_session.commit()

    with caplog.at_level(logging.WARNING):
        response = await _get_active(async_client_mdr, dataset, mdr_api_headers)

    assert response.status_code == 200, response.text
    assert response.json()["TransformationGroupId"] == dataset.transformation_group_id
    assert f"Ignoring transformation group {legacy.Id}" in caplog.text


@pytest.mark.asyncio
async def test_activate_makes_the_group_live_and_deprecates_the_others_at_that_time(async_client_mdr, mdr_api_headers):
    dataset, _ = await _prepare(async_client_mdr, inspect.currentframe().f_code.co_name)
    v2_id = await _add_group(async_client_mdr, dataset, mdr_api_headers, "2.0", ActivationDate=None)
    await _add_rule(async_client_mdr, dataset, v2_id, name="v2.0 rule")

    response = await _activate(async_client_mdr, mdr_api_headers, v2_id)

    assert response.status_code == 200, response.text
    activated = response.json()
    assert activated["Id"] == v2_id
    assert activated["DeprecationDate"] is None
    active = await _get_active(async_client_mdr, dataset, mdr_api_headers)
    assert active.json()["TransformationGroupId"] == v2_id
    v1 = await _get_group(async_client_mdr, mdr_api_headers, dataset, dataset.transformation_group_id)
    assert _parse(v1["DeprecationDate"]) == _parse(activated["ActivationDate"])


@pytest.mark.asyncio
async def test_rollback_is_activating_the_older_version(async_client_mdr, mdr_api_headers):
    """Activating a lower version works even while a higher one is live, and clears its own deprecation."""
    dataset, v1_rule_id = await _prepare(async_client_mdr, inspect.currentframe().f_code.co_name)
    v2_id = await _add_group(async_client_mdr, dataset, mdr_api_headers, "2.0", ActivationDate=None)
    await _add_rule(async_client_mdr, dataset, v2_id, name="v2.0 rule")
    assert (await _activate(async_client_mdr, mdr_api_headers, v2_id)).status_code == 200

    response = await _activate(async_client_mdr, mdr_api_headers, dataset.transformation_group_id)

    assert response.status_code == 200, response.text
    assert response.json()["DeprecationDate"] is None
    active = (await _get_active(async_client_mdr, dataset, mdr_api_headers)).json()
    assert active["TransformationGroupId"] == dataset.transformation_group_id
    assert [row["TransformationId"] for row in active["data"]] == [v1_rule_id]
    assert (await _get_group(async_client_mdr, mdr_api_headers, dataset, v2_id))["DeprecationDate"] is not None


@pytest.mark.asyncio
async def test_a_scheduled_activation_leaves_no_gap(async_client_mdr, mdr_api_headers):
    """Until the scheduled time the current version stays live; it is deprecated at exactly that time."""
    dataset, _ = await _prepare(async_client_mdr, inspect.currentframe().f_code.co_name)
    v2_id = await _add_group(async_client_mdr, dataset, mdr_api_headers, "2.0", ActivationDate=None)
    await _add_rule(async_client_mdr, dataset, v2_id, name="v2.0 rule")
    scheduled = _iso(timedelta(days=1))

    response = await _activate(async_client_mdr, mdr_api_headers, v2_id, activation_date=scheduled)

    assert response.status_code == 200, response.text
    assert _parse(response.json()["ActivationDate"]) == _parse(scheduled)
    active = await _get_active(async_client_mdr, dataset, mdr_api_headers)
    assert active.json()["TransformationGroupId"] == dataset.transformation_group_id
    v1 = await _get_group(async_client_mdr, mdr_api_headers, dataset, dataset.transformation_group_id)
    assert _parse(v1["DeprecationDate"]) == _parse(scheduled)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("case", "activation_date"),
    [
        ("past", lambda: _iso(timedelta(days=-1))),
        # Compared with an aware now, a naive date would be a TypeError (a 500), not a schedule.
        ("no_offset", lambda: (datetime.now(timezone.utc) + timedelta(days=1)).replace(tzinfo=None).isoformat()),
    ],
)
async def test_activate_rejects_a_bad_date(async_client_mdr, mdr_api_headers, case, activation_date):
    activation_date = activation_date()
    dataset, _ = await _prepare(async_client_mdr, f"{inspect.currentframe().f_code.co_name}_{case}")

    response = await _activate(
        async_client_mdr, mdr_api_headers, dataset.transformation_group_id, activation_date=activation_date
    )

    assert response.status_code == 422, response.text
    v1 = await _get_group(async_client_mdr, mdr_api_headers, dataset, dataset.transformation_group_id)
    assert v1["DeprecationDate"] is None


@pytest.mark.asyncio
async def test_activate_a_deleted_group_is_a_404(async_client_mdr, mdr_api_headers):
    dataset, _ = await _prepare(async_client_mdr, inspect.currentframe().f_code.co_name)
    v2_id = await _add_group(async_client_mdr, dataset, mdr_api_headers, "2.0", ActivationDate=None)
    assert (
        await async_client_mdr.delete(f"/transformation_groups/{v2_id}", headers=mdr_api_headers)
    ).status_code == 200

    response = await _activate(async_client_mdr, mdr_api_headers, v2_id)

    assert response.status_code == 404, response.text
    v1 = await _get_group(async_client_mdr, mdr_api_headers, dataset, dataset.transformation_group_id)
    assert v1["DeprecationDate"] is None


@pytest.mark.asyncio
async def test_activate_rejects_a_free_text_version(async_client_mdr, mdr_api_headers, test_db_session):
    """The active-set read skips it, so activating it would only deprecate the live version."""
    dataset, _ = await _prepare(async_client_mdr, inspect.currentframe().f_code.co_name)
    legacy = TransformationGroup(
        SourceDataModelId=dataset.source_data_model_id,
        TargetDataModelId=dataset.target_data_model_id,
        GroupVersion="v1",
        Name="legacy",
    )
    test_db_session.add(legacy)
    await test_db_session.commit()

    response = await _activate(async_client_mdr, mdr_api_headers, legacy.Id)

    assert response.status_code == 422, response.text
    v1 = await _get_group(async_client_mdr, mdr_api_headers, dataset, dataset.transformation_group_id)
    assert v1["DeprecationDate"] is None


@pytest.mark.asyncio
async def test_an_import_arrives_inactive_whatever_the_file_says(async_client_mdr, mdr_api_headers):
    dataset, _ = await _prepare(async_client_mdr, inspect.currentframe().f_code.co_name)
    exported = (
        await async_client_mdr.get(
            f"/transformation_groups/{dataset.transformation_group_id}/export", headers=mdr_api_headers
        )
    ).json()
    assert exported["ActivationDate"] is not None

    result = await import_transformation_group(
        async_client_mdr=async_client_mdr,
        transformation_group_id=dataset.transformation_group_id,
        body=exported,
        headers=mdr_api_headers,
    )

    imported = await _get_group(async_client_mdr, mdr_api_headers, dataset, result["TransformationGroupId"])
    assert imported["ActivationDate"] is None
    active = await _get_active(async_client_mdr, dataset, mdr_api_headers)
    assert active.json()["TransformationGroupId"] == dataset.transformation_group_id
