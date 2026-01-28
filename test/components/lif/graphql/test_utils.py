from lif.graphql import utils


def test_to_pascal_case_from_str():
    assert utils.to_pascal_case_from_str("person_name") == "PersonName"


def test_unique_type_name():
    assert utils.unique_type_name("Person", "FilterInput", "Person").endswith("FilterInput")
