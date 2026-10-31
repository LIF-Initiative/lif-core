#!/usr/bin/env python3
"""Generate the SQL that rebuilds MDR DataModelId 10 (CTDL) from the CTDL authority file.

Executes claude_CTDL-work-order-v7 (rationale: claude_CTDL-gap-analysis-v2). Reads three inputs
from this directory, verifies the two source files against the hashes pinned in the work order's
§0, and writes:

  ctdl_model_10_update.sql   one transaction: Phase 1 cleanup (soft deletes by explicit row id),
                             then Phase 2 build (value sets, entities, attributes, references);
                             idempotent -- a second run finds every row already in place
  build_report.json          every count the work order's §6.1 / §7 asks for, as computed here

Inputs:
  CTDL-authority-20260927.json           credreg.net CTDL JSON-LD, release 20260927 (§0)
  CTDL-registry-publishing-schema.json   Credential Registry publishing schema; read for the
                                         per-property `multivalue` flag only (§0, §4.4)
  model_10_before.json                   DataModelId 10 as the seed held it before this build;
                                         the rows to soft-delete, and the only source for the
                                         ten attributes carried onto the two retained
                                         deprecated classes (§2.4, §5.2)

Run with plain Python (stdlib only): `python3 build_ctdl_model.py`.
"""

# cspell:ignore ceterms ceasn qdata skos rdfs langString anyURI credreg multivalue vann dct
# cspell:ignore targetscheme plpgsql subclass timestamptz jsonb ctid qjson subclassof vsid

import collections
import hashlib
import json
import os
from typing import Any

HERE = os.path.dirname(os.path.abspath(__file__))
DM = 10
SOURCE_MODEL = "CTDL"
ORG = "LIF"
BUILD_DATE = "2026-10-29"

AUTHORITY_FILE = "CTDL-authority-20260927.json"
AUTHORITY_SHA256 = "5d4410b2350e62a39bd0a57dffec2bcf7c34183102a0a821fdd88b74dd6c4ff9"
REGISTRY_FILE = "CTDL-registry-publishing-schema.json"
REGISTRY_SHA256 = "ae2d046ec8e93884006a413ea795e63485d3d48fad7616a21dd742f3e58638e0"
BEFORE_FILE = "model_10_before.json"

# ---------------------------------------------------------------------------------------------
# Work-order constants
# ---------------------------------------------------------------------------------------------

# §4.2: the DataType map. DataType is copied verbatim into the OpenAPI `type`, so only these values
# are ever written. Dates and durations keep their source format in Notes.
LITERAL_TYPES = {
    "xsd:string": "string",
    "rdf:langString": "string",
    "rdfs:langString": "string",
    "rdfs:Literal": "string",
    "xsd:language": "string",
    "xsd:anyURI": "string",
    "xsd:boolean": "boolean",
    "xsd:integer": "number",
    "xsd:decimal": "number",
    "xsd:float": "number",
    "xsd:date": "string",
    "xsd:dateTime": "string",
    "xsd:duration": "string",
    "schema:Date": "string",
    "schema:Duration": "string",
}
FORMAT_NOTED = {"xsd:date", "xsd:dateTime", "xsd:duration", "schema:Date", "schema:Duration"}
# §4.2 / §4.6: rdfs:Resource and schema:WebPage are strings, but the work order counts their rows with the
# "no resolvable range" set (140 rows / 13 properties), so they carry the `[out of model]` Notes line.
CONCEPT = "skos:Concept"
# §4.2: skos:ConceptScheme is not skos:Concept. Those rows are strings, never enums.
CONCEPT_SCHEME = "skos:ConceptScheme"

# §5.1: Required exists solely so references render. ctid and name wherever present, plus these.
REQUIRED_GENERAL = {"ceterms:ctid", "ceterms:name"}
REQUIRED_BY_CLASS = {
    "ceterms:AlignmentObject": ["ceterms:targetNode", "ceterms:targetNodeName"],
    "ceterms:CredentialAlignmentObject": ["ceterms:targetNode", "ceterms:targetNodeName"],
    "ceterms:CredentialPerson": ["ceterms:givenName", "ceterms:familyName"],
    "ceterms:IdentifierValue": ["ceterms:identifierValueCode", "ceterms:identifierTypeName"],
    "ceterms:JurisdictionProfile": ["ceterms:description", "ceterms:globalJurisdiction"],
    "ceterms:PayProfile": ["schema:value", "ceterms:currency"],
    "ceterms:RevocationProfile": ["ceterms:description", "ceterms:revocationCriteriaDescription"],
    "ceterms:ValueProfile": ["schema:value", "ceterms:creditUnitType"],
    "schema:QuantitativeValue": ["schema:value", "schema:description"],
    "schema:MonetaryAmount": ["schema:value", "schema:description"],
    "elm:Note": ["elm:noteLiteral"],
    "ceterms:DurationProfile": ["ceterms:exactDuration", "ceterms:minimumDuration", "ceterms:maximumDuration"],
    "ceterms:Assessment": ["ceterms:hasRegulatoryInformation"],  # a reference row; marking it does nothing (§5.1)
}

# §3.1: foreign parents that are not modeled get the suffix; these three foreign classes are (§5.3).
MODELED_FOREIGN_CLASSES = {"schema:QuantitativeValue", "schema:MonetaryAmount", "elm:Note"}
FOREIGN_SUFFIX = " [foreign — not modeled]"

