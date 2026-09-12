"""Integration tests for Query Cache layer.

Verifies that the Query Cache API reads from and writes to MongoDB correctly.

The write-path tests (#1200) exist because the unit tests for these endpoints run
against a mocked collection, which cannot reproduce MongoDB's own semantics --
matching, array handling, or the difference between an update that matched and one
that did not. Only two containers are needed:

    docker compose up -d mongodb-org1 lif-query-cache-org1

or, from the repo root, ``scripts/run-query-cache-integration-tests.sh``.
"""

from typing import Any

import pytest

from utils.ports import OrgPorts
from utils.sample_data import SampleDataLoader


@pytest.mark.layer("query_cache")
class TestQueryCacheDataIntegrity:
    """Tests for Query Cache data integrity."""

    def _make_query_payload(
        self, identifier: str, identifier_type: str = "SCHOOL_ASSIGNED_NUMBER", selected_fields: list[str] | None = None
    ) -> dict[str, Any]:
        """Build a LIFQuery payload for the Query Cache API."""
        if selected_fields is None:
            # Request all common person fields
            selected_fields = [
                "Person.Name",
                "Person.Contact",
                "Person.Identifier",
                "Person.CredentialAward",
                "Person.CourseLearningExperience",
                "Person.EmploymentLearningExperience",
                "Person.Proficiency",
                "Person.PositionPreferences",
                "Person.EmploymentPreferences",
            ]

        return {
            "filter": {"Person": {"Identifier": {"identifier": identifier, "identifierType": identifier_type}}},
            "selected_fields": selected_fields,
        }

    def test_query_cache_health(
        self, org_id: str, org_ports: OrgPorts, http_client: Any, require_query_cache: None
    ) -> None:
        """Verify Query Cache API is responding."""
        response = http_client.get(f"{org_ports.query_cache_url}/")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data

    def test_query_returns_person_by_school_number(
        self,
        org_id: str,
        org_ports: OrgPorts,
        sample_data: SampleDataLoader,
        http_client: Any,
        require_query_cache: None,
    ) -> None:
        """Verify Query Cache returns person data by school assigned number."""
        # Get a person from sample data
        persons = sample_data.persons
        if not persons:
            pytest.skip(f"No sample data for {org_id}")

        person_data = persons[0]
        school_num = person_data.school_assigned_number
        if not school_num:
            pytest.skip(f"No school number for {person_data.full_name}")

        payload = self._make_query_payload(school_num)
        response = http_client.post(f"{org_ports.query_cache_url}/query", json=payload)

        assert response.status_code == 200, f"Query Cache query failed: {response.status_code} - {response.text}"

        records = response.json()
        assert len(records) > 0, (
            f"Query Cache returned no records for {person_data.full_name} (school_num: {school_num})"
        )

    def test_all_persons_queryable(
        self,
        org_id: str,
        org_ports: OrgPorts,
        sample_data: SampleDataLoader,
        http_client: Any,
        require_query_cache: None,
    ) -> None:
        """Verify all persons from sample data can be queried."""
        missing_persons = []

        for person_data in sample_data.persons:
            school_num = person_data.school_assigned_number
            if not school_num:
                continue

            payload = self._make_query_payload(school_num)
            response = http_client.post(f"{org_ports.query_cache_url}/query", json=payload)

            if response.status_code != 200:
                missing_persons.append(f"{person_data.full_name} (ID: {school_num}): HTTP {response.status_code}")
                continue

            records = response.json()
            if not records:
                missing_persons.append(f"{person_data.full_name} (ID: {school_num}): no records returned")

        assert not missing_persons, f"{org_id}: Persons not queryable via Query Cache:\n" + "\n".join(
            f"  - {p}" for p in missing_persons
        )

    def test_person_name_matches_sample(
        self,
        org_id: str,
        org_ports: OrgPorts,
        sample_data: SampleDataLoader,
        http_client: Any,
        require_query_cache: None,
    ) -> None:
        """Verify Query Cache returns correct name data."""
        mismatches = []

        for person_data in sample_data.persons:
            school_num = person_data.school_assigned_number
            if not school_num:
                continue

            payload = self._make_query_payload(school_num, selected_fields=["Person.Name"])
            response = http_client.post(f"{org_ports.query_cache_url}/query", json=payload)

            if response.status_code != 200:
                continue

            records = response.json()
            if not records:
                continue

            # Get the person from the response
            # Response format: [{"Person": [{"Name": [...], ...}]}]
            record = records[0]
            person = record.get("Person", record.get("person", []))
            if not person:
                continue

            person_obj = person[0] if isinstance(person, list) else person
            names = person_obj.get("Name", [])
            if not names:
                mismatches.append(f"{person_data.full_name}: No Name in response")
                continue

            response_name = names[0]
            expected_first = person_data.first_name
            expected_last = person_data.last_name
            actual_first = response_name.get("firstName", "").strip()
            actual_last = response_name.get("lastName", "").strip()

            if actual_first != expected_first or actual_last != expected_last:
                mismatches.append(
                    f"{person_data.full_name}: expected '{expected_first} {expected_last}', "
                    f"got '{actual_first} {actual_last}'"
                )

        if mismatches:
            pytest.fail(f"{org_id} name mismatches in Query Cache:\n" + "\n".join(f"  - {m}" for m in mismatches))

    def test_entity_counts_match_sample(
        self,
        org_id: str,
        org_ports: OrgPorts,
        sample_data: SampleDataLoader,
        http_client: Any,
        require_query_cache: None,
    ) -> None:
        """Verify entity counts from Query Cache are at least what sample data expects.

        Query Cache may contain aggregated data from multiple organizations, so actual
        counts may be higher than the sample data for a single org. This test verifies
        that at minimum, the expected data is present (actual >= expected).
        """
        entity_types = ["CredentialAward", "CourseLearningExperience", "EmploymentLearningExperience", "Proficiency"]
        missing_data = []

        for person_data in sample_data.persons:
            school_num = person_data.school_assigned_number
            if not school_num:
                continue

            # Query for all entity types
            selected_fields = [f"Person.{et}" for et in entity_types]
            payload = self._make_query_payload(school_num, selected_fields=selected_fields)

            response = http_client.post(f"{org_ports.query_cache_url}/query", json=payload)

            if response.status_code != 200:
                continue

            records = response.json()
            if not records:
                continue

            record = records[0]
            person = record.get("Person", record.get("person", []))
            if not person:
                continue

            person_obj = person[0] if isinstance(person, list) else person

            for entity_type in entity_types:
                expected_count = person_data.get_entity_count(entity_type)
                actual_count = len(person_obj.get(entity_type, []))

                # Only fail if actual count is LESS than expected (missing data)
                # Allow actual > expected for aggregated data from multiple orgs
                if actual_count < expected_count:
                    missing_data.append(
                        f"{person_data.full_name}.{entity_type}: expected at least {expected_count}, got {actual_count}"
                    )

        if missing_data:
            pytest.fail(f"{org_id} missing entity data in Query Cache:\n" + "\n".join(f"  - {m}" for m in missing_data))


