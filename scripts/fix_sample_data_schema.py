#!/usr/bin/env python3
"""
Script to validate and fix sample data files against the new LIF schema.

This script:
1. Reads the new LIF schema from the lif-data-model repo
2. Extracts required fields for each entity
3. For each sample data file, adds missing required fields:
   - identifier: generates unique IDs based on entity type and existing data
   - informationSourceOrganization: derives from informationSourceId mapping
4. Outputs fixed files (overwrites originals or creates new files)

Usage:
    python scripts/fix_sample_data_schema.py [--dry-run] [--schema-path PATH]
"""

import json
import re
import sys
import uuid
from pathlib import Path
from typing import Any


# Mapping from informationSourceId to informationSourceOrganization
INFO_SOURCE_ORG_MAP = {
    "Org1": "State University",
    "Org2": "Community College",
    "Org3": "Regional University",
    "org1": "State University",
    "org2": "Community College",
    "org3": "Regional University",
    "Single-Org": "Demo University",
    "single-org": "Demo University",
}

# Mapping from JSON keys (camelCase) to schema entity names (PascalCase)
KEY_TO_ENTITY = {
    # Person sub-entities
    "name": "Name",
    "contact": "Contact",
    "identifier": "Identifier",
    "proficiency": "Proficiency",
    "courseLearningExperience": "CourseLearningExperience",
    "credentialAward": "CredentialAward",
    "employmentLearningExperience": "EmploymentLearningExperience",
    "assessmentLearningExperience": "AssessmentLearningExperience",
    "programLearningExperience": "ProgramLearningExperience",
    "militaryLearningExperience": "MilitaryLearningExperience",
    "birth": "Birth",
    "death": "Death",
    "sexAndGender": "SexAndGender",
    "culture": "Culture",
    "demographics": "Demographics",
    "language": "Language",
    "residency": "Residency",
    "consent": "Consent",
    "relationshipContacts": "RelationshipContacts",
    # Top-level entities
    "person": "Person",
    "course": "Course",
    "credential": "Credential",
    "organization": "Organization",
    "assessment": "Assessment",
    "competencyFramework": "CompetencyFramework",
    "position": "Position",
    "program": "Program",
    # Nested reference entities
    "refCredentialAward": "CredentialAward",
    "refCompetency": "Competency",
    "refCourse": "Course",
    "refRefCourse": "Course",  # typo in data
    "refPosition": "Position",
    "refRefPosition": "Position",  # typo in data
    "image": "Image",
    "credentialAlignments": "CredentialAlignments",
    # Organization references
    "assertedByRefOrganization": "Organization",
    "offeredByRefOrganization": "Organization",
    "approvedByRefOrganization": "Organization",
    "issuedByRefOrganization": "Organization",
    "awardedByRefOrganization": "Organization",
    "accreditedByRefOrganization": "Organization",
}


