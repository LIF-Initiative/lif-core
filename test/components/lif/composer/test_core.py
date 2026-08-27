import json

from lif.composer.core import compose_with_fragment_list, compose_with_single_fragment
from lif.datatypes.core import LIFFragment, LIFRecord


employment_learning_experience_1 = '{"foo":"bar"}'
employment_learning_experience_1_dict = json.loads(employment_learning_experience_1)
employment_learning_experience_2 = '{"alpha":"beta"}'
employment_learning_experience_2_dict = json.loads(employment_learning_experience_2)
employment_learning_experience_3 = '{"gamma":"delta"}'
employment_learning_experience_3_dict = json.loads(employment_learning_experience_3)
employment_learning_experience_4 = '{"epsilon":"zeta"}'
employment_learning_experience_4_dict = json.loads(employment_learning_experience_4)
identifier_1 = '{"identifier": "100005", "identifierType": "School-assigned number"}'
identifier_1_dict = json.loads(identifier_1)
identifier_2 = '{"identifier": "sha256$81fb9410e68f70a95e9a614e8fcefba8a067fa406a1405610093713d4009844a", "identifierType": "INSTITUTION_ASSIGNED_NUMBER"}'
identifier_2_dict = json.loads(identifier_2)
identifier_3 = '{"identifier": "ABC-20250005", "identifierType": "ABC University student ID"}'
identifier_3_dict = json.loads(identifier_3)


def test_compose_with_single_fragment_with_existing_empty_array():
    lif_fragment = LIFFragment(
        fragment_path="person.employmentLearningExperience", fragment=[employment_learning_experience_1_dict]
    )
    lif_record_json = {"person": [{"foo": "foo", "employmentLearningExperience": []}]}
    lif_record = LIFRecord(**lif_record_json)
    new_lif_record = compose_with_single_fragment(lif_record, lif_fragment)
    assert lif_record.person[0]["foo"] == "foo"
    assert lif_record.person[0]["employmentLearningExperience"] == []
    assert new_lif_record.person[0]["foo"] == "foo"
    assert new_lif_record.person[0]["employmentLearningExperience"][0] == employment_learning_experience_1_dict


def test_compose_with_single_fragment_with_existing_nonempty_array():
    lif_fragment = LIFFragment(
        fragment_path="person.employmentLearningExperience", fragment=[employment_learning_experience_1_dict]
    )
    lif_record_json = {
        "person": [{"foo": "foo", "employmentLearningExperience": [employment_learning_experience_2_dict]}]
    }
    lif_record = LIFRecord(**lif_record_json)
    new_lif_record = compose_with_single_fragment(lif_record, lif_fragment)
    assert lif_record.person[0]["foo"] == "foo"
    assert lif_record.person[0]["employmentLearningExperience"] == [employment_learning_experience_2_dict]
    assert new_lif_record.person[0]["foo"] == "foo"
    assert new_lif_record.person[0]["employmentLearningExperience"][0] == employment_learning_experience_2_dict
    assert new_lif_record.person[0]["employmentLearningExperience"][1] == employment_learning_experience_1_dict


def test_compose_with_single_fragment_with_no_existing_array():
    lif_fragment = LIFFragment(
        fragment_path="person.employmentLearningExperience", fragment=[employment_learning_experience_1_dict]
    )
    lif_record_json = {"person": [{"foo": "foo"}]}
    lif_record = LIFRecord(**lif_record_json)
    new_lif_record = compose_with_single_fragment(lif_record, lif_fragment)
    assert lif_record.person[0]["foo"] == "foo"
    assert "employmentLearningExperience" not in lif_record.person[0]
    assert new_lif_record.person[0]["foo"] == "foo"
    assert new_lif_record.person[0]["employmentLearningExperience"][0] == employment_learning_experience_1_dict


