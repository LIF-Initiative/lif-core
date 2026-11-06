#!/usr/bin/env python3
"""Generate the SQL that rebuilds MDR DataModelId 4 (CEDS) from the CEDS Ontology v14.0.0.0.

The rules it applies are written up in README.md beside it ("Rules"); comments below name the
README heading each rule comes from. Reads its inputs, verifies each against its pinned SHA-256
hash, and writes:

  ceds_model_4_update.sql   one transaction: Phase 1 retirement (soft deletes by explicit row id,
                            guarded to model 4), then Phase 2 build (value sets, entities,
                            attributes, references); idempotent -- a second run finds every row
                            already in place
  build_report.json         every count the README's "Verification" section expects, as computed here

Inputs:
  CEDS-Ontology-v14.0.0.0.rdf   CEDStandards/CEDS-Ontology, tag V14.0.0.0, src/CEDS-Ontology.rdf.
                                The authority for classes, properties, concept schemes and members.
  CEDS-V14.0.0.0.xlsx           CEDStandards/CEDS-Elements, the tabular extract of the same release.
                                Read only to cross-check the RDF; the RDF wins (README: Sources).
  iso-639-3.tab                 SIL's ISO 639-3 code table; read for its Part1 column only, which
                                caps ISO6393LanguageCode (README: Value sets).
  model_4_before.json           DataModelId 4 as the seed held it before this build: the rows the
                                retirement soft-deletes by id.

The two CEDS files are 32 MB together, so they are not committed: they are downloaded from their
pinned tag and commit into .cache/ (git-ignored) on first run. The other two are committed.

Run with plain Python (stdlib only): `python3 build_ceds_model.py`.
"""

# cspell:ignore skos rdfs owl xsd plpgsql timestamptz jsonb qjson vsid gYear nonNegativeInteger anyURI
# cspell:ignore spreadsheetml iterparse SCED NAICS

import collections
import hashlib
import io
import json
import os
import re
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from typing import Any

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, ".cache")
DM = 4
SOURCE_MODEL = "CEDS v14"
ORG = "LIF"
BUILD_DATE = "2026-11-05"
RELEASE_DATE = "2026-03-11"

RDF_FILE = "CEDS-Ontology-v14.0.0.0.rdf"
RDF_URL = "https://raw.githubusercontent.com/CEDStandards/CEDS-Ontology/V14.0.0.0/src/CEDS-Ontology.rdf"
RDF_SHA256 = "26d782b6047236e84ba181f1ee38030560fad65e2cce9b47acc5062c212255e3"
XLSX_FILE = "CEDS-V14.0.0.0.xlsx"
XLSX_URL = (
    "https://raw.githubusercontent.com/CEDStandards/CEDS-Elements/"
    "b5937e8a0f19c1c660e1e122ad6561c200a1bcde/CEDS-V14.0.0.0.xlsx"
)
XLSX_SHA256 = "a92c2d4239dc682ac408de94e728c368196d47b71199f78288db8414cdc1f523"
ISO_FILE = "iso-639-3.tab"
ISO_SHA256 = "07ce5fed94472312bdd1a4bd7f297c83e7cd4ac4ff335dfbed0824a270f482ed"
BEFORE_FILE = "model_4_before.json"

RDF = "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}"
RDFS = "{http://www.w3.org/2000/01/rdf-schema#}"
OWL = "{http://www.w3.org/2002/07/owl#}"
SKOS = "{http://www.w3.org/2004/02/skos/core#}"
DC = "{http://purl.org/dc/elements/1.1/}"
SCHEMA = "{https://schema.org/}"
CEDS = "{https://w3id.org/CEDStandards/terms/}"
CEDS_NS = "https://w3id.org/CEDStandards/terms/"
XSD_NS = "http://www.w3.org/2001/XMLSchema#"

# ---------------------------------------------------------------------------------------------
# Rule constants (README: Rules)
# ---------------------------------------------------------------------------------------------

# README "Typing": DataType is copied verbatim into the OpenAPI `type`, so only these values are written.
# A range other than the one the type names exactly is kept in Notes as `format:`.
LITERAL_TYPES = {
    "string": "string",
    "token": "string",
    "anyURI": "string",
    "date": "string",
    "dateTime": "string",
    "time": "string",
    "gYear": "number",
    "decimal": "number",
    "int": "number",
    "integer": "number",
    "nonNegativeInteger": "number",
    "byte": "number",
}
FORMAT_SILENT = {"string", "decimal"}
# README "Typing": one property's range is written as the bare CURIE `dc:format` (a format name, so a string).
OTHER_LITERAL_RANGES = {"dc:format": "string"}
# README "Typing": the CEDS facets the MDR columns cannot carry, kept in Notes under their CEDS names.
FACETS = ["textFormat", "maxLength", "minLength", "minInclusive", "maxInclusive", "decimalPlaces"]

# README "Entities": the six pre-build entities kept and remediated in place (id -> CEDS class).
KEPT_ENTITIES = {
    14: "AssessmentForm",
    15: "AssessmentPerformanceLevel",
    18: "AssessmentResult",
    19: "AssessmentRegistration",
    198: "Employment",
    307: "ProgramParticipation",
}
# README "Entities": the twelve retired entities that name the CEDS v14 classes replacing them.
# The other seven retired entities have no CEDS v14 counterpart and carry no note.
RETIRED_REPLACEMENTS = {
    12: ["Assessment", "AssessmentRegistration", "AssessmentResult", "AssessmentSubtest"],
    13: ["Goal", "GoalMeasurement"],
    17: ["AssessmentParticipantSession", "AssessmentSession"],
    20: ["AssessmentParticipantSession", "AssessmentSession"],
    54: ["CompetencyDefinition", "CompetencyDefinitionAssociation", "CompetencyFramework"],
    90: ["Course", "CourseSection", "OrganizationCalendarSession", "OrganizationIdentification", "OrganizationTitle"],
    91: ["CareerAndTechnicalCourse", "CourseSection", "K12Course"],
    92: ["PostsecondaryStudentSection"],
    93: ["PostsecondaryStudentSection", "StudentCourseSectionEnrollment"],
    147: [
        "AdultEducationCourse",
        "CareerAndTechnicalCourse",
        "CompetencyDefinition",
        "CredentialDefinition",
        "CredentialDefinitionCategory",
        "CredentialDefinitionCriteriaDefinition",
        "CredentialDefinitionIdentification",
        "K12Course",
        "OrganizationSalaryScheduleSalary",
        "PostsecondaryCourse",
        "PostsecondaryProgram",
        "PostsecondarySection",
        "ProgramParticipationAdultEducation",
        "ProgramParticipationCareerAndTechnical",
        "WorkforceProgramParticipation",
    ],
    264: [
        "LocationAddress",
        "OrganizationEmail",
        "PersonBirthplace",
        "PersonEmailAddress",
        "PersonFamily",
        "PersonIdentification",
        "PersonName",
        "PersonPersonalInformationVerification",
        "PersonResidency",
        "Telephone",
    ],
    306: [
        "AdultEducationCourse",
        "CareerAndTechnicalCourse",
        "CredentialDefinition",
        "K12Course",
        "K12ProgramOrService",
        "K12StudentGraduationPlan",
        "OrganizationIdentification",
        "OrganizationTitle",
        "PostsecondaryCourse",
        "PostsecondaryProgram",
        "PostsecondarySection",
        "PostsecondaryStudentEnrollment",
        "PostsecondaryStudentProgram",
        "Program",
        "ProgramParticipationAdultEducation",
        "ProgramParticipationCareerAndTechnical",
        "StaffCredential",
        "WorkforceProgramParticipation",
    ],
}