@pytest.mark.layer("query_cache")
class TestQueryCacheWritePath:
    """Tests for the Query Cache write endpoints: /add, /update, /save (#1200).

    The unit tests in ``test/components/lif/query_cache_service/test_core.py`` assert
    the shape of the calls made to a ``MagicMock`` collection. That proves the service
    builds the update it intends to build; it cannot prove MongoDB accepts it, which is
    a different question and the one these tests answer.
    """

    # ---- helpers -------------------------------------------------------------

    def _query_payload(self, identifier: str, selected_fields: list[str]) -> dict[str, Any]:
        return {
            "filter": {
                "Person": {"Identifier": {"identifier": identifier, "identifierType": "SCHOOL_ASSIGNED_NUMBER"}}
            },
            "selected_fields": selected_fields,
        }

    def _update_payload(self, identifier: str, update_input: dict[str, Any]) -> dict[str, Any]:
        return {
            "updatePerson": {"filter": {"Person": {"Identifier": {"identifier": identifier}}}, "input": update_input}
        }

    def _person_from(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        """Pull person[0] out of a /query response, which is a list of records."""
        assert records, "expected at least one record"
        person = records[0]["Person"]
        return person[0] if isinstance(person, list) else person

    def _add(self, http_client: Any, base_url: str, identifier: str) -> dict[str, Any]:
        record = {
            "Person": [
                {
                    "informationSourceId": "Org1",
                    "Identifier": [
                        {
                            "informationSourceId": "Org1",
                            "identifier": identifier,
                            "identifierType": "SCHOOL_ASSIGNED_NUMBER",
                            "informationSourceOrganization": "State University",
                        }
                    ],
                    "Name": [{"informationSourceId": "Org1", "firstName": "Write", "lastName": "Path"}],
                }
            ]
        }
        response = http_client.post(f"{base_url}/add", json=record)
        assert response.status_code == 200, f"/add failed: {response.status_code} - {response.text}"
        return response.json()

    # ---- /add ----------------------------------------------------------------

    def test_add_persists_exactly_what_it_returns(
        self, org_ports: OrgPorts, http_client: Any, require_query_cache: None, write_test_identifier: str
    ) -> None:
        """#179 dropped ``add()``'s post-insert refetch and now returns the input record.

        That is only correct if what MongoDB stored matches what the caller was handed.
        A mocked ``insert_one`` cannot tell us; reading the document back can.
        """
        base_url = org_ports.query_cache_url
        returned = self._add(http_client, base_url, write_test_identifier)

        response = http_client.post(
            f"{base_url}/query", json=self._query_payload(write_test_identifier, ["Person.Name", "Person.Identifier"])
        )
        assert response.status_code == 200, f"/query failed: {response.status_code} - {response.text}"

        persisted = self._person_from(response.json())
        returned_person = returned["Person"][0]
        assert persisted["Name"] == returned_person["Name"]
        assert persisted["Identifier"] == returned_person["Identifier"]

    # ---- /update -------------------------------------------------------------

    def test_update_set_returns_the_updated_document(
        self, org_ports: OrgPorts, http_client: Any, require_query_cache: None, write_test_identifier: str
    ) -> None:
        """A matched ``$set`` answers 200 with the post-update document.

        This pins the behaviour change #179 introduced and left open in #1202's review:
        ``update_one`` + ``find_one`` could 404 after a *successful* write, where
        ``find_one_and_update(..., return_document=AFTER)`` returns the updated document.
        It could not be settled against a ``MagicMock``, whose ``find_one_and_update``
        returns whatever the test told it to; here the answer comes from MongoDB.
        """
        base_url = org_ports.query_cache_url
        self._add(http_client, base_url, write_test_identifier)

        # A scalar directly under Person.0 -- see the xfail below for why not Name.lastName.
        response = http_client.post(
            f"{base_url}/update", json=self._update_payload(write_test_identifier, {"Person": {"nickname": "Writey"}})
        )
        assert response.status_code == 200, f"/update failed: {response.status_code} - {response.text}"
        assert response.json()["Person"][0]["nickname"] == "Writey"

        # ...and the write really landed, rather than only being echoed back.
        readback = http_client.post(
            f"{base_url}/query", json=self._query_payload(write_test_identifier, ["Person.nickname"])
        )
        assert self._person_from(readback.json())["nickname"] == "Writey"

    def test_update_with_no_matching_record_is_404(
        self, org_ports: OrgPorts, http_client: Any, require_query_cache: None, write_test_identifier: str
    ) -> None:
        """The other half of the pinning above: an unmatched filter is still a 404.

        Guards against 'everything returns 200 now' as the response to #179.
        """
        response = http_client.post(
            f"{org_ports.query_cache_url}/update",
            json=self._update_payload(f"{write_test_identifier}-absent", {"Person": {"nickname": "Nobody"}}),
        )
        assert response.status_code == 404, f"expected 404, got {response.status_code} - {response.text}"

    def test_update_append_to_a_field_that_does_not_exist(
        self, org_ports: OrgPorts, http_client: Any, require_query_cache: None, write_test_identifier: str
    ) -> None:
        """``$push`` against an absent field -- the ordinary append path.

        Worth stating precisely, because it is easy to assume this is the case the
        array-initialization write exists for: it is not. MongoDB creates the array itself
        when the field is absent, so this passes with or without that step. The case that
        genuinely needs it is the next test.
        """
        base_url = org_ports.query_cache_url
        self._add(http_client, base_url, write_test_identifier)

        response = http_client.post(
            f"{base_url}/update",
            json=self._update_payload(write_test_identifier, {"Person": {"Proficiency": [{"name": "Welding"}]}}),
        )
        assert response.status_code == 200, f"/update append failed: {response.status_code} - {response.text}"

        readback = http_client.post(
            f"{base_url}/query", json=self._query_payload(write_test_identifier, ["Person.Proficiency"])
        )
        assert self._person_from(readback.json())["Proficiency"] == [{"name": "Welding"}]

    def test_update_append_multiple_elements_uses_each(
        self, org_ports: OrgPorts, http_client: Any, require_query_cache: None, write_test_identifier: str
    ) -> None:
        """A multi-element append must land as separate elements, not one nested list.

        Without the ``$each`` wrapper MongoDB pushes the list itself as a single element.
        The unit test asserts the wrapper is built; this asserts MongoDB agrees.
        """
        base_url = org_ports.query_cache_url
        self._add(http_client, base_url, write_test_identifier)

        response = http_client.post(
            f"{base_url}/update",
            json=self._update_payload(
                write_test_identifier, {"Person": {"Proficiency": [{"name": "Welding"}, {"name": "Milling"}]}}
            ),
        )
        assert response.status_code == 200, f"/update append failed: {response.status_code} - {response.text}"

        readback = http_client.post(
            f"{base_url}/query", json=self._query_payload(write_test_identifier, ["Person.Proficiency"])
        )
        assert self._person_from(readback.json())["Proficiency"] == [{"name": "Welding"}, {"name": "Milling"}]

    def test_update_append_over_a_non_array_field(
        self, org_ports: OrgPorts, http_client: Any, require_query_cache: None, write_test_identifier: str
    ) -> None:
        """``$push`` against a field currently holding a non-array value.

        This is the case ``update()``'s separate array-initialization write exists for:
        MongoDB's ``$push`` raises OperationFailure against a non-array field, so the
        field is first ``$set`` to ``[]``. Removing that step makes this a 500 while every
        other test here still passes, which is how it was found -- the unit suite asserts
        the init call is made, but a mocked collection has no opinion about whether it was
        needed.

        Note the initialization is destructive by design: the scalar is discarded.
        """
        base_url = org_ports.query_cache_url
        self._add(http_client, base_url, write_test_identifier)

        scalar = http_client.post(
            f"{base_url}/update", json=self._update_payload(write_test_identifier, {"Person": {"Hobby": "chess"}})
        )
        assert scalar.status_code == 200, f"setting the scalar failed: {scalar.status_code} - {scalar.text}"

        response = http_client.post(
            f"{base_url}/update",
            json=self._update_payload(write_test_identifier, {"Person": {"Hobby": [{"name": "go"}]}}),
        )
        assert response.status_code == 200, (
            f"/update append over a non-array field failed: {response.status_code} - {response.text}"
        )

        readback = http_client.post(
            f"{base_url}/query", json=self._query_payload(write_test_identifier, ["Person.Hobby"])
        )
        assert self._person_from(readback.json())["Hobby"] == [{"name": "go"}]

    @pytest.mark.xfail(
        reason="#1229: $set into an array-valued entity builds Person.0.<Entity>.<field>, which "
        "MongoDB rejects with OperationFailure -> HTTP 500. Pre-existing; predates #179, whose "
        "66fad9c leaves build_mongo_update_ops untouched. Remove this marker when #1229 lands -- "
        "strict=True means the suite goes red the moment it starts passing.",
        strict=True,
    )
    def test_update_set_a_field_inside_an_array_entity(
        self, org_ports: OrgPorts, http_client: Any, require_query_cache: None, write_test_identifier: str
    ) -> None:
        """``$set`` on a scalar inside an array-valued entity such as ``Name``.

        ``build_mongo_update_ops`` produces ``Person.0.Name.lastName``. Per the data-model
        rules every PascalCase entity is an array, so ``Name`` is a list and MongoDB
        cannot create a field inside it without an index -- it raises OperationFailure,
        which the route turns into a 500.

        The unit suite cannot see this: ``test_update_set_only_uses_single_find_one_and_update``
        asserts exactly ``{"$set": {"Person.0.Name.FamilyName": "Doe"}}`` against a fixture
        whose ``Name`` is a list, and the mock accepts it. This test is xfail(strict) so it
        will announce itself the moment the underlying behaviour is fixed.
        """
        base_url = org_ports.query_cache_url
        self._add(http_client, base_url, write_test_identifier)

        response = http_client.post(
            f"{base_url}/update",
            json=self._update_payload(write_test_identifier, {"Person": {"Name": {"lastName": "Renamed"}}}),
        )
        assert response.status_code == 200, f"/update $set failed: {response.status_code} - {response.text}"

    # ---- /save ---------------------------------------------------------------

    def test_save_creates_a_record_when_none_matches(
        self, org_ports: OrgPorts, http_client: Any, require_query_cache: None, write_test_identifier: str
    ) -> None:
        """``save()`` upserts, so an unmatched filter creates the record.

        Note the route takes two body parameters, so the payload is keyed by argument
        name rather than being a bare filter.
        """
        base_url = org_ports.query_cache_url
        response = http_client.post(
            f"{base_url}/save",
            json={
                "lif_query_filter": {
                    "Person": {
                        "Identifier": {"identifier": write_test_identifier, "identifierType": "SCHOOL_ASSIGNED_NUMBER"}
                    }
                },
                "lif_fragments": [
                    {"fragment_path": "Person.Name", "fragment": [{"firstName": "Saved", "lastName": "One"}]}
                ],
            },
        )
        assert response.status_code == 200, f"/save failed: {response.status_code} - {response.text}"

        readback = http_client.post(
            f"{base_url}/query", json=self._query_payload(write_test_identifier, ["Person.Name"])
        )
        assert self._person_from(readback.json())["Name"] == [{"firstName": "Saved", "lastName": "One"}]

    def test_save_replaces_fragments_rather_than_appending(
        self, org_ports: OrgPorts, http_client: Any, require_query_cache: None, write_test_identifier: str
    ) -> None:
        """#1165: composing with ``replace_existing=True`` must not re-add on every refresh.

        Saving twice is the shape that regressed -- the second save used to append, so a
        record grew a duplicate Name per refresh. ``save()`` returns ``null``, so the
        assertion has to come from reading the record back.
        """
        base_url = org_ports.query_cache_url
        filter_body = {
            "Person": {"Identifier": {"identifier": write_test_identifier, "identifierType": "SCHOOL_ASSIGNED_NUMBER"}}
        }

        for last_name in ("First", "Second"):
            response = http_client.post(
                f"{base_url}/save",
                json={
                    "lif_query_filter": filter_body,
                    "lif_fragments": [
                        {"fragment_path": "Person.Name", "fragment": [{"firstName": "Saved", "lastName": last_name}]}
                    ],
                },
            )
            assert response.status_code == 200, f"/save failed: {response.status_code} - {response.text}"

        readback = http_client.post(
            f"{base_url}/query", json=self._query_payload(write_test_identifier, ["Person.Name"])
        )
        names = self._person_from(readback.json())["Name"]
        assert names == [{"firstName": "Saved", "lastName": "Second"}], (
            f"expected the second save to replace the first, got {names}"
        )