# §5.2: the two deprecated classes retained by decision, outside the authority file.
DEPRECATION_DATE = "2021-10-29T00:00:00Z"
RETAINED_CLASSES = {
    # old entity id -> (new entity name, successor)
    63: ("Competency", "ceasn:Competency"),
    62: ("CompetencyFramework", "ceasn:CompetencyFramework"),
}
# Old attribute id -> (new bare name, DataType). Only genuine ceterms terms carry forward; the
# ceasn-namespace attributes on the old rows are dropped. Names and ids come from
# model_10_before.json, the only source these rows exist in.
RETAINED_ATTRIBUTES = {
    62: [  # CompetencyFramework
        (382, "source", "string"),
        (383, "name", "string"),
        (384, "description", "string"),
        (391, "inLanguage", "string"),
    ],
    63: [  # Competency
        (396, "codedNotation", "string"),
        (401, "inLanguage", "string"),
        (406, "environmentalHazardType", "enum"),
        (407, "performanceLevelType", "enum"),
        (409, "physicalCapabilityType", "enum"),
        (410, "sensoryCapabilityType", "enum"),
    ],
}
RETAINED_CLASS_NOTES = {
    "Competency": ["supersededBy: ceasn:Competency"],
    "CompetencyFramework": ["supersededBy: ceasn:CompetencyFramework"],
}
RETAINED_COMMON_NOTES = [
    "changeReason: deprecation of the class; use the ceasn equivalent",
    "reference: Credential Engine Schema-Development issue 785",
    "source: current MDR rows, filtered — not present in any shippable source file",
]

# ---------------------------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------------------------


def _read(name: str, expected_sha256: str | None = None) -> Any:
    path = os.path.join(HERE, name)
    with open(path, "rb") as f:
        raw = f.read()
    if expected_sha256 is not None:
        actual = hashlib.sha256(raw).hexdigest()
        if actual != expected_sha256:
            raise SystemExit(f"{name}: SHA-256 {actual} does not match §0 ({expected_sha256}); refusing to build")
    return json.loads(raw)


authority = _read(AUTHORITY_FILE, AUTHORITY_SHA256)["@graph"]
registry = _read(REGISTRY_FILE, REGISTRY_SHA256)
before = _read(BEFORE_FILE)

classes = {n["@id"]: n for n in authority if n.get("@type") == "rdfs:Class"}
props = {n["@id"]: n for n in authority if n.get("@type") == "rdf:Property"}
schemes = {n["@id"]: n for n in authority if n.get("@type") == "skos:ConceptScheme"}
concepts = {n["@id"]: n for n in authority if n.get("@type") == "skos:Concept"}
multivalue = {p["uri"]: p.get("multivalue") for p in registry["properties"]}

assert len(classes) == 140 and len(props) == 418 and len(schemes) == 36 and len(concepts) == 457, (
    len(classes),
    len(props),
    len(schemes),
    len(concepts),
)
assert len(multivalue) == 403 and sum(1 for v in multivalue.values() if v is True) == 288

# Domain rows, in the file's order: each class lists its properties in meta:domainFor.
rows = [(c, p) for c, node in classes.items() for p in node.get("meta:domainFor", [])]
assert len(rows) == 7753, len(rows)

# ---------------------------------------------------------------------------------------------
# Rules stated in code
# ---------------------------------------------------------------------------------------------


def resolves(range_term: str) -> bool:
    """§4.6 resolving predicate: a range resolves if and only if it is the @id of an rdfs:Class node
    in the authority file, i.e. a class DataModel 10 contains. Literals, skos:Concept,
    skos:ConceptScheme, rdfs:Resource, rdf:Statement, and every ceasn/qdata/asn class are
    unresolved."""
    return range_term in classes


def ranges_of(prop_id: str) -> list[str]:
    """The property's declared ranges, deduplicated, in file order (ceterms:CredentialType is listed
    twice on isSimilarTo)."""
    seen: list[str] = []
    for r in props[prop_id].get("schema:rangeIncludes", []):
        if r not in seen:
            seen.append(r)
    return seen


def is_reference(prop_id: str) -> bool:
    """§4: a domain row is a reference association when at least one range resolves; otherwise it
    is attribute-typed. Applied per range, not per property."""
    return any(resolves(r) for r in ranges_of(prop_id))


def local_name(term: str) -> str:
    """§4.1 naming: bare local name for ceterms terms; every other namespace keeps its prefix."""
    prefix, _, local = term.partition(":")
    return local if prefix == "ceterms" else term


def en(node: dict, key: str) -> Any:
    value = node.get(key)
    if isinstance(value, dict):
        return value.get("en-US") or next(iter(value.values()), None)
    return value


def entity_description(node: dict) -> str | None:
    return en(node, "rdfs:comment") or en(node, "dct:description")


# Ancestry over rdfs:subClassOf inside the file, for the reference-child rule.
parents_of = {c: [p for p in node.get("rdfs:subClassOf", [])] for c, node in classes.items()}


def ancestors(class_id: str) -> set[str]:
    out: set[str] = set()
    stack = list(parents_of.get(class_id, []))
    while stack:
        p = stack.pop()
        if p in out:
            continue
        out.add(p)
        stack.extend(parents_of.get(p, []))
    return out


# Whether a class ends up with at least one Required attribute-typed row, so a reference to it
# renders as a non-empty object (§5.1, §6.3 step 5). Computed before attributes are emitted.
def required_props_for(class_id: str) -> set[str]:
    own = {p for p in classes[class_id].get("meta:domainFor", [])}
    picks = {p for p in REQUIRED_GENERAL if p in own}
    picks |= {p for p in REQUIRED_BY_CLASS.get(class_id, []) if p in own}
    return {p for p in picks if not is_reference(p)}


has_required = {c: bool(required_props_for(c)) for c in classes}