# README "Value sets": schemes up to this size are loaded in full; of the larger ones, these eight are
# loaded in full by decision, and ISO6393LanguageCode is capped to the codes with an ISO 639-1 equivalent.
FULL_LOAD_MAX = 100
FULL_LOAD_LARGE = {
    "SCEDCourseCode",
    "EmploymentNAICSCode",
    "TribalAffiliation",
    "ISO6392LanguageCode",
    "CountryCode",
    "FinancialExpenditureObjectCode",
    "ISO6395LanguageFamily",
    "FinancialAccountRevenueCode",
}
CAPPED_SCHEME = "ISO6393LanguageCode"
# README "Value sets": the one legacy value set whose name is also a CEDS v14 scheme. It is remediated in place,
# like the kept entities, so the CEDS -> LIF mappings on its values keep their rows; values are matched by code.
REMEDIATED_VALUE_SETS = {277: "StateAbbreviation"}
# A placeholder definition CEDS ships on one of the duplicated members (README: Value sets).
PLACEHOLDER_DEFINITION = "PutDefinitionHere"

DEPRECATED_PREFIX = "(Deprecated)"
DEPRECATION_DATE = f"{RELEASE_DATE}T00:00:00Z"

# ---------------------------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------------------------


def _source(name: str, expected_sha256: str, url: str | None = None) -> bytes:
    """A pinned input: committed beside this file, or downloaded into .cache/ from its pinned URL."""
    path = os.path.join(HERE, name) if url is None else os.path.join(CACHE, name)
    if url is not None and not os.path.exists(path):
        os.makedirs(CACHE, exist_ok=True)
        print(f"downloading {url}")
        with urllib.request.urlopen(url) as response:
            data = response.read()
        with open(path, "wb") as f:
            f.write(data)
    with open(path, "rb") as f:
        raw = f.read()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != expected_sha256:
        raise SystemExit(
            f"{name}: SHA-256 {actual} does not match the pinned hash ({expected_sha256}); refusing to build"
        )
    return raw


rdf_root = ET.fromstring(_source(RDF_FILE, RDF_SHA256, RDF_URL))
xlsx_raw = _source(XLSX_FILE, XLSX_SHA256, XLSX_URL)
iso_rows = _source(ISO_FILE, ISO_SHA256).decode("utf-8").splitlines()
with open(os.path.join(HERE, BEFORE_FILE), encoding="utf-8") as f:
    before = json.load(f)

version = rdf_root.find(f"{OWL}Ontology/{OWL}versionInfo")
assert version is not None and version.text == "14.0.0.0", version


def about(node: ET.Element) -> str:
    return node.get(f"{RDF}about") or ""


def resources(node: ET.Element, tag: str) -> list[str]:
    return [x.get(f"{RDF}resource") or "" for x in node.findall(tag)]


def text(node: ET.Element, tag: str) -> str | None:
    value = node.findtext(tag)
    return value.strip() if value and value.strip() else None


# README "Sources": a term is in the model when it carries a dc:identifier. That excludes the ontology's own
# metadata vocabulary (editHistoryEntry, localUsageEntry and the properties that describe them).
classes = {about(n): n for n in rdf_root if n.tag == f"{RDFS}Class" and n.find(f"{DC}identifier") is not None}
props = {about(n): n for n in rdf_root if n.tag == f"{RDF}Property" and n.find(f"{DC}identifier") is not None}
schemes = {about(n): n for n in rdf_root if n.tag == f"{OWL}Class" and n.find(f"{DC}identifier") is not None}
members: dict[str, list[ET.Element]] = collections.defaultdict(list)
for n in rdf_root:
    if n.tag == f"{OWL}NamedIndividual":
        in_scheme = resources(n, f"{SKOS}inScheme")
        assert len(in_scheme) == 1 and in_scheme[0] in schemes, (about(n), in_scheme)
        members[in_scheme[0]].append(n)

assert len(classes) == 402 and len(props) == 2324 and len(schemes) == 965, (len(classes), len(props), len(schemes))
assert sum(len(m) for m in members.values()) == 19546

# ---------------------------------------------------------------------------------------------
# Rules stated in code
# ---------------------------------------------------------------------------------------------


def clean(notation: str) -> str:
    """README "Naming": the technical name (skos:notation) without the `(Deprecated)` prefix or any whitespace."""
    name = notation.replace(DEPRECATED_PREFIX, "", 1) if notation.startswith(DEPRECATED_PREFIX) else notation
    name = re.sub(r"\s+", "", name)
    assert re.fullmatch(r"[A-Za-z][A-Za-z0-9*-]*", name), notation
    return name


def notation(node: ET.Element) -> str:
    value = node.findtext(f"{SKOS}notation")
    assert value is not None, about(node)
    return value


def identifier(node: ET.Element) -> str:
    value = node.findtext(f"{DC}identifier")
    assert value is not None, about(node)
    return value.strip()


def definition(node: ET.Element) -> str | None:
    return text(node, f"{SKOS}definition") or text(node, f"{DC}description")


def notation_note(node: ET.Element) -> list[str]:
    raw = notation(node)
    return [f"CEDS v14 skos:notation: {raw}"] if clean(raw) != raw else []


