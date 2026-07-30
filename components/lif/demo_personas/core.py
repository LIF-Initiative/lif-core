# cspell:disable
"""Curated demo learner personas — the single source of truth for the six demo
learners used across LIF demo surfaces.

Both the Advisor app (`bases/lif/advisor_restapi`) and the LDE test/export
playground (#1036) need the *same* set of demo learners. Keeping the list here,
in one shared brick, avoids a second copy drifting (see #1055 / #1000).

The data is synthetic and safe to surface in demo UIs. `username` is the
Advisor's demo-login account; the LDE playground uses only the learner identity
(name + identifier), and can ignore `username`.
"""

from dataclasses import dataclass, asdict
from typing import Any


@dataclass(frozen=True)
class DemoPersona:
    """A single demo learner."""

    username: str
    firstname: str
    lastname: str
    identifier: str
    identifier_type: str
    identifier_type_enum: str


_DEMO_PERSONAS: list[DemoPersona] = [
    DemoPersona(
        "atsatrian_lifdemo@stateu.edu", "Alan", "Tsatrian", "100001", "SCHOOL_ASSIGNED_NUMBER", "SCHOOL_ASSIGNED_NUMBER"
    ),
    DemoPersona(
        "jdiaz_lifdemo@stateu.edu", "Jenna", "Diaz", "100002", "SCHOOL_ASSIGNED_NUMBER", "SCHOOL_ASSIGNED_NUMBER"
    ),
    DemoPersona(
        "smarin_lifdemo@stateu.edu", "Sarah", "Marin", "100003", "SCHOOL_ASSIGNED_NUMBER", "SCHOOL_ASSIGNED_NUMBER"
    ),
    DemoPersona(
        "Rgreen11Fdemo@stateu.edu", "Renee", "Green", "100004", "SCHOOL_ASSIGNED_NUMBER", "SCHOOL_ASSIGNED_NUMBER"
    ),
    DemoPersona(
        "tthatcher_lifdemo@stateu.edu",
        "Tracy",
        "Thatcher",
        "100006",
        "SCHOOL_ASSIGNED_NUMBER",
        "SCHOOL_ASSIGNED_NUMBER",
    ),
    DemoPersona(
        "mhanson_lifdemo@stateu.edu", "Matt", "Hanson", "100005", "SCHOOL_ASSIGNED_NUMBER", "SCHOOL_ASSIGNED_NUMBER"
    ),
]


def get_demo_personas() -> list[DemoPersona]:
    """Return the curated demo personas (a fresh list; entries are immutable)."""
    return list(_DEMO_PERSONAS)


def get_demo_personas_as_dicts() -> list[dict[str, Any]]:
    """Personas as plain dicts — e.g. for the Advisor's ``users_db`` or a JSON
    response served to the LDE playground."""
    return [asdict(p) for p in _DEMO_PERSONAS]