def test_compose_with_fragment_list_with_existing_empty_array():
    lif_fragment1 = LIFFragment(
        fragment_path="person.employmentLearningExperience", fragment=[employment_learning_experience_1_dict]
    )
    lif_fragment2 = LIFFragment(
        fragment_path="person.employmentLearningExperience", fragment=[employment_learning_experience_2_dict]
    )
    lif_record_json = {"person": [{"foo": "foo", "employmentLearningExperience": []}]}
    lif_record = LIFRecord(**lif_record_json)
    new_lif_record = compose_with_fragment_list(lif_record, [lif_fragment1, lif_fragment2])
    assert lif_record.person[0]["foo"] == "foo"
    assert lif_record.person[0]["employmentLearningExperience"] == []
    assert new_lif_record.person[0]["foo"] == "foo"
    assert new_lif_record.person[0]["employmentLearningExperience"][0] == employment_learning_experience_1_dict
    assert new_lif_record.person[0]["employmentLearningExperience"][1] == employment_learning_experience_2_dict


def test_compose_with_fragment_list_with_existing_nonempty_array():
    lif_fragment1 = LIFFragment(
        fragment_path="person.employmentLearningExperience", fragment=[employment_learning_experience_1_dict]
    )
    lif_fragment2 = LIFFragment(
        fragment_path="person.employmentLearningExperience", fragment=[employment_learning_experience_2_dict]
    )
    lif_record_json = {
        "person": [
            {
                "foo": "foo",
                "employmentLearningExperience": [
                    employment_learning_experience_3_dict,
                    employment_learning_experience_4_dict,
                ],
            }
        ]
    }
    lif_record = LIFRecord(**lif_record_json)
    new_lif_record = compose_with_fragment_list(lif_record, [lif_fragment1, lif_fragment2])
    assert lif_record.person[0]["foo"] == "foo"
    assert lif_record.person[0]["employmentLearningExperience"] == [
        employment_learning_experience_3_dict,
        employment_learning_experience_4_dict,
    ]
    assert new_lif_record.person[0]["foo"] == "foo"
    # Issue #1165: the fragments replace what was there; the two fragments targeting the
    # same path still accumulate with each other within this one call.
    assert new_lif_record.person[0]["employmentLearningExperience"] == [
        employment_learning_experience_1_dict,
        employment_learning_experience_2_dict,
    ]

    # The old append behavior is still available explicitly.
    appended = compose_with_fragment_list(lif_record, [lif_fragment1, lif_fragment2], replace_existing=False)
    assert appended.person[0]["employmentLearningExperience"] == [
        employment_learning_experience_3_dict,
        employment_learning_experience_4_dict,
        employment_learning_experience_1_dict,
        employment_learning_experience_2_dict,
    ]


def test_compose_with_fragment_list_with_no_existing_array():
    lif_fragment3 = LIFFragment(
        fragment_path="person.employmentLearningExperience", fragment=[employment_learning_experience_3_dict]
    )
    lif_fragment4 = LIFFragment(
        fragment_path="person.employmentLearningExperience", fragment=[employment_learning_experience_4_dict]
    )
    lif_record_json = {"person": [{"foo": "foo"}]}
    lif_record = LIFRecord(**lif_record_json)
    new_lif_record = compose_with_fragment_list(lif_record, [lif_fragment3, lif_fragment4])
    assert lif_record.person[0]["foo"] == "foo"
    assert "employmentLearningExperience" not in lif_record.person[0]
    assert new_lif_record.person[0]["foo"] == "foo"
    assert new_lif_record.person[0]["employmentLearningExperience"][0] == employment_learning_experience_3_dict
    assert new_lif_record.person[0]["employmentLearningExperience"][1] == employment_learning_experience_4_dict


def test_compose_with_fragment_list_with_existing_nonempty_array_for_identifier():
    lif_fragment1 = LIFFragment(fragment_path="person.identifier", fragment=[identifier_3_dict])
    lif_record_json = {"person": [{"foo": "foo", "identifier": [identifier_1_dict, identifier_2_dict]}]}
    lif_record = LIFRecord(**lif_record_json)
    new_lif_record = compose_with_fragment_list(lif_record, [lif_fragment1])
    assert lif_record.person[0]["foo"] == "foo"
    assert lif_record.person[0]["identifier"] == [identifier_1_dict, identifier_2_dict]
    assert new_lif_record.person[0]["foo"] == "foo"
    # Issue #1165: the incoming fragment is the current source truth for this path.
    assert new_lif_record.person[0]["identifier"] == [identifier_3_dict]

    appended = compose_with_fragment_list(lif_record, [lif_fragment1], replace_existing=False)
    assert appended.person[0]["identifier"] == [identifier_1_dict, identifier_2_dict, identifier_3_dict]


