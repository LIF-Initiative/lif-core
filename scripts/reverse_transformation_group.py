#!/usr/bin/env python3
"""
reverse_transformation_group.py

Reads an exported MDR transformation group JSON (e.g. Ed-Fi → StateU LIF)
and produces a reversed version (StateU LIF → Ed-Fi) ready to POST to the MDR API.

What it does:
  1. Swaps SourceDataModelId / TargetDataModelId
  2. Swaps SourceAttributes <-> TargetAttribute for every transformation
  3. Reverses the JSONata expression where possible (simple 1:1 cases)
  4. Flags complex expressions (those using $functions like $split/$contains)
     with a NEEDS_REVIEW comment — these must be updated manually before import.

Usage:
    python scripts/reverse_transformation_group.py \\
        --input  Ed-Fi_v5_StateU_LIF_v1.0.json \\
        --output StateU_LIF_v1.0_Ed-Fi_v5.json

    # Override model IDs or version if needed:
    python scripts/reverse_transformation_group.py \\
        --input  Ed-Fi_v5_StateU_LIF_v1.0.json \\
        --output StateU_LIF_v1.0_Ed-Fi_v5.json \\
        --source-model-id 17 \\
        --target-model-id 6 \\
        --group-version 1.0
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# JSONata reversal helpers
# ---------------------------------------------------------------------------

def _has_complex_functions(expr: str) -> bool:
    """True if the expression uses built-in JSONata $functions."""
    return bool(re.search(r'\$[a-zA-Z]+\(', expr))


def _parse_entity_id_path(path: str) -> tuple[list[str], str | None]:
    """
    Parse a named EntityIdPath like:
        "1:Person,1:Common.Contact,1:Common.Contact.Email,17:~Common.Contact.Email.emailAddress"

    Returns:
        entity_short_names  – short names of each entity segment (before the attr)
        attribute_short_name – short name of the final attribute, or None if path ends on entity
    """
    parts = path.split(",")
    entity_names: list[str] = []
    attr_name: str | None = None

    for part in parts:
        segment = part.split(":", 1)[1]          # strip the "dmId:" prefix
        if segment.startswith("~"):
            # Attribute — last segment after the final "."
            attr_name = segment.lstrip("~").split(".")[-1]
        else:
            # Entity — short name is the last "."-delimited token
            entity_names.append(segment.split(".")[-1])

    return entity_names, attr_name


def reverse_jsonata(expression: str, old_src_attr: dict, old_tgt_attr: dict) -> tuple[str, bool]:
    """
    Attempt to produce a reversed JSONata expression.

    old_src_attr  – the original SourceAttribute (Ed-Fi side)
    old_tgt_attr  – the original TargetAttribute  (LIF side)

    Returns (new_expression, was_auto_reversed).
    If auto-reversal isn't possible the original expression is returned
    wrapped in a NEEDS_REVIEW comment and was_auto_reversed=False.
    """
    if _has_complex_functions(expression):
        return (
            f"/* NEEDS_REVIEW: expression uses $functions — update manually */\n{expression}",
            False,
        )

    src_path = (old_src_attr or {}).get("EntityIdPath", "")
    tgt_path = (old_tgt_attr or {}).get("EntityIdPath", "")

    if not src_path or not tgt_path:
        return (
            f"/* NEEDS_REVIEW: missing EntityIdPath — update manually */\n{expression}",
            False,
        )

    # Parse both paths
    src_entities, src_attr_name = _parse_entity_id_path(src_path)   # Ed-Fi
    tgt_entities, tgt_attr_name = _parse_entity_id_path(tgt_path)   # LIF

    if not src_entities or not src_attr_name or not tgt_entities or not tgt_attr_name:
        return (
            f"/* NEEDS_REVIEW: could not parse paths — update manually */\n{expression}",
            False,
        )

    # Ed-Fi root entity (context variable in original expression)
    edfi_root = src_entities[0]       # e.g. "Assessment", "ElectronicMail"
    edfi_attr = src_attr_name         # e.g. "AssessmentIdentifier", "ElectronicMailAddress"

    # LIF root entity (becomes context variable in reversed expression)
    lif_root = tgt_entities[0]        # e.g. "Assessment", "Person"
    lif_attr = tgt_attr_name          # e.g. "identifier", "emailAddress"

    # Build the JSONata path from LIF root into the attribute
    # For a single-level LIF path ["Assessment"] the path is just the attr name.
    # For ["Person", "Contact", "Email"] the path is Contact[0].Email[0].emailAddress
    lif_nav_segments = tgt_entities[1:]   # intermediate entities after root

    if not lif_nav_segments:
        # Simple flat case:  { "EdFiRoot": LIFRoot. { "EdFiAttr": lifAttr } }
        new_expr = f'{{ "{edfi_root}": {lif_root}. {{ "{edfi_attr}": {lif_attr} }} }}'
    else:
        # Nested case: navigate through intermediate LIF entities
        # e.g.  Contact[0].Email[0].emailAddress
        nav = ".".join(f"{seg}[0]" for seg in lif_nav_segments) + f".{lif_attr}"
        new_expr = f'{{ "{edfi_root}": {lif_root}. {{ "{edfi_attr}": {nav} }} }}'

    return new_expr, True


# ---------------------------------------------------------------------------
# Main transformation group reversal
# ---------------------------------------------------------------------------

def reverse_group(
    data: dict,
    new_source_dm_id: int,
    new_target_dm_id: int,
    new_source_name: str,
    new_target_name: str,
    group_version: str | None,
) -> tuple[dict, list[str]]:
    """
    Build the reversed transformation group dict.

    Returns (reversed_group_dict, list_of_names_needing_review).
    """
    version = group_version or data.get("GroupVersion", "1.0")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    reversed_group: dict = {
        "SourceDataModelId": new_source_dm_id,
        "TargetDataModelId": new_target_dm_id,
        "Name": f"{new_source_name}_{new_target_name}",
        "GroupVersion": version,
        "Description": data.get("Description"),
        "Notes": data.get("Notes"),
        "CreationDate": now,
        "ActivationDate": data.get("ActivationDate"),
        "DeprecationDate": data.get("DeprecationDate"),
        "Contributor": data.get("Contributor"),
        "ContributorOrganization": data.get("ContributorOrganization"),
        "Tags": data.get("Tags"),
        "Transformations": [],
    }

    needs_review: list[str] = []

    for t in data.get("Transformations", []):
        old_src_attrs: list[dict] = t.get("SourceAttributes") or []
        old_tgt_attr: dict | None = t.get("TargetAttribute")
        t_name: str = t.get("Name") or "unknown"

        # Warn about multi-source transformations
        if len(old_src_attrs) > 1:
            needs_review.append(f"{t_name}  ← multiple source attributes (check manually)")

        # Primary source attr for reversal (first one)
        primary_src = old_src_attrs[0] if old_src_attrs else {}

        # Reverse the JSONata expression
        old_expr: str = t.get("Expression") or ""
        new_expr, was_reversed = reverse_jsonata(old_expr, primary_src, old_tgt_attr)
        if not was_reversed:
            needs_review.append(t_name)

        # New SourceAttribute = old TargetAttribute (LIF side → now the source)
        new_src_attrs: list[dict] = []
        if old_tgt_attr:
            new_src_attrs.append({
                "AttributeId": None,
                "EntityId": None,        # resolved server-side via EntityIdPath
                "AttributeType": "Source",
                "Notes": old_tgt_attr.get("Notes"),
                "CreationDate": old_tgt_attr.get("CreationDate"),
                "ActivationDate": old_tgt_attr.get("ActivationDate"),
                "DeprecationDate": old_tgt_attr.get("DeprecationDate"),
                "Contributor": old_tgt_attr.get("Contributor"),
                "ContributorOrganization": old_tgt_attr.get("ContributorOrganization"),
                "EntityIdPath": old_tgt_attr.get("EntityIdPath"),
            })

        # New TargetAttribute = old primary SourceAttribute (Ed-Fi side → now the target)
        new_tgt_attr: dict | None = None
        if primary_src:
            new_tgt_attr = {
                "AttributeId": None,
                "EntityId": None,        # resolved server-side via EntityIdPath
                "AttributeType": "Target",
                "Notes": primary_src.get("Notes"),
                "CreationDate": primary_src.get("CreationDate"),
                "ActivationDate": primary_src.get("ActivationDate"),
                "DeprecationDate": primary_src.get("DeprecationDate"),
                "Contributor": primary_src.get("Contributor"),
                "ContributorOrganization": primary_src.get("ContributorOrganization"),
                "EntityIdPath": primary_src.get("EntityIdPath"),
            }

        reversed_group["Transformations"].append({
            "Name": t_name,
            "Expression": new_expr,
            "ExpressionLanguage": t.get("ExpressionLanguage", "JSONata"),
            "Notes": t.get("Notes"),
            "Alignment": t.get("Alignment"),
            "CreationDate": t.get("CreationDate"),
            "ActivationDate": t.get("ActivationDate"),
            "DeprecationDate": t.get("DeprecationDate"),
            "Contributor": t.get("Contributor"),
            "ContributorOrganization": t.get("ContributorOrganization"),
            "SourceAttributes": new_src_attrs,
            "TargetAttribute": new_tgt_attr,
        })

    return reversed_group, needs_review


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reverse an MDR transformation group JSON (swap source/target, reverse JSONata).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--input", required=True, help="Path to the exported transformation group JSON")
    parser.add_argument("--output", required=True, help="Path to write the reversed JSON")
    parser.add_argument(
        "--source-model-id", type=int, default=17,
        help="New source data model ID (default: 17 = StateU LIF)",
    )
    parser.add_argument(
        "--target-model-id", type=int, default=6,
        help="New target data model ID (default: 6 = Ed-Fi v5)",
    )
    parser.add_argument("--source-model-name", default="StateU LIF")
    parser.add_argument("--target-model-name", default="Ed-Fi v5")
    parser.add_argument(
        "--group-version", default=None,
        help="Transformation group version string (defaults to the version in the input file)",
    )
    args = parser.parse_args()

    with open(args.input) as f:
        data = json.load(f)

    reversed_group, needs_review = reverse_group(
        data,
        new_source_dm_id=args.source_model_id,
        new_target_dm_id=args.target_model_id,
        new_source_name=args.source_model_name,
        new_target_name=args.target_model_name,
        group_version=args.group_version,
    )

    with open(args.output, "w") as f:
        json.dump(reversed_group, f, indent=2)

    total = len(reversed_group["Transformations"])
    auto = total - len([n for n in needs_review if "←" not in n])  # approx
    print(f"✓  Written to {args.output}")
    print(f"   Transformations total : {total}")
    print(f"   Needs manual review   : {len(needs_review)}")

    if needs_review:
        print("\n⚠️  The following transformations need their JSONata updated manually")
        print("   (search for NEEDS_REVIEW in the output file):\n")
        for name in needs_review:
            print(f"   • {name}")
        print(
            "\n   Tip: these are complex expressions with $split/$contains/$replace etc.\n"
            "   The expression has been preserved as-is with a comment prefix.\n"
            "   Update the Expression field before running import_transformation_group.py."
        )
    else:
        print("   All expressions auto-reversed ✓")


if __name__ == "__main__":
    main()
