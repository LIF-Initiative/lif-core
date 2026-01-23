"""Sample data loader for integration tests.

Dynamically loads sample data from the projects/mongodb/sample_data directory.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class PersonData:
    """Container for a single person's data from sample files."""

    filename: str
    raw_data: dict[str, Any]
    org_id: str

    @property
    def person(self) -> dict[str, Any]:
        """Get the first Person record from the data."""
        persons = self.raw_data.get("Person", [])
        if not persons:
            raise ValueError(f"No Person data found in {self.filename}")
        return persons[0]

    @property
    def organizations(self) -> list[dict[str, Any]]:
        """Get Organization records from the data."""
        return self.raw_data.get("Organization", [])

    @property
    def first_name(self) -> str:
        """Extract first name from Person.Name."""
        names = self.person.get("Name", [])
        if names:
            return names[0].get("firstName", "").strip()
        return ""

    @property
    def last_name(self) -> str:
        """Extract last name from Person.Name."""
        names = self.person.get("Name", [])
        if names:
            return names[0].get("lastName", "").strip()
        return ""

    @property
    def full_name(self) -> str:
        """Get full name as 'FirstName LastName'."""
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def school_assigned_number(self) -> str | None:
        """Extract SCHOOL_ASSIGNED_NUMBER identifier if present."""
        identifiers = self.person.get("Identifier", [])
        for ident in identifiers:
            if ident.get("identifierType") == "SCHOOL_ASSIGNED_NUMBER":
                return ident.get("identifier")
        return None

    def get_entity_count(self, entity_type: str) -> int:
        """Count entities of a given type within the Person record."""
        return len(self.person.get(entity_type, []))


@dataclass
class SampleDataLoader:
    """Loads and provides access to sample data for a specific org."""

    org_id: str
    sample_data_key: str
    _persons: list[PersonData] = field(default_factory=list, init=False)
    _loaded: bool = field(default=False, init=False)

    @staticmethod
    def get_sample_data_root() -> Path:
        """Get the root path for sample data files."""
        # Support running from project root or integration_tests directory
        candidates = [
            Path(__file__).parent.parent.parent / "projects" / "mongodb" / "sample_data",
            Path.cwd() / "projects" / "mongodb" / "sample_data",
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        raise FileNotFoundError(
            f"Could not find sample_data directory. Tried: {candidates}"
        )

    def _load(self) -> None:
        """Load all sample data files for this org."""
        if self._loaded:
            return

        root = self.get_sample_data_root()
        org_dir = root / self.sample_data_key

        if not org_dir.exists():
            raise FileNotFoundError(f"Sample data directory not found: {org_dir}")

        for json_file in sorted(org_dir.glob("*.json")):
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                self._persons.append(
                    PersonData(
                        filename=json_file.name,
                        raw_data=data,
                        org_id=self.org_id,
                    )
                )

        self._loaded = True

    @property
    def persons(self) -> list[PersonData]:
        """Get all person records for this org."""
        self._load()
        return self._persons

    def get_person_by_name(self, first_name: str) -> PersonData | None:
        """Find a person by their first name."""
        self._load()
        for person in self._persons:
            if person.first_name.lower() == first_name.lower():
                return person
        return None

    def get_person_by_school_number(self, school_number: str) -> PersonData | None:
        """Find a person by their school assigned number."""
        self._load()
        for person in self._persons:
            if person.school_assigned_number == school_number:
                return person
        return None

    def get_all_school_numbers(self) -> list[str]:
        """Get all school assigned numbers for this org."""
        self._load()
        numbers = []
        for person in self._persons:
            num = person.school_assigned_number
            if num:
                numbers.append(num)
        return numbers


def load_all_orgs() -> dict[str, SampleDataLoader]:
    """Load sample data for all configured organizations."""
    from .ports import ORG_PORTS

    loaders = {}
    for org_id, ports in ORG_PORTS.items():
        if ports.sample_data_key:
            loaders[org_id] = SampleDataLoader(
                org_id=org_id,
                sample_data_key=ports.sample_data_key,
            )
    return loaders