def test_compose_with_single_multi_item_fragment_with_existing_empty_array():
    lif_fragment = LIFFragment(
        fragment_path="person.employmentLearningExperience",
        fragment=[employment_learning_experience_1_dict, employment_learning_experience_2_dict],
    )
    lif_record_json = {"person": [{"foo": "foo", "employmentLearningExperience": []}]}
    lif_record = LIFRecord(**lif_record_json)
    new_lif_record = compose_with_single_fragment(lif_record, lif_fragment)
    assert lif_record.person[0]["foo"] == "foo"
    assert lif_record.person[0]["employmentLearningExperience"] == []
    assert new_lif_record.person[0]["foo"] == "foo"
    assert new_lif_record.person[0]["employmentLearningExperience"][0] == employment_learning_experience_1_dict
    assert new_lif_record.person[0]["employmentLearningExperience"][1] == employment_learning_experience_2_dict


def test_compose_with_single_multi_item_fragment_with_existing_nonempty_array():
    lif_fragment = LIFFragment(
        fragment_path="person.employmentLearningExperience",
        fragment=[employment_learning_experience_1_dict, employment_learning_experience_3_dict],
    )
    lif_record_json = {
        "person": [{"foo": "foo", "employmentLearningExperience": [employment_learning_experience_2_dict]}]
    }
    lif_record = LIFRecord(**lif_record_json)
    new_lif_record = compose_with_single_fragment(lif_record, lif_fragment)
    assert lif_record.person[0]["foo"] == "foo"
    assert lif_record.person[0]["employmentLearningExperience"] == [employment_learning_experience_2_dict]
    assert new_lif_record.person[0]["foo"] == "foo"
    assert new_lif_record.person[0]["employmentLearningExperience"][0] == employment_learning_experience_2_dict
    assert new_lif_record.person[0]["employmentLearningExperience"][1] == employment_learning_experience_1_dict
    assert new_lif_record.person[0]["employmentLearningExperience"][2] == employment_learning_experience_3_dict


def test_compose_with_single_multi_item_fragment_with_no_existing_array():
    lif_fragment = LIFFragment(
        fragment_path="person.employmentLearningExperience",
        fragment=[employment_learning_experience_1_dict, employment_learning_experience_2_dict],
    )
    lif_record_json = {"person": [{"foo": "foo"}]}
    lif_record = LIFRecord(**lif_record_json)
    new_lif_record = compose_with_single_fragment(lif_record, lif_fragment)
    assert lif_record.person[0]["foo"] == "foo"
    assert "employmentLearningExperience" not in lif_record.person[0]
    assert new_lif_record.person[0]["foo"] == "foo"
    assert new_lif_record.person[0]["employmentLearningExperience"][0] == employment_learning_experience_1_dict
    assert new_lif_record.person[0]["employmentLearningExperience"][1] == employment_learning_experience_2_dict


def test_compose_for_fragment_list_with_one_multi_item_fragment_and_lif_record_with_existing_nonempty_array():
    lif_fragment1 = LIFFragment(
        fragment_path="person.employmentLearningExperience", fragment=[employment_learning_experience_1_dict]
    )
    lif_fragment2 = LIFFragment(
        fragment_path="person.employmentLearningExperience",
        fragment=[employment_learning_experience_2_dict, employment_learning_experience_3_dict],
    )
    lif_record_json = {
        "person": [{"foo": "foo", "employmentLearningExperience": [employment_learning_experience_4_dict]}]
    }
    lif_record = LIFRecord(**lif_record_json)
    new_lif_record = compose_with_fragment_list(lif_record, [lif_fragment1, lif_fragment2])
    assert lif_record.person[0]["foo"] == "foo"
    assert lif_record.person[0]["employmentLearningExperience"] == [employment_learning_experience_4_dict]
    assert new_lif_record.person[0]["foo"] == "foo"
    # Issue #1165: a multi-item fragment replaces too, and ordering across fragments holds.
    assert new_lif_record.person[0]["employmentLearningExperience"] == [
        employment_learning_experience_1_dict,
        employment_learning_experience_2_dict,
        employment_learning_experience_3_dict,
    ]


