# cspell:disable
from dataclasses import FrozenInstanceError

import pytest

from lif.demo_personas import DemoPersona, get_demo_personas, get_demo_personas_as_dicts

EXPECTED_FIELDS = {"username", "firstname", "lastname", "identifier", "identifier_type", "identifier_type_enum"}


def test_returns_thirty_personas():
    personas = get_demo_personas()
    assert len(personas) == 30
    assert all(isinstance(p, DemoPersona) for p in personas)


def test_identifiers_are_the_expected_unique_set():
    ids = [p.identifier for p in get_demo_personas()]
    # the six original personas, then the 24 synthetic learners (#1525)
    assert sorted(ids) == [str(n) for n in (*range(100001, 100007), *range(100101, 100125))]
    assert len(set(ids)) == len(ids)  # unique


def test_as_dicts_has_the_keys_the_advisor_users_db_relies_on():
    dicts = get_demo_personas_as_dicts()
    assert len(dicts) == 30
    for d in dicts:
        assert set(d.keys()) == EXPECTED_FIELDS
        # the Advisor keys demo login off username and surfaces first/last name
        assert d["username"] and d["firstname"] and d["lastname"]
        assert d["identifier_type"] == "SCHOOL_ASSIGNED_NUMBER"


def test_get_returns_a_fresh_list_and_entries_are_immutable():
    # callers can't mutate the shared source
    get_demo_personas().clear()
    assert len(get_demo_personas()) == 30
    with pytest.raises(FrozenInstanceError):
        get_demo_personas()[0].identifier = "999999"  # type: ignore[misc]