def change_descriptions(node: ET.Element) -> list[str]:
    return [
        d.strip()
        for d in (e.findtext(f"{CEDS}changeDescription") for e in node.iter(f"{CEDS}editHistoryEntry"))
        if d and d.strip()
    ]


def is_deprecated(node: ET.Element) -> bool:
    return node.find(f"{OWL}deprecated") is not None


def deprecation_statement(node: ET.Element) -> str:
    """README "Deprecation": the CEDS statement is the edit-history entry that records the deprecation."""
    statements = [d for d in change_descriptions(node) if "deprecated" in d.lower()]
    assert statements, about(node)
    return statements[-1]


def use_considerations(node: ET.Element) -> str | None:
    parts = [p for p in [text(node, f"{RDFS}comment")] if p]
    if is_deprecated(node):
        parts.append(f"Deprecated in CEDS: {deprecation_statement(node)}")
    return "\n".join(parts) or None


class_name = {c: clean(notation(n)) for c, n in classes.items()}
scheme_name = {s: clean(notation(n)) for s, n in schemes.items()}
assert len(set(class_name.values())) == len(class_name)
assert len(set(scheme_name.values())) == len(scheme_name)
CLASS_BY_NAME = {v: k for k, v in class_name.items()}

# README "Naming": two pairs of properties share a technical name; each keeps it as Name and is told apart
# by a `_<dc:identifier>` suffix (P######) wherever a key must be unique.
prop_name = {p: clean(notation(n)) for p, n in props.items()}
name_counts = collections.Counter(prop_name.values())
prop_key = {p: (f"{name}_{identifier(props[p])}" if name_counts[name] > 1 else name) for p, name in prop_name.items()}
assert sorted(k for k in prop_key.values() if "_P" in k) == [
    "LearningResourceIdentifier_P001750",
    "LearningResourceIdentifier_P002027",
    "hasIndividualizedProgramMeetingAttendee_P600161",
    "hasIndividualizedProgramMeetingAttendee_P600553",
], sorted(k for k in prop_key.values() if "_P" in k)


def range_of(prop_id: str) -> str:
    ranges = resources(props[prop_id], f"{SCHEMA}rangeIncludes")
    assert len(ranges) == 1, (prop_id, ranges)
    return ranges[0]


def domains_of(prop_id: str) -> list[str]:
    domains = resources(props[prop_id], f"{SCHEMA}domainIncludes")
    assert domains and all(d in classes for d in domains), (prop_id, domains)
    return domains


def kind_of(prop_id: str) -> str:
    """README "References" and "Typing": a class range is a reference, a scheme range an enum, else a literal."""
    r = range_of(prop_id)
    if r in classes:
        return "reference"
    if r in schemes:
        return "enum"
    assert r in OTHER_LITERAL_RANGES or (r.startswith(XSD_NS) and r[len(XSD_NS) :] in LITERAL_TYPES), (prop_id, r)
    return "literal"


def attribute_type_and_notes(prop_id: str) -> tuple[str, list[str]]:
    node = props[prop_id]
    notes = [f"property: {identifier(node)}"] + notation_note(node)
    r = range_of(prop_id)
    if r in schemes:
        data_type = "enum"
        notes.append(f"rangeIncludes: {identifier(schemes[r])} ({scheme_name[r]})")
    elif r in OTHER_LITERAL_RANGES:
        data_type = OTHER_LITERAL_RANGES[r]
        notes.append(f"rangeIncludes: {r}")
    else:
        xsd = r[len(XSD_NS) :]
        data_type = LITERAL_TYPES[xsd]
        if xsd not in FORMAT_SILENT:
            notes.append(f"format: xsd:{xsd}")
    for facet in FACETS:
        value = text(node, f"{CEDS}{facet}")
        if value is not None:
            notes.append(f"{facet}: {value}")
    domains = domains_of(prop_id)
    if len(domains) > 1:
        notes.append("domainIncludes: " + "; ".join(class_name[d] for d in domains))
    return data_type, notes


# ---------------------------------------------------------------------------------------------
# Cross-check against the xlsx (README: Sources)
# ---------------------------------------------------------------------------------------------

XL = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def xlsx_sheets() -> dict[str, list[dict[str, str]]]:
    book = zipfile.ZipFile(io.BytesIO(xlsx_raw))
    shared = [
        "".join(t.text or "" for t in si.iter(f"{XL}t"))
        for si in ET.fromstring(book.read("xl/sharedStrings.xml")).iter(f"{XL}si")
    ]
    workbook = ET.fromstring(book.read("xl/workbook.xml"))
    names = [s.get("name") or "" for s in workbook.iter(f"{XL}sheet")]
    sheets: dict[str, list[dict[str, str]]] = {}
    for index, name in enumerate(names, start=1):
        if name not in ("Classes", "Concept Schemes", "Properties", "Named Individuals"):
            continue
        header: list[str] = []
        rows: list[dict[str, str]] = []
        for _, el in ET.iterparse(book.open(f"xl/worksheets/sheet{index}.xml")):
            if el.tag != f"{XL}row":
                continue
            cells: dict[int, str] = {}
            for c in el.iter(f"{XL}c"):
                ref = re.match(r"[A-Z]+", c.get("r") or "")
                assert ref
                column = 0
                for ch in ref.group(0):
                    column = column * 26 + ord(ch) - 64
                v = c.findtext(f"{XL}v")
                if c.get("t") == "s" and v is not None:
                    v = shared[int(v)]
                elif c.get("t") == "inlineStr":
                    v = "".join(t.text or "" for t in c.iter(f"{XL}t"))
                cells[column - 1] = v or ""
            values = [cells.get(i, "") for i in range(max(cells) + 1)] if cells else []
            if not header:
                header = values
            else:
                rows.append(dict(zip(header, values)))
            el.clear()
        sheets[name] = rows
    return sheets


sheets = xlsx_sheets()
xlsx_disagreements: dict[str, Any] = collections.OrderedDict()
for sheet, nodes, column in (
    ("Classes", classes, "Technical Name (skos:notation)"),
    ("Concept Schemes", schemes, "Technical Name (skos:notation)"),
    ("Properties", props, "Technical Name (skos:notation)"),
):
    xl = {r["IRI"].strip(): r for r in sheets[sheet] if r.get("IRI", "").strip()}
    only_rdf = sorted(set(nodes) - set(xl))
    only_xlsx = sorted(set(xl) - set(nodes))
    names_differ = sorted(i for i in set(nodes) & set(xl) if xl[i][column].strip() != notation(nodes[i]).strip())
    xlsx_disagreements[sheet] = {
        "only_in_rdf": only_rdf,
        "only_in_xlsx": only_xlsx,
        "technical_name_differs": names_differ,
    }