def load_schema(schema_path: Path) -> dict:
    """Load the LIF schema from a JSON file."""
    with open(schema_path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_required_fields(schema: dict) -> dict[str, list[str]]:
    """Extract required fields for each entity from the schema."""
    required_fields = {}

    schemas = schema.get("components", {}).get("schemas", {})

    for entity_name, entity_def in schemas.items():
        required = entity_def.get("required", [])
        if required:
            required_fields[entity_name] = required

        # Also get required fields from nested properties
        properties = entity_def.get("properties", {})
        for prop_name, prop_def in properties.items():
            if isinstance(prop_def, dict) and "required" in prop_def:
                nested_required = prop_def.get("required", [])
                if nested_required:
                    required_fields[prop_name] = nested_required

    return required_fields


def generate_identifier(entity_type: str, obj: dict, index: int = 0) -> str:
    """Generate a unique identifier for an entity based on its type and data."""
    # Try to create a meaningful identifier from existing data
    parts = [entity_type.lower()]

    # Use existing identifying information if available
    if "name" in obj and isinstance(obj["name"], str):
        parts.append(re.sub(r"[^a-z0-9]", "-", obj["name"].lower())[:30])
    elif "firstName" in obj and "lastName" in obj:
        parts.append(f"{obj['firstName']}-{obj['lastName']}".lower())
    elif "lastName" in obj:
        parts.append(obj["lastName"].lower())
    elif "id" in obj:
        parts.append(str(obj["id"])[:30])

    # Add info source for uniqueness
    if "informationSourceId" in obj:
        parts.append(obj["informationSourceId"].lower())

    # Add index for uniqueness within arrays
    parts.append(f"{index + 1:03d}")

    return "-".join(parts)


def fix_entity(
    obj: dict,
    entity_type: str,
    required_fields: dict[str, list[str]],
    index: int = 0,
    parent_info_source: str | None = None,
) -> tuple[dict, list[str]]:
    """
    Fix a single entity object by adding missing required fields.

    Returns:
        Tuple of (fixed_object, list_of_changes_made)
    """
    changes = []

    # Get required fields for this entity type
    entity_name = KEY_TO_ENTITY.get(entity_type, entity_type)
    required = required_fields.get(entity_name, [])

    if not required:
        return obj, changes

    # Inherit informationSourceId from parent if not present
    info_source_id = obj.get("informationSourceId", parent_info_source)

    # Add missing informationSourceId
    if "informationSourceId" in required and "informationSourceId" not in obj:
        if info_source_id:
            obj["informationSourceId"] = info_source_id
            changes.append(f"Added informationSourceId: {info_source_id}")

    # Add missing informationSourceOrganization
    if "informationSourceOrganization" in required and "informationSourceOrganization" not in obj:
        info_source = obj.get("informationSourceId", info_source_id)
        if info_source and info_source in INFO_SOURCE_ORG_MAP:
            obj["informationSourceOrganization"] = INFO_SOURCE_ORG_MAP[info_source]
            changes.append(f"Added informationSourceOrganization: {INFO_SOURCE_ORG_MAP[info_source]}")
        else:
            obj["informationSourceOrganization"] = "Unknown Organization"
            changes.append("Added informationSourceOrganization: Unknown Organization (please review)")

    # Add missing identifier
    if "identifier" in required and "identifier" not in obj:
        new_id = generate_identifier(entity_name, obj, index)
        obj["identifier"] = new_id
        changes.append(f"Added identifier: {new_id}")

    return obj, changes


def fix_array_of_entities(
    arr: list,
    entity_type: str,
    required_fields: dict[str, list[str]],
    parent_info_source: str | None = None,
) -> tuple[list, list[str]]:
    """Fix an array of entity objects."""
    all_changes = []
    fixed_arr = []

    for i, item in enumerate(arr):
        if isinstance(item, dict):
            fixed_item, changes = fix_entity(
                item, entity_type, required_fields, i, parent_info_source
            )
            # Recursively fix nested entities
            fixed_item, nested_changes = fix_nested_entities(
                fixed_item, required_fields, item.get("informationSourceId", parent_info_source)
            )
            all_changes.extend([f"{entity_type}[{i}]: {c}" for c in changes])
            all_changes.extend([f"{entity_type}[{i}].{c}" for c in nested_changes])
            fixed_arr.append(fixed_item)
        else:
            fixed_arr.append(item)

    return fixed_arr, all_changes


def fix_nested_entities(
    obj: dict,
    required_fields: dict[str, list[str]],
    parent_info_source: str | None = None,
) -> tuple[dict, list[str]]:
    """Recursively fix nested entities within an object."""
    all_changes = []

    for key, value in list(obj.items()):
        if key in KEY_TO_ENTITY:
            if isinstance(value, list):
                fixed_value, changes = fix_array_of_entities(
                    value, key, required_fields, parent_info_source
                )
                obj[key] = fixed_value
                all_changes.extend(changes)
            elif isinstance(value, dict):
                fixed_value, changes = fix_entity(
                    value, key, required_fields, 0, parent_info_source
                )
                fixed_value, nested_changes = fix_nested_entities(
                    fixed_value, required_fields,
                    value.get("informationSourceId", parent_info_source)
                )
                obj[key] = fixed_value
                all_changes.extend([f"{key}: {c}" for c in changes])
                all_changes.extend([f"{key}.{c}" for c in nested_changes])

    return obj, all_changes


def fix_sample_data(data: dict, required_fields: dict[str, list[str]]) -> tuple[dict, list[str]]:
    """Fix all entities in a sample data file."""
    all_changes = []

    # Get top-level informationSourceId
    top_info_source = data.get("informationSourceId")

    # Process each top-level entity type
    for key in list(data.keys()):
        if key == "informationSourceId":
            continue

        value = data[key]

        if isinstance(value, list):
            fixed_value, changes = fix_array_of_entities(
                value, key, required_fields, top_info_source
            )
            data[key] = fixed_value
            all_changes.extend(changes)
        elif isinstance(value, dict):
            fixed_value, changes = fix_entity(
                value, key, required_fields, 0, top_info_source
            )
            fixed_value, nested_changes = fix_nested_entities(
                fixed_value, required_fields, top_info_source
            )
            data[key] = fixed_value
            all_changes.extend([f"{key}: {c}" for c in changes])
            all_changes.extend([f"{key}.{c}" for c in nested_changes])

    return data, all_changes


def process_file(
    file_path: Path,
    required_fields: dict[str, list[str]],
    dry_run: bool = False,
) -> list[str]:
    """Process a single sample data file."""
    print(f"\nProcessing: {file_path.name}")

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    fixed_data, changes = fix_sample_data(data, required_fields)

    if not changes:
        print("  No changes needed")
        return []

    print(f"  {len(changes)} changes made:")
    for change in changes[:10]:  # Show first 10 changes
        print(f"    - {change}")
    if len(changes) > 10:
        print(f"    ... and {len(changes) - 10} more changes")

    if not dry_run:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(fixed_data, f, indent=2, ensure_ascii=False)
        print(f"  Saved changes to {file_path}")
    else:
        print("  (dry run - no changes saved)")

    return changes


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Fix sample data files against the new LIF schema"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show changes without modifying files",
    )
    parser.add_argument(
        "--schema-path",
        type=Path,
        default=Path("/tmp/new-lif-schema.json"),
        help="Path to the new LIF schema JSON file",
    )
    parser.add_argument(
        "--sample-dir",
        type=Path,
        default=None,
        help="Directory containing sample data files (default: projects/mongodb/sample_data)",
    )
    parser.add_argument(
        "files",
        nargs="*",
        type=Path,
        help="Specific files to process (default: all *-validated.json files)",
    )

    args = parser.parse_args()

    # Load schema
    if not args.schema_path.exists():
        print(f"Error: Schema file not found: {args.schema_path}")
        print("Run: gh api repos/LIF-Initiative/lif-data-model/contents/lif.json --jq '.content' | base64 -d > /tmp/new-lif-schema.json")
        sys.exit(1)

    print(f"Loading schema from: {args.schema_path}")
    schema = load_schema(args.schema_path)
    required_fields = get_required_fields(schema)

    print(f"\nRequired fields by entity:")
    for entity, fields in sorted(required_fields.items()):
        if fields:
            print(f"  {entity}: {', '.join(fields)}")

    # Find sample data files
    if args.files:
        files = args.files
    else:
        base_dir = args.sample_dir or Path(__file__).parent.parent / "projects" / "mongodb" / "sample_data"
        files = list(base_dir.glob("**/*-validated.json"))

    if not files:
        print("\nNo sample data files found")
        sys.exit(1)

    print(f"\nFound {len(files)} sample data files")

    # Process each file
    total_changes = 0
    for file_path in sorted(files):
        changes = process_file(file_path, required_fields, args.dry_run)
        total_changes += len(changes)

    print(f"\n{'=' * 50}")
    print(f"Total changes: {total_changes}")
    if args.dry_run:
        print("(dry run - no files modified)")


if __name__ == "__main__":
    main()
