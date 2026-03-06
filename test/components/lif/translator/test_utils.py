import pytest
from lif.translator.utils import deep_merge, convert_transformation_to_mappings


# ------------------------------ deep_merge tests ------------------------------ #


def test_deep_merge_recurses_on_dicts_and_overwrites_scalars():
    dst = {"a": {"b": 1}, "c": 10}
    src = {"a": {"d": 2}, "c": 99, "e": {"f": 3}}

    out = deep_merge(dst, src)

    # in-place modification and returned object are the same reference
    assert out is dst
    # recursive merge for dicts
    assert dst["a"] == {"b": 1, "d": 2}
    # scalar overwrite
    assert dst["c"] == 99
    # new nested dict copied in
    assert dst["e"] == {"f": 3}


def test_deep_merge_lists_of_dicts_are_merged_by_index():
    dst = {"images": [{"caption": "first"}, {"imageId": "id-2"}]}
    src = {
        "images": [
            {"imageId": "id-1"},  # merges with index 0 in dst
            {"caption": "second"},  # merges with index 1 in dst
            {"imageType": "png"},  # appended as new 3rd element
        ]
    }

    deep_merge(dst, src)

    assert dst == {
        "images": [
            {"caption": "first", "imageId": "id-1"},
            {"imageId": "id-2", "caption": "second"},
            {"imageType": "png"},
        ]
    }


def test_deep_merge_lists_of_primitives_append_unique_only():
    dst = {"tags": ["a", "b", 1]}
    src = {"tags": ["b", "c", 1, 2]}

    deep_merge(dst, src)

    # only new/unique items from src should be appended
    assert dst == {"tags": ["a", "b", 1, "c", 2]}


def test_deep_merge_mixed_list_types_treated_as_append_unique():
    # Not all items are dicts in one or both lists -> use append-unique path
    dst = {"mixed": ["x", {"k": 1}]}
    src = {"mixed": ["x", {"k": 1}, {"k": 2}]}

    deep_merge(dst, src)

    # Strings and dicts are compared by equality; {"k": 1} already present, {"k": 2} is new
    assert dst == {"mixed": ["x", {"k": 1}, {"k": 2}]}


def test_deep_merge_overwrites_when_types_differ():
    # dst has list at key 'x'; src provides scalar -> should overwrite
    dst = {"x": [1, 2, 3]}
    src = {"x": 42}

    deep_merge(dst, src)

    assert dst == {"x": 42}


def test_deep_merge_does_not_alias_source_structures():
    # Ensure deep copies are used so future mutation of src does not affect dst
    dst = {"a": {"b": 1}, "arr": [{"x": 1}]}
    src = {"a": {"c": 2}, "arr": [{"y": 2}]}

    deep_merge(dst, src)

    # mutate src after merge
    src["a"]["c"] = 999
    src["arr"][0]["y"] = 999

    # dst should remain unaffected
    assert dst["a"]["c"] == 2
    assert dst["arr"][0]["y"] == 2


# -------- convert_transformation_to_mappings tests (extraction behaviour) ------- #


def test_convert_transformation_to_mappings_basic_extraction():
    transformation = {"data": [{"TransformationExpression": '{ "a": 1 }'}, {"TransformationExpression": '{ "b": 2 }'}]}

    expressions = convert_transformation_to_mappings(transformation)
    assert expressions == ['{ "a": 1 }', '{ "b": 2 }']


def test_convert_transformation_to_mappings_skips_missing_or_empty():
    transformation = {
        "data": [
            {},  # missing
            {"TransformationExpression": None},  # falsy
            {"TransformationExpression": ""},  # empty string -> falsy -> skipped
            {"TransformationExpression": '{ "ok": true }'},
        ]
    }

    expressions = convert_transformation_to_mappings(transformation)
    assert expressions == ['{ "ok": true }']


def test_convert_transformation_to_mappings_no_data_returns_empty():
    # Empty dict -> no data -> empty list
    assert convert_transformation_to_mappings({}) == []
    # Passing {"data": None} results in a TypeError because the implementation
    # iterates directly over the value returned by transformation.get("data", []).
    # We treat this as invalid input rather than expecting an empty list.
    with pytest.raises(TypeError):
        convert_transformation_to_mappings({"data": None})