def reference_child(prop_id: str) -> tuple[str, list[str], list[str]]:
    """Which permitted target becomes EntityAssociation.ChildEntityId.

    The work order writes one reference association per domain row with "multiple permitted
    targets" (§4.3). The table holds one ChildEntityId, so the full permitted list is recorded in
    the association's Notes and one target is chosen for the column, deterministically:

      1. the candidate that is an rdfs:subClassOf ancestor (within the file) of the most other
         candidates -- e.g. Organization over its two subclasses, Credential over its 50 subtypes;
      2. on a tie, a candidate with a Required attribute row, so the reference renders non-empty;
      3. on a tie, the first in the file's (alphabetical) order.

    Returns (child, permitted targets in file order, unresolved ranges in file order).
    """
    all_ranges = ranges_of(prop_id)
    permitted = [r for r in all_ranges if resolves(r)]
    # §7.4: an unresolved range is a class-like term the model lacks. Literal and skos:Concept
    # ranges on a reference row are attribute kinds the reference cannot carry; they are noted
    # separately as dropped, not as unresolved.
    unresolved = [r for r in all_ranges if not resolves(r) and r not in LITERAL_TYPES and r != CONCEPT]
    assert permitted, prop_id

    def score(candidate: str) -> tuple[int, int, int]:
        descendants = sum(1 for other in permitted if other != candidate and candidate in ancestors(other))
        return (descendants, 1 if has_required[candidate] else 0, -permitted.index(candidate))

    child = max(permitted, key=score)
    return child, permitted, unresolved


def data_type_for(prop_id: str) -> tuple[str, list[str]]:
    """§4.2 / §4.3 / §4.6 typing for an attribute-typed row: (DataType, extra Notes lines)."""
    rs = ranges_of(prop_id)
    notes: list[str] = []
    kinds: set[str] = set()
    for r in rs:
        if r in LITERAL_TYPES:
            kinds.add(LITERAL_TYPES[r])
        elif r == CONCEPT:
            kinds.add("enum")
        else:
            # skos:ConceptScheme, rdfs:Resource, schema:WebPage, rdf:Statement, foreign classes
            kinds.add("unresolved")
    formats = [r for r in rs if r in FORMAT_NOTED]
    if formats:
        notes.append("format: " + "; ".join(formats))
    if kinds == {"unresolved"}:
        # §4.6: no literal, concept or in-model range -> string, with the ranges in Notes.
        notes.append("rangeIncludes: " + "; ".join(f"{r} [out of model]" for r in rs))
        return "string", notes
    if len(kinds) == 1:
        return next(iter(kinds)), notes
    # §4.3: more than one kind (all-literal mixes, and leftSource / rightSource with
    # rdf:Property + rdfs:Class + rdfs:Literal + skos:Concept) -> the widest type, string, with
    # every declared range enumerated.
    notes.append("rangeIncludes: " + "; ".join(rs))
    return "string", notes


def array_value(prop_id: str) -> str | None:
    """§4.4: Array follows the Registry's multivalue on attribute rows; properties the Registry
    lacks get null."""
    flag = multivalue.get(prop_id)
    if flag is True:
        return "Yes"
    if flag is False:
        return "No"
    return None


def multivalue_note(prop_id: str) -> str:
    flag = multivalue.get(prop_id)
    if flag is None:
        return "multivalue: unknown (property not in the Registry publishing schema)"
    return f"multivalue: {'true' if flag else 'false'}"


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


def w(s: str = "") -> None:
    out.append(s)


def banner(text: str) -> None:
    w()
    w("-- " + "=" * 92)
    w(f"-- {text}")
    w("-- " + "=" * 92)


def id_list(items: list[dict]) -> str:
    return ",".join(str(x["Id"]) for x in items)


w("-- CTDL (MDR DataModelId 10) rebuild from CTDL-authority-20260927.json, per claude_CTDL-work-order-v7.")
w(f"-- Generated by build_ctdl_model.py on {BUILD_DATE}. Do not edit by hand; rerun the generator.")
w("-- One transaction. Idempotent: soft deletes name the exact rows, and every insert is guarded by the")
w("-- live-row lookup the database's own unique indexes use.")
w("BEGIN;")
w("SET search_path TO public;")
w("SET standard_conforming_strings = on;")

# ---- Phase 1: cleanup ---------------------------------------------------------------------------
banner("Phase 1 -- cleanup (soft deletes; nothing cascades, so each table is named)")

group = before["transformation_group"]
assert group["Id"] == 9
w("-- §2.2 transformation group 9 (CTDL_LIF): already soft-deleted in the seed; asserted here, not re-deleted.")
w('UPDATE "TransformationsGroup" SET "Deleted" = true WHERE "Id" = 9 AND "Deleted" IS NOT TRUE;')
w(
    f'UPDATE "Transformations" SET "Deleted" = true WHERE "Id" IN ({id_list(before["transformations"])}) '
    'AND "Deleted" IS NOT TRUE;'
)
w(
    f'UPDATE "TransformationAttributes" SET "Deleted" = true WHERE "Id" IN ({id_list(before["transformation_attributes"])}) '
    'AND "Deleted" IS NOT TRUE;'
)
w("-- §2.3 the 27 value sets, their 112 values, and the 115 mapping rows sourced from them. LIF set 52 stays.")
w(
    f'UPDATE "ValueSetValueMapping" SET "Deleted" = true WHERE "Id" IN ({id_list(before["value_set_value_mappings"])}) '
    'AND "Deleted" IS NOT TRUE;'
)
w(
    f'UPDATE "ValueSetValues" SET "Deleted" = true WHERE "Id" IN ({id_list(before["value_set_values"])}) AND "Deleted" IS NOT TRUE;'
)
w(f'UPDATE "ValueSets" SET "Deleted" = true WHERE "Id" IN ({id_list(before["value_sets"])}) AND "Deleted" IS NOT TRUE;')
w("-- §2.4 the 14 existing entities, their 140 attributes and 140 attribute associations.")
w(
    f'UPDATE "EntityAttributeAssociation" SET "Deleted" = true WHERE "Id" IN ({id_list(before["entity_attribute_associations"])}) '
    'AND "Deleted" IS NOT TRUE;'
)
w(
    f'UPDATE "Attributes" SET "Deleted" = true WHERE "Id" IN ({id_list(before["attributes"])}) AND "Deleted" IS NOT TRUE;'
)
w(f'UPDATE "Entities" SET "Deleted" = true WHERE "Id" IN ({id_list(before["entities"])}) AND "Deleted" IS NOT TRUE;')
assert len(before["entities"]) == 14 and len(before["attributes"]) == 140
assert len(before["value_sets"]) == 27 and len(before["value_set_values"]) == 112
assert len(before["value_set_value_mappings"]) == 115
assert len(before["transformations"]) == 176 and len(before["transformation_attributes"]) == 352
report["cleanup"] = {
    "entities": 14,
    "attributes": 140,
    "entity_attribute_associations": 140,
    "value_sets": 27,
    "value_set_values": 112,
    "value_set_value_mappings": 115,
    "transformation_group": 1,
    "transformations": 176,
    "transformation_attributes": 352,
    "transformation_rows_already_deleted_in_seed": True,
}

