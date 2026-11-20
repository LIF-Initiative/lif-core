# cspell:disable
"""Curated demo learner personas — the single source of truth for the demo
learners used across LIF demo surfaces: the six original personas plus 24
synthetic State University learners (#1525).

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
    # Synthetic State University learners (#1525); records in sample_data/dev-single-org.
    DemoPersona(
        "dokaforbrooks_lifdemo@stateu.edu",
        "Danielle",
        "Okafor-Brooks",
        "100101",
        "SCHOOL_ASSIGNED_NUMBER",
        "SCHOOL_ASSIGNED_NUMBER",
    ),
    DemoPersona(
        "rnguyen_lifdemo@stateu.edu", "Robert", "Nguyen", "100102", "SCHOOL_ASSIGNED_NUMBER", "SCHOOL_ASSIGNED_NUMBER"
    ),
    DemoPersona(
        "mcastilloruiz_lifdemo@stateu.edu",
        "María Fernanda",
        "Castillo Ruiz",
        "100103",
        "SCHOOL_ASSIGNED_NUMBER",
        "SCHOOL_ASSIGNED_NUMBER",
    ),
    DemoPersona(
        "apetrov_lifdemo@stateu.edu",
        "Alexander",
        "Petrov",
        "100104",
        "SCHOOL_ASSIGNED_NUMBER",
        "SCHOOL_ASSIGNED_NUMBER",
    ),
    DemoPersona(
        "jellis_lifdemo@stateu.edu", "Jordan", "Ellis", "100105", "SCHOOL_ASSIGNED_NUMBER", "SCHOOL_ASSIGNED_NUMBER"
    ),
    DemoPersona(
        "trhodes_lifdemo@stateu.edu", "Tamika", "Rhodes", "100106", "SCHOOL_ASSIGNED_NUMBER", "SCHOOL_ASSIGNED_NUMBER"
    ),
    DemoPersona(
        "kwatanabe_lifdemo@stateu.edu",
        "Kenji",
        "Watanabe",
        "100107",
        "SCHOOL_ASSIGNED_NUMBER",
        "SCHOOL_ASSIGNED_NUMBER",
    ),
    DemoPersona(
        "lmoreno_lifdemo@stateu.edu", "Leticia", "Moreno", "100108", "SCHOOL_ASSIGNED_NUMBER", "SCHOOL_ASSIGNED_NUMBER"
    ),
    DemoPersona(
        "bhollis_lifdemo@stateu.edu", "Bryce", "Hollis", "100109", "SCHOOL_ASSIGNED_NUMBER", "SCHOOL_ASSIGNED_NUMBER"
    ),
    DemoPersona(
        "bcallahan_lifdemo@stateu.edu",
        "Brian",
        "Callahan",
        "100110",
        "SCHOOL_ASSIGNED_NUMBER",
        "SCHOOL_ASSIGNED_NUMBER",
    ),
    DemoPersona(
        "mwebb_lifdemo@stateu.edu", "Marcus", "Webb", "100111", "SCHOOL_ASSIGNED_NUMBER", "SCHOOL_ASSIGNED_NUMBER"
    ),
    DemoPersona(
        "ndang_lifdemo@stateu.edu", "Nathan", "Dang", "100112", "SCHOOL_ASSIGNED_NUMBER", "SCHOOL_ASSIGNED_NUMBER"
    ),
    DemoPersona(
        "ctanaka_lifdemo@stateu.edu", "Carlos", "Tanaka", "100113", "SCHOOL_ASSIGNED_NUMBER", "SCHOOL_ASSIGNED_NUMBER"
    ),
    DemoPersona(
        "dibrahim_lifdemo@stateu.edu", "Diego", "Ibrahim", "100114", "SCHOOL_ASSIGNED_NUMBER", "SCHOOL_ASSIGNED_NUMBER"
    ),
    DemoPersona(
        "treyes_lifdemo@stateu.edu", "Terrence", "Reyes", "100115", "SCHOOL_ASSIGNED_NUMBER", "SCHOOL_ASSIGNED_NUMBER"
    ),
    DemoPersona(
        "mabernathy_lifdemo@stateu.edu",
        "Mei",
        "Abernathy",
        "100116",
        "SCHOOL_ASSIGNED_NUMBER",
        "SCHOOL_ASSIGNED_NUMBER",
    ),
    DemoPersona(
        "lbauer_lifdemo@stateu.edu", "Luis", "Bauer", "100117", "SCHOOL_ASSIGNED_NUMBER", "SCHOOL_ASSIGNED_NUMBER"
    ),
    DemoPersona(
        "pkaur_lifdemo@stateu.edu", "Priya", "Kaur", "100118", "SCHOOL_ASSIGNED_NUMBER", "SCHOOL_ASSIGNED_NUMBER"
    ),
    DemoPersona(
        "oromero_lifdemo@stateu.edu", "Omar", "Romero", "100119", "SCHOOL_ASSIGNED_NUMBER", "SCHOOL_ASSIGNED_NUMBER"
    ),
    DemoPersona(
        "nschneider_lifdemo@stateu.edu",
        "Nadia",
        "Schneider",
        "100120",
        "SCHOOL_ASSIGNED_NUMBER",
        "SCHOOL_ASSIGNED_NUMBER",
    ),
    DemoPersona(
        "gwhitaker_lifdemo@stateu.edu",
        "Grace",
        "Whitaker",
        "100121",
        "SCHOOL_ASSIGNED_NUMBER",
        "SCHOOL_ASSIGNED_NUMBER",
    ),
    DemoPersona(
        "snakamura_lifdemo@stateu.edu",
        "Samuel",
        "Nakamura",
        "100122",
        "SCHOOL_ASSIGNED_NUMBER",
        "SCHOOL_ASSIGNED_NUMBER",
    ),
    DemoPersona(
        "ahargrove_lifdemo@stateu.edu",
        "Aaliyah",
        "Hargrove",
        "100123",
        "SCHOOL_ASSIGNED_NUMBER",
        "SCHOOL_ASSIGNED_NUMBER",
    ),
    DemoPersona(
        "dnovak_lifdemo@stateu.edu", "Darius", "Novak", "100124", "SCHOOL_ASSIGNED_NUMBER", "SCHOOL_ASSIGNED_NUMBER"
    ),
]


def get_demo_personas() -> list[DemoPersona]:
    """Return the curated demo personas (a fresh list; entries are immutable)."""
    return list(_DEMO_PERSONAS)


def get_demo_personas_as_dicts() -> list[dict[str, Any]]:
    """Personas as plain dicts — e.g. for the Advisor's ``users_db`` or a JSON
    response served to the LDE playground."""
    return [asdict(p) for p in _DEMO_PERSONAS]