xl_members = {r["IRI"].strip() for r in sheets["Named Individuals"] if r.get("IRI", "").strip()}
rdf_members = {about(m) for ms in members.values() for m in ms}
xlsx_disagreements["Named Individuals"] = {
    "only_in_rdf": len(rdf_members - xl_members),
    "only_in_xlsx": len(xl_members - rdf_members),
}

# ---------------------------------------------------------------------------------------------
# SQL emission
# ---------------------------------------------------------------------------------------------

out: list[str] = []
report: dict[str, Any] = collections.OrderedDict()


def q(v: Any) -> str:
    """SQL literal (standard_conforming_strings: only quotes need escaping)."""
    if v is None or v == "":
        return "NULL"
    return "'" + str(v).replace("'", "''") + "'"


def qjson(obj: Any) -> str:
    body = json.dumps(obj, ensure_ascii=False)
    assert "$j$" not in body
    return "$j$" + body + "$j$::jsonb"


def qts(deprecated: bool) -> str:
    return f"{q(DEPRECATION_DATE)}::timestamptz" if deprecated else "NULL"


def w(s: str = "") -> None:
    out.append(s)


def banner(s: str) -> None:
    w()
    w("-- " + "=" * 92)
    w(f"-- {s}")
    w("-- " + "=" * 92)


def id_list(ids: list[int]) -> str:
    return ",".join(str(i) for i in sorted(ids))


w(f"-- CEDS (MDR DataModelId 4) rebuild from {RDF_FILE}. The rules are in README.md beside this file.")
w(f"-- Generated by build_ceds_model.py on {BUILD_DATE}. Do not edit by hand; rerun the generator.")
w("-- One transaction. Idempotent: soft deletes name the exact rows and touch model 4 only, and every insert is")
w("-- guarded by the live-row lookup the database's own unique indexes use.")
w("BEGIN;")
w("SET search_path TO public;")
w("SET standard_conforming_strings = on;")

# ---- Phase 1: retirement -------------------------------------------------------------------------
banner("Phase 1 -- retirement (soft deletes; nothing cascades, so each table is named)")

# Every row is named by id AND guarded by its model-4 ownership, so the SQL cannot touch another model's
# rows on a database whose ids differ from the seed's.
assert before["data_model"]["Id"] == DM
assert all(e["DataModelId"] == DM and not e["Deleted"] for e in before["entities"])
assert all(a["DataModelId"] == DM and not a["Deleted"] for a in before["attributes"])
assert all(not x["Deleted"] for x in before["entity_attribute_associations"])
assert {x["EntityId"] for x in before["entity_attribute_associations"]} <= {e["Id"] for e in before["entities"]}
assert before["entity_associations"] == []
before_entities = {e["Id"]: e for e in before["entities"]}
for old_id, name in KEPT_ENTITIES.items():
    assert before_entities[old_id]["UniqueName"] == name and name in CLASS_BY_NAME, (old_id, name)
retired_entities = sorted(set(before_entities) - set(KEPT_ENTITIES))
assert len(retired_entities) == 19 and set(RETIRED_REPLACEMENTS) <= set(retired_entities)
for old_id, replacements in RETIRED_REPLACEMENTS.items():
    assert all(r in CLASS_BY_NAME for r in replacements), (old_id, replacements)

# README "Value sets": the legacy value sets bound to the old attributes are retired with them; the others,
# which carry the CEDS -> LIF value crosswalk, stay.
bound_sets = sorted({a["ValueSetId"] for a in before["attributes"] if a["ValueSetId"] is not None})
assert bound_sets == [38, 39, 40, 41, 73, 328, 331, 332, 333], bound_sets
retired_values = [v["Id"] for v in before["value_set_values"] if v["ValueSetId"] in bound_sets]
assert all(not v["Deleted"] for v in before["value_set_values"] if v["ValueSetId"] in bound_sets)
retired_mappings = [m["Id"] for m in before["value_set_value_mappings"] if not m["Deleted"]]
before_sets = {s["Id"]: s for s in before["value_sets"]}
for set_id, name in REMEDIATED_VALUE_SETS.items():
    assert before_sets[set_id]["Name"] == name and not before_sets[set_id]["Deleted"] and set_id not in bound_sets
legacy_sets_kept = sorted(
    s["Name"]
    for s in before["value_sets"]
    if s["Id"] not in bound_sets and s["Id"] not in REMEDIATED_VALUE_SETS and not s["Deleted"]
)
assert len(legacy_sets_kept) == 67 and not set(legacy_sets_kept) & set(scheme_name.values())
assert len(retired_values) == 583 and len(retired_mappings) == 583, (len(retired_values), len(retired_mappings))

MODEL_ENTITIES = f'(SELECT "Id" FROM "Entities" WHERE "DataModelId" = {DM})'
RETIRED_VALUE_IDS = (
    f'(SELECT "Id" FROM "ValueSetValues" WHERE "DataModelId" = {DM} AND "ValueSetId" IN ({id_list(bound_sets)}))'
)
w(f"-- The {len(retired_mappings)} value mappings from the retired values to LIF.")
w(
    f'UPDATE "ValueSetValueMapping" SET "Deleted" = true WHERE "Id" IN ({id_list(retired_mappings)}) '
    f'AND ("SourceValueId" IN {RETIRED_VALUE_IDS} OR "TargetValueId" IN {RETIRED_VALUE_IDS}) AND "Deleted" IS NOT TRUE;'
)
w(f"-- The {len(bound_sets)} legacy value sets bound to the old attributes and their {len(retired_values)} values.")
w(
    f'UPDATE "ValueSetValues" SET "Deleted" = true WHERE "Id" IN ({id_list(retired_values)}) '
    f'AND "DataModelId" = {DM} AND "Deleted" IS NOT TRUE;'
)
w(
    f'UPDATE "ValueSets" SET "Deleted" = true WHERE "Id" IN ({id_list(bound_sets)}) '
    f'AND "DataModelId" = {DM} AND "Deleted" IS NOT TRUE;'
)
old_associations = [x["Id"] for x in before["entity_attribute_associations"]]
old_attributes = [a["Id"] for a in before["attributes"]]
w(
    f"-- All {len(old_attributes)} old attributes and their {len(old_associations)} associations, kept entities included."
)
w(
    f'UPDATE "EntityAttributeAssociation" SET "Deleted" = true WHERE "Id" IN ({id_list(old_associations)}) '
    f'AND "EntityId" IN {MODEL_ENTITIES} AND "Deleted" IS NOT TRUE;'
)
w(
    f'UPDATE "Attributes" SET "Deleted" = true WHERE "Id" IN ({id_list(old_attributes)}) '
    f'AND "DataModelId" = {DM} AND "Deleted" IS NOT TRUE;'
)
w(
    f"-- The {len(retired_entities)} retired entities; {len(RETIRED_REPLACEMENTS)} name the CEDS v14 classes that replace them."
)
for old_id, replacements in sorted(RETIRED_REPLACEMENTS.items()):
    note = "Retired. Replaced by CEDS v14 classes: " + ", ".join(replacements) + "."
    w(f'UPDATE "Entities" SET "UseConsiderations" = {q(note)} WHERE "Id" = {old_id} AND "DataModelId" = {DM};')