# ---- Phase 2: model notes -----------------------------------------------------------------------
banner("Phase 2 -- DataModels row 10 keeps its id, name and version; Notes record the sources and rules")
model_notes = "\n".join(
    [
        f"Rebuilt {BUILD_DATE} from {AUTHORITY_FILE} (credreg.net CTDL JSON-LD with meta properties, release 20260927;"
        f" SHA-256 {AUTHORITY_SHA256}) per claude_CTDL-work-order-v7: 140 classes, 418 properties, 7,753 domain rows,"
        " 36 concept schemes, 457 concepts; plus the deprecated ceterms:Competency and ceterms:CompetencyFramework"
        " retained by decision.",
        f"Array on attribute rows follows `multivalue` in {REGISTRY_FILE} (Credential Registry publishing schema;"
        f" SHA-256 {REGISTRY_SHA256}), not CTDL, which declares no cardinality. Rows for the 15 properties the"
        " Registry lacks carry Array null. For reference associations, multivalue is recorded in the association"
        " Notes, never as Array.",
        "Required exists solely so references render: the schema generator copies only a referenced entity's"
        " required properties. ctid and name are Required wherever present, with a substitute pair on classes"
        " that have neither. Required does not assert CTDL cardinality.",
        "Every domain row with an in-model class range is a Reference association named by the property; its"
        " child is one of the permitted targets (listed in the association Notes), chosen by build_ctdl_model.py."
        " Every other row is an attribute, one row per class and property, UniqueName <Class>.<property>.",
        "Class hierarchy is recorded in each entity's Notes as subClassOf lines; foreign parents are marked.",
    ]
)
w(
    f'UPDATE "DataModels" SET "Notes" = {q(model_notes)}, "Description" = COALESCE("Description", {q("Credential Transparency Description Language (CTDL), ceterms namespace, as published by Credential Engine.")}) WHERE "Id" = {DM};'
)