# --- Issue #1165 regression -------------------------------------------------------
#
# The demo outage: the query cache's `save` loads the stored record, composes freshly
# fetched source fragments onto it, and writes the whole thing back. While composition
# appended, every cache refresh re-added data the record already had. One demo learner
# reached 1,272 copies of the same Name and a single query returned 6.3MB -- past the
# Advisor model's context window, so every conversation failed.


def test_repeated_composition_of_the_same_fragments_is_idempotent():
    """The core guarantee: refreshing N times must not grow the record N times."""
    fragments = [
        LIFFragment(fragment_path="person.identifier", fragment=[identifier_1_dict, identifier_2_dict]),
        LIFFragment(
            fragment_path="person.employmentLearningExperience", fragment=[employment_learning_experience_1_dict]
        ),
    ]
    record = LIFRecord(**{"person": [{"foo": "foo"}]})

    for _ in range(25):
        record = compose_with_fragment_list(record, fragments)

    assert record.person[0]["identifier"] == [identifier_1_dict, identifier_2_dict]
    assert record.person[0]["employmentLearningExperience"] == [employment_learning_experience_1_dict]
    assert record.person[0]["foo"] == "foo"


def test_repeated_composition_grows_without_bound_in_append_mode():
    """Documents the old behavior, so the reason for the default is visible in the suite."""
    fragments = [LIFFragment(fragment_path="person.identifier", fragment=[identifier_1_dict])]
    record = LIFRecord(**{"person": [{"foo": "foo"}]})

    for _ in range(25):
        record = compose_with_fragment_list(record, fragments, replace_existing=False)

    assert len(record.person[0]["identifier"]) == 25


def test_paths_absent_from_the_fragment_list_are_left_alone():
    """A partial refresh must not wipe data it says nothing about."""
    record = LIFRecord(
        **{
            "person": [
                {
                    "identifier": [identifier_1_dict],
                    "employmentLearningExperience": [employment_learning_experience_4_dict],
                }
            ]
        }
    )

    new_record = compose_with_fragment_list(
        record, [LIFFragment(fragment_path="person.identifier", fragment=[identifier_3_dict])]
    )

    assert new_record.person[0]["identifier"] == [identifier_3_dict]
    assert new_record.person[0]["employmentLearningExperience"] == [employment_learning_experience_4_dict]


def test_replacing_an_absent_path_is_not_an_error():
    record = LIFRecord(**{"person": [{"foo": "foo"}]})

    new_record = compose_with_fragment_list(
        record, [LIFFragment(fragment_path="person.identifier", fragment=[identifier_1_dict])]
    )

    assert new_record.person[0]["identifier"] == [identifier_1_dict]


def test_empty_fragment_list_leaves_the_record_untouched():
    record = LIFRecord(**{"person": [{"identifier": [identifier_1_dict, identifier_2_dict]}]})

    new_record = compose_with_fragment_list(record, [])

    assert new_record.person[0]["identifier"] == [identifier_1_dict, identifier_2_dict]


def test_an_already_duplicated_record_collapses_on_the_next_compose():
    """The demo recovery path: no manual data surgery needed.

    Demo org1 already holds thousands of duplicate entries from before the fix. Because
    composition now replaces, the first cache refresh after deploying this collapses the
    bloated arrays back to the source truth on its own.
    """
    bloated = LIFRecord(
        **{
            "person": [
                {
                    "identifier": [identifier_1_dict] * 1272,
                    "employmentLearningExperience": [employment_learning_experience_1_dict] * 5096,
                }
            ]
        }
    )
    assert len(bloated.person[0]["identifier"]) == 1272

    healed = compose_with_fragment_list(
        bloated,
        [
            LIFFragment(fragment_path="person.identifier", fragment=[identifier_1_dict, identifier_2_dict]),
            LIFFragment(
                fragment_path="person.employmentLearningExperience", fragment=[employment_learning_experience_1_dict]
            ),
        ],
    )

    assert healed.person[0]["identifier"] == [identifier_1_dict, identifier_2_dict]
    assert healed.person[0]["employmentLearningExperience"] == [employment_learning_experience_1_dict]