w(
    f'UPDATE "Entities" SET "Deleted" = true WHERE "Id" IN ({id_list(retired_entities)}) '
    f'AND "DataModelId" = {DM} AND "Deleted" IS NOT TRUE;'
)
report["retirement"] = {
    "entities": len(retired_entities),
    "entities_with_replacement_note": len(RETIRED_REPLACEMENTS),
    "entities_kept": {str(k): v for k, v in KEPT_ENTITIES.items()},
    "attributes": len(old_attributes),
    "entity_attribute_associations": len(old_associations),
    "value_sets": len(bound_sets),
    "value_set_values": len(retired_values),
    "value_set_value_mappings": len(retired_mappings),
    "legacy_value_sets_kept": len(legacy_sets_kept),
    "legacy_value_sets_remediated": {str(k): v for k, v in REMEDIATED_VALUE_SETS.items()},
}

# ---- Phase 2: the model row ------------------------------------------------------------------------
banner("Phase 2 -- DataModels row 4: CEDS v14 / 14.0.0.0, Notes record the sources")
model_notes = (
    f"Tracks CEDS Ontology v14.0.0.0 (released {RELEASE_DATE}; terms namespace {CEDS_NS}; owl:versionInfo 14.0.0.0)."
    f" Built from {RDF_FILE} (CEDStandards/CEDS-Ontology, tag V14.0.0.0, src/CEDS-Ontology.rdf; SHA-256 {RDF_SHA256})"
    f" and cross-checked against {XLSX_FILE} (CEDStandards/CEDS-Elements; SHA-256 {XLSX_SHA256}); the RDF is the"
    " authority where the two disagree. ISO6393LanguageCode is capped using the Part1 column of SIL's iso-639-3.tab"
    f" (SHA-256 {ISO_SHA256}). Generator, rules and verification: projects/lif_mdr_database/data_models/ceds/ in the"
    " lif-core repository."
)
model_use = (
    "CEDS declares no cardinality: Required and Array are not set on any element, and every association has Array"
    " false. A property whose range is a CEDS class is a Reference association named by the property, not an"
    " attribute. Class hierarchy (rdfs:subClassOf) is recorded in entity Notes, not as associations, and properties"
    " are not inherited down it."
)
w(
    f'UPDATE "DataModels" SET "Name" = {q("CEDS v14")}, "DataModelVersion" = {q("14.0.0.0")}, '
    f'"Notes" = {q(model_notes)}, "UseConsiderations" = {q(model_use)} WHERE "Id" = {DM};'
)