# ---- temp functions -----------------------------------------------------------------------------
banner("Temporary helpers (dropped at the end)")
w(
    f"""
CREATE OR REPLACE FUNCTION public.ctdl_tmp_valueset(
    p_name text, p_description text, p_use text, p_notes text, p_values jsonb
) RETURNS bigint AS $fn$
DECLARE v_id bigint; v jsonb; v_vid bigint;
BEGIN
    SELECT "Id" INTO v_id FROM public."ValueSets"
     WHERE "DataModelId" = {DM} AND "Name" = p_name AND "Deleted" IS NOT TRUE LIMIT 1;
    IF v_id IS NULL THEN
        INSERT INTO public."ValueSets"
            ("Name","Description","UseConsiderations","Notes","DataModelId","ContributorOrganization","Extension","Deleted")
        VALUES (p_name, p_description, p_use, p_notes, {DM}, {q(ORG)}, false, false)
        RETURNING "Id" INTO v_id;
    ELSE
        UPDATE public."ValueSets"
           SET "Description" = p_description, "UseConsiderations" = p_use, "Notes" = p_notes,
               "ContributorOrganization" = {q(ORG)}
         WHERE "Id" = v_id;
    END IF;
    FOR v IN SELECT * FROM jsonb_array_elements(p_values) LOOP
        SELECT "Id" INTO v_vid FROM public."ValueSetValues"
         WHERE "ValueSetId" = v_id AND "ValueName" = v->>'n' AND "Deleted" IS NOT TRUE LIMIT 1;
        IF v_vid IS NULL THEN
            INSERT INTO public."ValueSetValues"
                ("ValueSetId","Value","ValueName","Description","UseConsiderations","Notes",
                 "DataModelId","Source","ContributorOrganization","Extension","Deleted")
            VALUES (v_id, v->>'v', v->>'n', v->>'d', v->>'u', v->>'notes', {DM}, {q(SOURCE_MODEL)}, {q(ORG)}, false, false);
        ELSE
            UPDATE public."ValueSetValues"
               SET "Value" = v->>'v', "Description" = v->>'d', "UseConsiderations" = v->>'u', "Notes" = v->>'notes',
                   "Source" = {q(SOURCE_MODEL)}, "ContributorOrganization" = {q(ORG)}
             WHERE "Id" = v_vid;
        END IF;
    END LOOP;
    RETURN v_id;
END $fn$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION public.ctdl_tmp_entity(
    p_name text, p_description text, p_use text, p_notes text, p_deprecation timestamptz
) RETURNS bigint AS $fn$
DECLARE v_id bigint;
BEGIN
    SELECT "Id" INTO v_id FROM public."Entities"
     WHERE "DataModelId" = {DM} AND "UniqueName" = p_name AND "Deleted" IS NOT TRUE LIMIT 1;
    IF v_id IS NULL THEN
        INSERT INTO public."Entities"
            ("Name","UniqueName","Description","UseConsiderations","Required","Array","SourceModel","DataModelId",
             "Notes","DeprecationDate","ContributorOrganization","Extension","Deleted","LevelOfAccess","Queryable","Modifiable")
        VALUES (p_name, p_name, p_description, p_use, NULL, NULL, {q(SOURCE_MODEL)}, {DM},
                p_notes, p_deprecation, {q(ORG)}, false, false, 'Public', false, false)
        RETURNING "Id" INTO v_id;
    ELSE
        UPDATE public."Entities"
           SET "Name" = p_name, "Description" = p_description, "UseConsiderations" = p_use, "Required" = NULL,
               "Array" = NULL, "SourceModel" = {q(SOURCE_MODEL)}, "Notes" = p_notes, "DeprecationDate" = p_deprecation,
               "ContributorOrganization" = {q(ORG)}, "Extension" = false
         WHERE "Id" = v_id;
    END IF;
    RETURN v_id;
END $fn$ LANGUAGE plpgsql;

-- One attribute row per domain row (§1.5), plus its single attribute association. Array is written to
-- the Attributes row, which the schema generator reads, and mirrored on the association (§4.4).
CREATE OR REPLACE FUNCTION public.ctdl_tmp_attr(
    p_entity text, p_name text, p_unique_name text, p_description text, p_use text, p_datatype text,
    p_valueset text, p_required text, p_array text, p_notes text, p_assoc_notes text, p_deprecation timestamptz
) RETURNS bigint AS $fn$
DECLARE v_id bigint; v_eid bigint; v_vsid bigint; v_assoc_array boolean;
BEGIN
    SELECT "Id" INTO v_eid FROM public."Entities"
     WHERE "DataModelId" = {DM} AND "UniqueName" = p_entity AND "Deleted" IS NOT TRUE LIMIT 1;
    IF v_eid IS NULL THEN
        RAISE EXCEPTION 'Owning entity % not found for attribute %', p_entity, p_unique_name;
    END IF;
    IF p_valueset IS NOT NULL THEN
        SELECT "Id" INTO v_vsid FROM public."ValueSets"
         WHERE "DataModelId" = {DM} AND "Name" = p_valueset AND "Deleted" IS NOT TRUE LIMIT 1;
        IF v_vsid IS NULL THEN
            RAISE EXCEPTION 'Value set % not found for attribute %', p_valueset, p_unique_name;
        END IF;
    END IF;
    v_assoc_array := CASE p_array WHEN 'Yes' THEN true WHEN 'No' THEN false ELSE NULL END;

    SELECT "Id" INTO v_id FROM public."Attributes"
     WHERE "DataModelId" = {DM} AND "UniqueName" = p_unique_name AND "Deleted" IS NOT TRUE LIMIT 1;
    IF v_id IS NULL THEN
        INSERT INTO public."Attributes"
            ("Name","UniqueName","Description","UseConsiderations","DataModelId","DataType","ValueSetId","TargetEntityId",
             "Required","Array","SourceModel","Notes","DeprecationDate","ContributorOrganization","Extension","Deleted",
             "LevelOfAccess","Queryable","Modifiable")
        VALUES (p_name, p_unique_name, p_description, p_use, {DM}, p_datatype, v_vsid, NULL,
                p_required, p_array, {q(SOURCE_MODEL)}, p_notes, p_deprecation, {q(ORG)}, false, false,
                'Public', false, false)
        RETURNING "Id" INTO v_id;
    ELSE
        UPDATE public."Attributes"
           SET "Name" = p_name, "Description" = p_description, "UseConsiderations" = p_use, "DataType" = p_datatype,
               "ValueSetId" = v_vsid, "TargetEntityId" = NULL, "Required" = p_required, "Array" = p_array,
               "SourceModel" = {q(SOURCE_MODEL)}, "Notes" = p_notes, "DeprecationDate" = p_deprecation,
               "ContributorOrganization" = {q(ORG)}, "Extension" = false
         WHERE "Id" = v_id;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM public."EntityAttributeAssociation"
         WHERE "EntityId" = v_eid AND "AttributeId" = v_id AND "ExtendedByDataModelId" IS NULL AND "Deleted" IS NOT TRUE
    ) THEN
        INSERT INTO public."EntityAttributeAssociation"
            ("EntityId","AttributeId","Notes","Deleted","ExtendedByDataModelId","ContributorOrganization","Name","Array")
        VALUES (v_eid, v_id, p_assoc_notes, false, NULL, {q(ORG)}, p_name, v_assoc_array);
    ELSE
        UPDATE public."EntityAttributeAssociation" SET "Name" = p_name, "Array" = v_assoc_array, "Notes" = p_assoc_notes
         WHERE "EntityId" = v_eid AND "AttributeId" = v_id AND "ExtendedByDataModelId" IS NULL AND "Deleted" IS NOT TRUE;
    END IF;
    RETURN v_id;
END $fn$ LANGUAGE plpgsql;

-- One Reference association per class-ranged domain row (§4, §4.5). Relationship stays NULL: the
-- association's Name is the key the generator reads. Array is never written on a reference (§4.4).
CREATE OR REPLACE FUNCTION public.ctdl_tmp_ref(
    p_parent text, p_child text, p_name text, p_notes text
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
            ("ParentEntityId","ChildEntityId","Relationship","Placement","Notes","ContributorOrganization",
             "Deleted","Extension","ExtendedByDataModelId","Name","Array")
        VALUES (v_pid, v_cid, NULL, 'Reference', p_notes, {q(ORG)}, false, false, NULL, p_name, NULL)
        RETURNING "Id" INTO v_id;
    ELSE
        UPDATE public."EntityAssociation"
           SET "ChildEntityId" = v_cid, "Relationship" = NULL, "Placement" = 'Reference', "Notes" = p_notes,
               "Array" = NULL, "ContributorOrganization" = {q(ORG)}
         WHERE "Id" = v_id;
    END IF;
    RETURN v_id;
END $fn$ LANGUAGE plpgsql;
"""
)

# ---- value sets (§4.8) --------------------------------------------------------------------------
banner("Phase 2 -- 36 concept schemes as value sets (after §2.3 freed the names)")
value_count = 0
scheme_by_local: dict[str, str] = {}
for scheme_id, node in schemes.items():
    name = local_name(scheme_id)
    assert name not in scheme_by_local
    scheme_by_local[name] = scheme_id
    members = node.get("meta:hasConcept", [])
    values = []
    seen_names: set[str] = set()
    for concept_id in members:
        c = concepts[concept_id]
        assert scheme_id in c.get("skos:inScheme", []), (concept_id, scheme_id)
        value_name = en(c, "skos:prefLabel")
        assert value_name and value_name not in seen_names, (scheme_id, concept_id, value_name)
        seen_names.add(value_name)
        notes_lines = [f"concept: {concept_id}"]
        if c.get("skos:broader"):
            notes_lines.append("broader: " + "; ".join(c["skos:broader"]))
        if en(c, "dct:description"):
            notes_lines.append("dct:description: " + str(en(c, "dct:description")))
        values.append(
            {
                "v": concept_id,
                "n": value_name,
                "d": en(c, "skos:definition"),
                "u": en(c, "vann:usageNote"),
                "notes": "\n".join(notes_lines),
            }
        )
    value_count += len(values)
    notes = f"scheme: {scheme_id}"
    if en(node, "dct:description"):
        notes += "\ndct:description: " + str(en(node, "dct:description"))
    w(
        f"SELECT public.ctdl_tmp_valueset({q(name)}, {q(en(node, 'rdfs:comment'))}, {q(en(node, 'vann:usageNote'))}, {q(notes)}, {qjson(values)});"
    )
assert value_count == 457, value_count
assert sum(1 for c in concepts.values() for s in c.get("skos:inScheme", []) if s in schemes) == 457
report["value_sets"] = {"schemes": len(schemes), "concepts": value_count}

# ---- entities (§3) ------------------------------------------------------------------------------
banner("Phase 2 -- 142 entities: 140 classes from the file plus the two retained deprecated classes (§5.2)")
entity_name: dict[str, str] = {c: local_name(c) for c in classes}
assert len(set(entity_name.values())) == len(entity_name)
hierarchy_notes = 0
multi_parent = 0
no_subclass = 0
no_in_model_parent = 0
propertyless = []
for class_id, node in classes.items():
    notes: list[str] = []
    parents = node.get("rdfs:subClassOf", [])
    if parents:
        hierarchy_notes += 1
        if len(parents) > 1:
            multi_parent += 1
        in_model = [p for p in parents if p in classes]
        if not in_model:
            no_in_model_parent += 1
        for p in parents:
            notes.append(f"subClassOf: {p}" + ("" if p in classes else FOREIGN_SUFFIX))
    else:
        no_subclass += 1
        no_in_model_parent += 1
    if class_id in MODELED_FOREIGN_CLASSES:
        notes.append("retained by exception: foreign class shipped in the CTDL serialization (work order §5.3)")
    if node.get("owl:equivalentClass"):
        notes.append("equivalentClass: " + "; ".join(node["owl:equivalentClass"]))
    if node.get("vs:term_status"):
        notes.append(f"termStatus: {node['vs:term_status']}")
    if not node.get("meta:domainFor"):
        propertyless.append(class_id)
        notes.append("no properties in the authority file; created for hierarchy and as a reference target")
    w(
        f"SELECT public.ctdl_tmp_entity({q(entity_name[class_id])}, {q(entity_description(node))}, "
        f"{q(en(node, 'vann:usageNote'))}, {q(chr(10).join(notes))}, NULL);"
    )
assert hierarchy_notes == 96 and multi_parent == 7 and no_subclass == 44 and no_in_model_parent == 56, (
    hierarchy_notes,
    multi_parent,
    no_subclass,
    no_in_model_parent,
)
assert len(propertyless) == 10, propertyless

before_entities = {e["Id"]: e for e in before["entities"]}
for old_id, (name, successor) in RETAINED_CLASSES.items():
    old = before_entities[old_id]
    assert old["Name"] == name, (old_id, old["Name"])
    notes = (
        RETAINED_CLASS_NOTES[name]
        + RETAINED_COMMON_NOTES
        + [f"source: Entities row {old_id} ({old['UniqueName']}) in the pre-build seed"]
    )
    w(
        f"SELECT public.ctdl_tmp_entity({q(name)}, {q(old.get('Description'))}, {q(old.get('UseConsiderations'))}, "
        f"{q(chr(10).join(notes))}, {q(DEPRECATION_DATE)}::timestamptz);"
    )
report["entities"] = {
    "from_file": len(classes),
    "retained_deprecated": len(RETAINED_CLASSES),
    "total": len(classes) + len(RETAINED_CLASSES),
    "with_hierarchy_notes": hierarchy_notes,
    "multi_parent": multi_parent,
    "no_subclassof": no_subclass,
    "no_in_model_parent": no_in_model_parent,
    "propertyless": [entity_name[c] for c in propertyless],
}

# ---- attribute rows and reference rows (§4) -------------------------------------------------------
banner("Phase 2 -- 7,753 domain rows: attribute-typed rows become Attributes, class-ranged rows become references")

# §4.1 safety: no class holds two properties sharing a bare name.
for class_id, node in classes.items():
    names = [local_name(p) for p in node.get("meta:domainFor", [])]
    assert len(names) == len(set(names)), class_id