# ---- temp functions -----------------------------------------------------------------------------
banner("Temporary helpers (dropped at the end)")
w(
    f"""
CREATE OR REPLACE FUNCTION public.ceds_tmp_valueset(
    p_name text, p_description text, p_use text, p_notes text, p_deprecation timestamptz, p_values jsonb
) RETURNS bigint AS $fn$
DECLARE v_id bigint; v jsonb; v_vid bigint;
BEGIN
    SELECT "Id" INTO v_id FROM public."ValueSets"
     WHERE "DataModelId" = {DM} AND "Name" = p_name AND "Deleted" IS NOT TRUE LIMIT 1;
    IF v_id IS NULL THEN
        INSERT INTO public."ValueSets"
            ("Name","Description","UseConsiderations","Notes","DataModelId","DeprecationDate","ContributorOrganization",
             "Extension","Deleted")
        VALUES (p_name, p_description, p_use, p_notes, {DM}, p_deprecation, {q(ORG)}, false, false)
        RETURNING "Id" INTO v_id;
    ELSE
        UPDATE public."ValueSets"
           SET "Description" = p_description, "UseConsiderations" = p_use, "Notes" = p_notes,
               "DeprecationDate" = p_deprecation, "ContributorOrganization" = {q(ORG)}
         WHERE "Id" = v_id;
    END IF;
    FOR v IN SELECT * FROM jsonb_array_elements(p_values) LOOP
        SELECT "Id" INTO v_vid FROM public."ValueSetValues"
         WHERE "ValueSetId" = v_id AND "ValueName" = v->>'n' AND "Deleted" IS NOT TRUE LIMIT 1;
        IF v_vid IS NULL THEN
            INSERT INTO public."ValueSetValues"
                ("ValueSetId","Value","ValueName","Description","UseConsiderations","Notes","DeprecationDate",
                 "DataModelId","Source","ContributorOrganization","Extension","Deleted")
            VALUES (v_id, v->>'v', v->>'n', v->>'d', v->>'u', v->>'notes', (v->>'dep')::timestamptz,
                    {DM}, {q(SOURCE_MODEL)}, {q(ORG)}, false, false);
        ELSE
            UPDATE public."ValueSetValues"
               SET "Value" = v->>'v', "Description" = v->>'d', "UseConsiderations" = v->>'u', "Notes" = v->>'notes',
                   "DeprecationDate" = (v->>'dep')::timestamptz, "Source" = {q(SOURCE_MODEL)},
                   "ContributorOrganization" = {q(ORG)}
             WHERE "Id" = v_vid;
        END IF;
    END LOOP;
    RETURN v_id;
END $fn$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION public.ceds_tmp_entity(
    p_name text, p_description text, p_use text, p_notes text
) RETURNS bigint AS $fn$
DECLARE v_id bigint;
BEGIN
    SELECT "Id" INTO v_id FROM public."Entities"
     WHERE "DataModelId" = {DM} AND "UniqueName" = p_name AND "Deleted" IS NOT TRUE LIMIT 1;
    IF v_id IS NULL THEN
        INSERT INTO public."Entities"
            ("Name","UniqueName","Description","UseConsiderations","Required","Array","SourceModel","DataModelId",
             "Notes","ContributorOrganization","Extension","Deleted","LevelOfAccess","Queryable","Modifiable")
        VALUES (p_name, p_name, p_description, p_use, NULL, NULL, {q(SOURCE_MODEL)}, {DM},
                p_notes, {q(ORG)}, false, false, 'Public', false, false)
        RETURNING "Id" INTO v_id;
    ELSE
        UPDATE public."Entities"
           SET "Name" = p_name, "Description" = p_description, "UseConsiderations" = p_use, "Required" = NULL,
               "Array" = NULL, "SourceModel" = {q(SOURCE_MODEL)}, "Notes" = p_notes, "DeprecationDate" = NULL,
               "ContributorOrganization" = {q(ORG)}, "Extension" = false, "LevelOfAccess" = 'Public',
               "Queryable" = false, "Modifiable" = false
         WHERE "Id" = v_id;
    END IF;
    RETURN v_id;
END $fn$ LANGUAGE plpgsql;

-- One attribute row per CEDS property, associated to each of its domain classes. CEDS declares no
-- cardinality, so Required and Array stay NULL and every association has Array false (README: Cardinality).
CREATE OR REPLACE FUNCTION public.ceds_tmp_attr(
    p_unique_name text, p_name text, p_description text, p_use text, p_datatype text, p_valueset text,
    p_notes text, p_deprecation timestamptz, p_entities jsonb
) RETURNS bigint AS $fn$
DECLARE v_id bigint; v_vsid bigint; v_eid bigint; e text;
BEGIN
    IF p_valueset IS NOT NULL THEN
        SELECT "Id" INTO v_vsid FROM public."ValueSets"
         WHERE "DataModelId" = {DM} AND "Name" = p_valueset AND "Deleted" IS NOT TRUE LIMIT 1;
        IF v_vsid IS NULL THEN
            RAISE EXCEPTION 'Value set % not found for attribute %', p_valueset, p_unique_name;
        END IF;
    END IF;
    SELECT "Id" INTO v_id FROM public."Attributes"
     WHERE "DataModelId" = {DM} AND "UniqueName" = p_unique_name AND "Deleted" IS NOT TRUE LIMIT 1;
    IF v_id IS NULL THEN
        INSERT INTO public."Attributes"
            ("Name","UniqueName","Description","UseConsiderations","DataModelId","DataType","ValueSetId","TargetEntityId",
             "Required","Array","SourceModel","Notes","DeprecationDate","ContributorOrganization","Extension","Deleted",
             "LevelOfAccess","Queryable","Modifiable")
        VALUES (p_name, p_unique_name, p_description, p_use, {DM}, p_datatype, v_vsid, NULL,
                NULL, NULL, {q(SOURCE_MODEL)}, p_notes, p_deprecation, {q(ORG)}, false, false,
                'Public', false, false)
        RETURNING "Id" INTO v_id;
    ELSE
        UPDATE public."Attributes"
           SET "Name" = p_name, "Description" = p_description, "UseConsiderations" = p_use, "DataType" = p_datatype,
               "ValueSetId" = v_vsid, "TargetEntityId" = NULL, "Required" = NULL, "Array" = NULL,
               "SourceModel" = {q(SOURCE_MODEL)}, "Notes" = p_notes, "DeprecationDate" = p_deprecation,
               "ContributorOrganization" = {q(ORG)}, "Extension" = false
         WHERE "Id" = v_id;
    END IF;
    FOR e IN SELECT * FROM jsonb_array_elements_text(p_entities) LOOP
        SELECT "Id" INTO v_eid FROM public."Entities"
         WHERE "DataModelId" = {DM} AND "UniqueName" = e AND "Deleted" IS NOT TRUE LIMIT 1;
        IF v_eid IS NULL THEN
            RAISE EXCEPTION 'Domain entity % not found for attribute %', e, p_unique_name;
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM public."EntityAttributeAssociation"
             WHERE "EntityId" = v_eid AND "AttributeId" = v_id AND "ExtendedByDataModelId" IS NULL AND "Deleted" IS NOT TRUE
        ) THEN
            INSERT INTO public."EntityAttributeAssociation"
                ("EntityId","AttributeId","Deleted","ExtendedByDataModelId","ContributorOrganization","Name","Array")
            VALUES (v_eid, v_id, false, NULL, {q(ORG)}, p_name, false);
        ELSE
            UPDATE public."EntityAttributeAssociation" SET "Name" = p_name, "Array" = false
             WHERE "EntityId" = v_eid AND "AttributeId" = v_id AND "ExtendedByDataModelId" IS NULL AND "Deleted" IS NOT TRUE;
        END IF;
    END LOOP;
    RETURN v_id;
END $fn$ LANGUAGE plpgsql;

-- One Reference association per class-ranged domain row (README: References). Relationship stays NULL: the
-- association's Name is the key the generator reads.
CREATE OR REPLACE FUNCTION public.ceds_tmp_ref(
    p_parent text, p_child text, p_name text, p_notes text, p_deprecation timestamptz
) RETURNS bigint AS $fn$
DECLARE v_id bigint; v_pid bigint; v_cid bigint;
BEGIN
    SELECT "Id" INTO v_pid FROM public."Entities"
     WHERE "DataModelId" = {DM} AND "UniqueName" = p_parent AND "Deleted" IS NOT TRUE LIMIT 1;
    SELECT "Id" INTO v_cid FROM public."Entities"
     WHERE "DataModelId" = {DM} AND "UniqueName" = p_child AND "Deleted" IS NOT TRUE LIMIT 1;
    IF v_pid IS NULL OR v_cid IS NULL THEN
        RAISE EXCEPTION 'Reference % -> % (%): entity not found', p_parent, p_child, p_name;
    END IF;
    SELECT "Id" INTO v_id FROM public."EntityAssociation"
     WHERE "ParentEntityId" = v_pid AND "Name" = p_name AND "ExtendedByDataModelId" IS NULL AND "Deleted" IS NOT TRUE LIMIT 1;
    IF v_id IS NULL THEN
        INSERT INTO public."EntityAssociation"
            ("ParentEntityId","ChildEntityId","Relationship","Placement","Notes","DeprecationDate","ContributorOrganization",
             "Deleted","Extension","ExtendedByDataModelId","Name","Array")
        VALUES (v_pid, v_cid, NULL, 'Reference', p_notes, p_deprecation, {q(ORG)}, false, false, NULL, p_name, false)
        RETURNING "Id" INTO v_id;
    ELSE
        UPDATE public."EntityAssociation"
           SET "ChildEntityId" = v_cid, "Relationship" = NULL, "Placement" = 'Reference', "Notes" = p_notes,
               "DeprecationDate" = p_deprecation, "Array" = false, "ContributorOrganization" = {q(ORG)}
         WHERE "Id" = v_id;
    END IF;
    RETURN v_id;
END $fn$ LANGUAGE plpgsql;
"""
)