attribute_rows = 0
reference_rows = 0
array_counts: collections.Counter = collections.Counter()
ref_multivalue_counts: collections.Counter = collections.Counter()
datatype_counts: collections.Counter = collections.Counter()
no_target_rows = 0
no_target_props: set[str] = set()
value_set_link_rows = 0
value_set_link_props: set[str] = set()
required_rows = 0
required_multivalue: set[str] = set()
unresolved_ref_rows = 0
unresolved_ref_props: set[str] = set()
unresolved_ranges_seen: collections.Counter = collections.Counter()
dropped_ref_rows = 0
dropped_ref_props: set[str] = set()
enum_without_set = 0
child_choice: dict[str, str] = {}
child_choice_reason: dict[str, dict] = {}
association_scheme_notes = 0
placed_props: set[str] = set()
mixed_multi_range: dict[str, str] = {}

for class_id, prop_id in rows:
    placed_props.add(prop_id)
    node = props[prop_id]
    owner = entity_name[class_id]
    name = local_name(prop_id)
    description = en(node, "rdfs:comment")
    use = en(node, "vann:usageNote")
    target_scheme = node.get("meta:targetScheme", [])
    if is_reference(prop_id):
        reference_rows += 1
        child, permitted, unresolved = reference_child(prop_id)
        child_choice[prop_id] = child
        notes = [multivalue_note(prop_id), "permittedTargets: " + "; ".join(permitted)]
        if unresolved:
            unresolved_ref_rows += 1
            unresolved_ref_props.add(prop_id)
            for r in unresolved:
                unresolved_ranges_seen[r] += 1
            notes.append("unresolvedRanges: " + "; ".join(unresolved))
        dropped = [r for r in ranges_of(prop_id) if r in LITERAL_TYPES or r == CONCEPT]
        if dropped:
            dropped_ref_rows += 1
            dropped_ref_props.add(prop_id)
            notes.append(
                "droppedRanges: " + "; ".join(dropped) + " [literal or concept range not carried by a reference]"
            )
        if target_scheme:
            notes.append("targetScheme: " + "; ".join(target_scheme))
            association_scheme_notes += 1
        if description:
            notes.append(f"description: {description}")
        if prop_id in ("ceterms:isSimilarTo",):
            mixed_multi_range[prop_id] = "reference"
        flag = multivalue.get(prop_id)
        ref_multivalue_counts["multivalue" if flag is True else "single" if flag is False else "null"] += 1
        w(f"SELECT public.ctdl_tmp_ref({q(owner)}, {q(entity_name[child])}, {q(name)}, {q(chr(10).join(notes))});")
        continue

    attribute_rows += 1
    data_type, notes = data_type_for(prop_id)
    if any(n.startswith("rangeIncludes:") and "[out of model]" in n for n in notes):
        no_target_rows += 1
        no_target_props.add(prop_id)
    if prop_id in ("ceterms:leftSource", "ceterms:rightSource"):
        mixed_multi_range[prop_id] = data_type
    datatype_counts[data_type] += 1
    value_set = None
    if data_type == "enum":
        in_file = [s for s in target_scheme if s in schemes]
        if in_file:
            assert len(in_file) == 1, prop_id
            value_set = local_name(in_file[0])
            value_set_link_rows += 1
            value_set_link_props.add(prop_id)
        else:
            enum_without_set += 1
            if target_scheme:
                notes.append("targetScheme: " + "; ".join(target_scheme) + " [scheme not in the authority file]")
    elif target_scheme:
        notes.append("targetScheme: " + "; ".join(target_scheme))
    required = None
    if prop_id in REQUIRED_GENERAL or prop_id in REQUIRED_BY_CLASS.get(class_id, []):
        required = "Yes"
        required_rows += 1
        if multivalue.get(prop_id) is True:
            required_multivalue.add(prop_id)
    array = array_value(prop_id)
    array_counts[array or "null"] += 1
    if node.get("vs:term_status"):
        notes.append(f"termStatus: {node['vs:term_status']}")
    assoc_notes = multivalue_note(prop_id)
    w(
        f"SELECT public.ctdl_tmp_attr({q(owner)}, {q(name)}, {q(owner + '.' + name)}, {q(description)}, {q(use)}, "
        f"{q(data_type)}, {q(value_set)}, {q(required)}, {q(array)}, {q(chr(10).join(notes))}, {q(assoc_notes)}, NULL);"
    )

assert reference_rows == 5402 and attribute_rows == 2351, (reference_rows, attribute_rows)
assert no_target_rows == 140 and len(no_target_props) == 13, (no_target_rows, sorted(no_target_props))
assert value_set_link_rows == 21 and len(value_set_link_props) == 16, (
    value_set_link_rows,
    sorted(value_set_link_props),
)
assert unresolved_ref_rows == 295 and len(unresolved_ref_props) == 21, (
    unresolved_ref_rows,
    sorted(unresolved_ref_props),
)
assert array_counts == collections.Counter({"Yes": 915, "No": 1433, "null": 3}), array_counts
assert ref_multivalue_counts == collections.Counter({"multivalue": 4929, "single": 321, "null": 152}), (
    ref_multivalue_counts
)
never_placed = sorted(set(props) - placed_props)
assert len(never_placed) == 13, never_placed