# ---- value sets (README: Value sets) ------------------------------------------------------------
banner("Phase 2 -- 965 concept schemes as value sets")
iso_header = iso_rows[0].split("\t")
iso_part1 = {
    row["Id"]
    for row in (dict(zip(iso_header, line.split("\t"))) for line in iso_rows[1:] if line.strip())
    if row["Part1"]
}
assert len(iso_part1) == 184, len(iso_part1)

value_count = 0
values_by_rule: collections.Counter = collections.Counter()
duplicate_codes_dropped: list[dict[str, str]] = []
names_disambiguated: list[dict[str, str]] = []
deprecated_values = 0
deprecated_schemes = 0
empty_schemes: list[str] = []
large_schemes: dict[str, int] = {}
for scheme_id, node in schemes.items():
    name = scheme_name[scheme_id]
    all_members = members[scheme_id]
    if len(all_members) > FULL_LOAD_MAX:
        large_schemes[name] = len(all_members)
    if name == CAPPED_SCHEME:
        chosen = [m for m in all_members if notation(m).strip() in iso_part1]
        rule = "capped"
    elif len(all_members) <= FULL_LOAD_MAX or name in FULL_LOAD_LARGE:
        chosen = list(all_members)
        rule = "full" if len(all_members) <= FULL_LOAD_MAX else "full_large"
    else:
        raise AssertionError(f"scheme {name} has {len(all_members)} members and no load rule")
    if not all_members:
        empty_schemes.append(name)

    # README "Value sets": a code listed twice is loaded once -- the non-deprecated row, then the one with a
    # real definition, then the first in file order.
    by_code: dict[str, list[ET.Element]] = collections.defaultdict(list)
    for m in chosen:
        by_code[notation(m).strip()].append(m)
    kept: list[ET.Element] = []
    for code, rows in by_code.items():
        best = sorted(
            rows, key=lambda m: (is_deprecated(m), definition(m) in (None, PLACEHOLDER_DEFINITION), rows.index(m))
        )[0]
        kept.append(best)
        for m in rows:
            if m is not best:
                duplicate_codes_dropped.append(
                    {"scheme": name, "code": code, "dropped": identifier(m), "kept": identifier(best)}
                )
    kept.sort(key=chosen.index)

    # README "Value sets": ValueName is the preferred label; a label shared by two codes becomes `Label (code)`.
    labels = collections.Counter(text(m, f"{SKOS}prefLabel") for m in kept)
    values = []
    for m in kept:
        label = text(m, f"{SKOS}prefLabel")
        code = notation(m).strip()
        assert label and code, about(m)
        value_name = f"{label} ({code})" if labels[label] > 1 else label
        if value_name != label:
            names_disambiguated.append({"scheme": name, "code": code, "value_name": value_name})
        notes = [f"concept: {identifier(m)}"]
        if value_name != label:
            notes.append(f"prefLabel: {label}")
        deprecated = is_deprecated(m)
        deprecated_values += deprecated
        values.append(
            {
                "v": code,
                "n": value_name,
                "d": definition(m),
                "u": use_considerations(m),
                "notes": "\n".join(notes),
                "dep": DEPRECATION_DATE if deprecated else None,
            }
        )
    assert len({v["n"] for v in values}) == len(values), name
    values_by_rule[rule] += len(values)
    value_count += len(values)

    notes = [f"scheme: {identifier(node)}"] + notation_note(node)
    use = use_considerations(node)
    if name == CAPPED_SCHEME:
        cap = (
            f"Capped: holds the {len(values)} of the {len(all_members)} CEDS v14 codes that have an ISO 639-1"
            " equivalent (a Part1 code in SIL's iso-639-3.tab). The full code list is in the CEDS ontology."
        )
        use = f"{use}\n{cap}" if use else cap
    deprecated_schemes += is_deprecated(node)
    remediated = [set_id for set_id, set_name in REMEDIATED_VALUE_SETS.items() if set_name == name]
    for set_id in remediated:
        # Rename each legacy value by id to its CEDS label, so the helper below finds and updates it in place.
        by_value = {v["v"]: v["n"] for v in values}
        legacy = [v for v in before["value_set_values"] if v["ValueSetId"] == set_id]
        assert legacy and all(v["Value"] in by_value for v in legacy), name
        for v in legacy:
            w(
                f'UPDATE "ValueSetValues" SET "ValueName" = {q(by_value[v["Value"]])} WHERE "Id" = {v["Id"]} '
                f'AND "ValueSetId" = {set_id} AND "DataModelId" = {DM} AND "Value" = {q(v["Value"])} AND "Deleted" IS NOT TRUE;'
            )
        report.setdefault("remediated_value_sets", {})[name] = {
            "id": set_id,
            "legacy_values_kept": len(legacy),
            "values_added": len(values) - len(legacy),
        }
    w(
        f"SELECT public.ceds_tmp_valueset({q(name)}, {q(definition(node))}, {q(use)}, {q(chr(10).join(notes))}, "
        f"{qts(is_deprecated(node))}, {qjson(values)});"
    )
assert value_count == 11810, value_count
assert len(duplicate_codes_dropped) == 3, duplicate_codes_dropped
assert set(large_schemes) == FULL_LOAD_LARGE | {CAPPED_SCHEME}, sorted(large_schemes)
assert values_by_rule["capped"] == 183, values_by_rule
assert deprecated_schemes == 1 and deprecated_values == 25, (deprecated_schemes, deprecated_values)
report["value_sets"] = {
    "schemes": len(schemes),
    "values": value_count,
    "values_by_load_rule": dict(values_by_rule),
    "members_in_source": sum(len(m) for m in members.values()),
    "large_schemes_in_source": dict(sorted(large_schemes.items())),
    "empty_schemes": empty_schemes,
    "duplicate_codes_dropped": duplicate_codes_dropped,
    "value_names_disambiguated": names_disambiguated,
    "deprecated_schemes": deprecated_schemes,
    "deprecated_values": deprecated_values,
}

# ---- entities (README: Entities, Hierarchy) ------------------------------------------------------
banner("Phase 2 -- 402 entities, one per CEDS class (six keep their pre-build ids)")
hierarchy_notes = 0
restriction_notes = 0
for class_id, node in classes.items():
    notes = [f"class: {identifier(node)}"] + notation_note(node)
    for parent in node.findall(f"{RDFS}subClassOf"):
        target = parent.get(f"{RDF}resource")
        if target is not None:
            assert target in classes, (class_id, target)
            notes.append(f"subClassOf: {class_name[target]}")
            hierarchy_notes += 1
            continue
        restriction = parent.find(f"{OWL}Restriction")
        assert restriction is not None, class_id
        on_property = resources(restriction, f"{OWL}onProperty")
        all_values = resources(restriction, f"{OWL}allValuesFrom")
        assert len(on_property) == 1 and len(all_values) == 1, class_id
        labels = [prop_key.get(r, r.replace(CEDS_NS, "")) for r in on_property + all_values]
        notes.append(f"restriction: onProperty {labels[0]} allValuesFrom {labels[1]}")
        restriction_notes += 1
    w(
        f"SELECT public.ceds_tmp_entity({q(class_name[class_id])}, {q(definition(node))}, "
        f"{q(use_considerations(node))}, {q(chr(10).join(notes))});"
    )
report["entities"] = {
    "total": len(classes),
    "kept_ids": len(KEPT_ENTITIES),
    "new": len(classes) - len(KEPT_ENTITIES),
    "subclass_of_notes": hierarchy_notes,
    "restriction_notes": restriction_notes,
}

# ---- attributes and references (README: References, Typing) -------------------------------------
banner("Phase 2 -- 2,324 properties: class-ranged ones become references, the rest attributes")

# README "Naming" safety: under one parent, every attribute and reference key is distinct.
keys_by_parent: dict[str, list[str]] = collections.defaultdict(list)
for prop_id in props:
    for d in domains_of(prop_id):
        keys_by_parent[d].append(prop_key[prop_id] if kind_of(prop_id) == "reference" else prop_name[prop_id])
assert all(len(k) == len(set(k)) for k in keys_by_parent.values())

data_types: collections.Counter = collections.Counter()
attribute_count = 0
attribute_association_count = 0
shared_attributes = 0
reference_properties = 0
reference_count = 0
self_references = 0
deprecated_props: list[str] = []
for prop_id, node in props.items():
    deprecated = is_deprecated(node)
    if deprecated:
        deprecated_props.append(prop_key[prop_id])
    domains = domains_of(prop_id)
    if kind_of(prop_id) == "reference":
        reference_properties += 1
        child = range_of(prop_id)
        notes = [f"property: {identifier(node)}"] + notation_note(node)
        description = definition(node)
        if description:
            notes.append(f"description: {description}")
        use = use_considerations(node)
        if use:
            notes.append(f"useConsiderations: {use}")
        for d in domains:
            reference_count += 1
            self_references += d == child
            w(
                f"SELECT public.ceds_tmp_ref({q(class_name[d])}, {q(class_name[child])}, {q(prop_key[prop_id])}, "
                f"{q(chr(10).join(notes))}, {qts(deprecated)});"
            )
        continue
    data_type, notes = attribute_type_and_notes(prop_id)
    data_types[data_type] += 1
    attribute_count += 1
    attribute_association_count += len(domains)
    shared_attributes += len(domains) > 1
    r = range_of(prop_id)
    value_set = scheme_name[r] if r in schemes else None
    w(
        f"SELECT public.ceds_tmp_attr({q(prop_key[prop_id])}, {q(prop_name[prop_id])}, {q(definition(node))}, "
        f"{q(use_considerations(node))}, {q(data_type)}, {q(value_set)}, {q(chr(10).join(notes))}, "
        f"{qts(deprecated)}, {qjson([class_name[d] for d in domains])});"
    )
assert data_types == collections.Counter({"enum": 994, "string": 727, "number": 252}), data_types
assert attribute_count == 1973 and attribute_association_count == 2277, (attribute_count, attribute_association_count)
assert reference_properties == 351 and reference_count == 473, (reference_properties, reference_count)
assert len(deprecated_props) == 3, deprecated_props
report["attributes"] = {
    "total": attribute_count,
    "shared_by_several_classes": shared_attributes,
    "associations": attribute_association_count,
    "data_types": dict(data_types),
}
report["references"] = {
    "properties": reference_properties,
    "associations": reference_count,
    "self_references": self_references,
}
report["deprecated_properties"] = deprecated_props

# ---- end ------------------------------------------------------------------------------------------
banner("Done")
w("DROP FUNCTION IF EXISTS public.ceds_tmp_ref(text,text,text,text,timestamptz);")
w("DROP FUNCTION IF EXISTS public.ceds_tmp_attr(text,text,text,text,text,text,text,timestamptz,jsonb);")
w("DROP FUNCTION IF EXISTS public.ceds_tmp_entity(text,text,text,text);")
w("DROP FUNCTION IF EXISTS public.ceds_tmp_valueset(text,text,text,text,timestamptz,jsonb);")
w("COMMIT;")

with open(os.path.join(HERE, "ceds_model_4_update.sql"), "w", encoding="utf-8") as f:
    f.write("\n".join(out) + "\n")

report["xlsx_cross_check"] = xlsx_disagreements
with open(os.path.join(HERE, "build_report.json"), "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2, ensure_ascii=False)
    f.write("\n")

print(f"wrote ceds_model_4_update.sql ({len(out)} lines) and build_report.json")
print(json.dumps({k: v for k, v in report.items() if k not in ("value_sets", "xlsx_cross_check")}, indent=1))
print("xlsx cross-check:", json.dumps(xlsx_disagreements))