# ---- the ten retained attributes (§5.2) -----------------------------------------------------------
banner("Phase 2 -- the ten attributes carried onto the retained deprecated classes (§5.2)")
before_attrs = {a["Id"]: a for a in before["attributes"]}
before_owner = {x["AttributeId"]: x["EntityId"] for x in before["entity_attribute_associations"] if not x["Deleted"]}
retained_attribute_report = []
for old_entity_id, items in RETAINED_ATTRIBUTES.items():
    owner, _ = RETAINED_CLASSES[old_entity_id]
    for old_attr_id, name, data_type in items:
        old = before_attrs[old_attr_id]
        assert before_owner[old_attr_id] == old_entity_id, (old_attr_id, before_owner.get(old_attr_id))
        assert old["Name"].replace("ceterms-", "") == name, (old_attr_id, old["Name"], name)
        prop_id = "ceterms:" + name
        assert prop_id in props, prop_id  # a genuine ceterms term
        notes = [
            f"source: Attributes row {old_attr_id} ({old['UniqueName']}) in the pre-build seed; this class has no"
            f" domain row for {prop_id} in {AUTHORITY_FILE}",
            "typedBy: work order §4.2 (the pre-build row had no DataType)",
        ]
        array = array_value(prop_id)
        w(
            f"SELECT public.ctdl_tmp_attr({q(owner)}, {q(name)}, {q(owner + '.' + name)}, {q(old.get('Description'))}, "
            f"{q(old.get('UseConsiderations'))}, {q(data_type)}, NULL, NULL, {q(array)}, {q(chr(10).join(notes))}, "
            f"{q(multivalue_note(prop_id))}, {q(DEPRECATION_DATE)}::timestamptz);"
        )
        retained_attribute_report.append(
            {
                "entity": owner,
                "attribute": f"{owner}.{name}",
                "source_attribute_id": old_attr_id,
                "source_unique_name": old["UniqueName"],
                "source_entity_id": old_entity_id,
                "data_type": data_type,
                "array": array,
            }
        )
assert len(retained_attribute_report) == 10

# ---- end ------------------------------------------------------------------------------------------
banner("Done")
w("DROP FUNCTION IF EXISTS public.ctdl_tmp_ref(text,text,text,text);")
w("DROP FUNCTION IF EXISTS public.ctdl_tmp_attr(text,text,text,text,text,text,text,text,text,text,text,timestamptz);")
w("DROP FUNCTION IF EXISTS public.ctdl_tmp_entity(text,text,text,text,timestamptz);")
w("DROP FUNCTION IF EXISTS public.ctdl_tmp_valueset(text,text,text,text,jsonb);")
w("COMMIT;")

with open(os.path.join(HERE, "ctdl_model_10_update.sql"), "w", encoding="utf-8") as f:
    f.write("\n".join(out) + "\n")

# ---- report --------------------------------------------------------------------------------------
single_range = [p for p in props if len(ranges_of(p)) == 1]
multi_range = [p for p in props if len(ranges_of(p)) > 1]
report["domain_rows"] = {
    "total": len(rows),
    "reference_rows": reference_rows,
    "attribute_rows": attribute_rows,
    "properties_placed": len(placed_props),
    "properties_never_placed": never_placed,
    "single_range_properties": len(single_range),
    "multi_range_properties": len(multi_range),
}
report["attributes"] = {
    "from_domain_rows": attribute_rows,
    "retained_deprecated": 10,
    "total": attribute_rows + 10,
    "data_types": dict(datatype_counts),
    "array": dict(array_counts),
    "no_resolvable_range_rows": no_target_rows,
    "no_resolvable_range_properties": sorted(no_target_props),
    "value_set_link_rows": value_set_link_rows,
    "value_set_link_properties": sorted(value_set_link_props),
    "enum_rows_without_value_set": enum_without_set,
    "required_rows": required_rows,
    "required_picks_that_are_multivalue": sorted(required_multivalue),
    "retained": retained_attribute_report,
}
report["references"] = {
    "rows": reference_rows,
    "multivalue_notes": dict(ref_multivalue_counts),
    "rows_with_unresolved_ranges": unresolved_ref_rows,
    "properties_with_unresolved_ranges": sorted(unresolved_ref_props),
    "unresolved_ranges": dict(sorted(unresolved_ranges_seen.items())),
    "target_scheme_notes": association_scheme_notes,
    "rows_with_dropped_literal_or_concept_ranges": dropped_ref_rows,
    "properties_with_dropped_literal_or_concept_ranges": sorted(dropped_ref_props),
    "child_per_property": {p: entity_name[c] for p, c in sorted(child_choice.items())},
}
report["mixed_multi_range_properties"] = {
    "ceterms:leftSource": {
        "type": mixed_multi_range.get("ceterms:leftSource"),
        "ranges": ranges_of("ceterms:leftSource"),
    },
    "ceterms:rightSource": {
        "type": mixed_multi_range.get("ceterms:rightSource"),
        "ranges": ranges_of("ceterms:rightSource"),
    },
    "ceterms:isSimilarTo": {
        "type": "reference",
        "child": entity_name[child_choice["ceterms:isSimilarTo"]],
        "permitted_targets": len([r for r in ranges_of("ceterms:isSimilarTo") if resolves(r)]),
        "unresolved": [r for r in ranges_of("ceterms:isSimilarTo") if not resolves(r)],
    },
}
report["expected_by_work_order_6_1"] = {
    "entities": 142,
    "associations": 7753 + 10,
    "reference_rows": 5402,
    "attribute_rows": 2351,
    "properties_placed_never": [405, 13],
    "schemes_concepts": [36, 457],
    "hierarchy_notes": 96,
    "no_subclassof": 44,
    "no_in_model_parent": 56,
    "propertyless": 10,
    "attribute_array_yes_no_null": [915, 1433, 3],
    "reference_multivalue_single_null": [4929, 321, 152],
    "no_resolvable_range": [140, 13],
    "unresolved_ranges": [295, 21],
    "value_set_links": [21, 16],
}
with open(os.path.join(HERE, "build_report.json"), "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2, ensure_ascii=False)
    f.write("\n")

print(f"wrote ctdl_model_10_update.sql ({len(out)} lines) and build_report.json")
print(json.dumps({k: v for k, v in report.items() if k in ("cleanup", "domain_rows", "value_sets")}, indent=1))
print("attributes:", {k: v for k, v in report["attributes"].items() if k != "retained"})
print("references:", {k: v for k, v in report["references"].items() if k != "child_per_property"})
