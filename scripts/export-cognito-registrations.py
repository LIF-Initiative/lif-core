#!/usr/bin/env python3
"""Export Cognito self-serve registrations for outreach (issue #884).

Pulls every user from the `{env}-lif-mdr-cognito` stack's User Pool and emits
one row per user with the registration custom attributes (organization, role,
reason) plus signup metadata and Cognito-group membership. Default output is
CSV to stdout; use `--format json` for raw JSON, `--output <path>` to write
to a file.

The script is read-only — no `--apply` flag because nothing it does
mutates state. Requires `AWS_PROFILE=lif` (or equivalent credentials with
`cognito-idp:ListUsers`, `cognito-idp:AdminListGroupsForUser`, and
`cloudformation:DescribeStacks`).

Usage
-----
  AWS_PROFILE=lif ./scripts/export-cognito-registrations.py dev
  AWS_PROFILE=lif ./scripts/export-cognito-registrations.py demo --format json
  AWS_PROFILE=lif ./scripts/export-cognito-registrations.py demo --output demo-registrations.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from dataclasses import asdict, dataclass
from typing import Any

import boto3

# CSV column order. Match the dataclass field order; if you reorder one,
# reorder the other.
COLUMNS = [
    "sub",
    "email",
    "email_verified",
    "organization",
    "role",
    "reason",
    "status",
    "enabled",
    "created_at",
    "last_modified_at",
    "groups",
]

# Cognito custom attributes (see cloudformation/cognito-selfserve.yml).
# Stored on the user as `custom:organization` etc. — strip the prefix when
# projecting to flat columns.
CUSTOM_ATTRIBUTES = ("organization", "role", "reason")


@dataclass
class Registration:
    sub: str
    email: str
    email_verified: bool
    organization: str
    role: str
    reason: str
    status: str
    enabled: bool
    created_at: str
    last_modified_at: str
    groups: str  # semicolon-joined; empty string if no groups


def _stack_user_pool_id(cfn_client, env: str) -> str:
    """Read UserPoolId from the {env}-lif-mdr-cognito stack outputs."""
    stack_name = f"{env}-lif-mdr-cognito"
    response = cfn_client.describe_stacks(StackName=stack_name)
    outputs = response["Stacks"][0].get("Outputs", [])
    for output in outputs:
        if output.get("OutputKey") == "UserPoolId":
            return output["OutputValue"]
    raise RuntimeError(f"Stack {stack_name!r} has no UserPoolId output")


def _attributes_to_dict(attributes: list[dict[str, str]]) -> dict[str, str]:
    """Flatten Cognito's `[{Name, Value}, ...]` shape into a plain dict."""
    return {a["Name"]: a.get("Value", "") for a in attributes}


def _group_names(cognito_client, user_pool_id: str, username: str) -> list[str]:
    """List Cognito group names for one user. Paginates internally."""
    groups: list[str] = []
    paginator = cognito_client.get_paginator("admin_list_groups_for_user")
    for page in paginator.paginate(UserPoolId=user_pool_id, Username=username):
        groups.extend(g["GroupName"] for g in page.get("Groups", []))
    return groups


def _build_registration(user: dict[str, Any], groups: list[str]) -> Registration:
    attrs = _attributes_to_dict(user.get("Attributes", []))
    return Registration(
        sub=attrs.get("sub", ""),
        email=attrs.get("email", ""),
        email_verified=attrs.get("email_verified", "false").lower() == "true",
        organization=attrs.get(f"custom:{CUSTOM_ATTRIBUTES[0]}", ""),
        role=attrs.get(f"custom:{CUSTOM_ATTRIBUTES[1]}", ""),
        reason=attrs.get(f"custom:{CUSTOM_ATTRIBUTES[2]}", ""),
        status=user.get("UserStatus", ""),
        enabled=bool(user.get("Enabled", False)),
        # Cognito returns timezone-aware datetimes; isoformat is stable across
        # CSV/JSON consumers and trivially sortable as a string.
        created_at=user["UserCreateDate"].isoformat() if user.get("UserCreateDate") else "",
        last_modified_at=user["UserLastModifiedDate"].isoformat() if user.get("UserLastModifiedDate") else "",
        groups=";".join(groups),
    )


def _list_registrations(cognito_client, user_pool_id: str) -> list[Registration]:
    registrations: list[Registration] = []
    paginator = cognito_client.get_paginator("list_users")
    for page in paginator.paginate(UserPoolId=user_pool_id):
        for user in page.get("Users", []):
            username = user.get("Username", "")
            if not username:
                continue
            groups = _group_names(cognito_client, user_pool_id, username)
            registrations.append(_build_registration(user, groups))
    return registrations


def _write_csv(registrations: list[Registration], stream) -> None:
    writer = csv.DictWriter(stream, fieldnames=COLUMNS)
    writer.writeheader()
    for reg in registrations:
        row = asdict(reg)
        # csv module renders Python booleans as `True`/`False`; lowercase
        # matches how every other CSV consumer (Sheets, Excel) interprets them.
        row["email_verified"] = "true" if reg.email_verified else "false"
        row["enabled"] = "true" if reg.enabled else "false"
        writer.writerow(row)


def _write_json(registrations: list[Registration], stream) -> None:
    json.dump([asdict(r) for r in registrations], stream, indent=2, default=str)
    stream.write("\n")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0] if __doc__ else "Export Cognito registrations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Requires AWS_PROFILE=lif (or equivalent credentials).",
    )
    parser.add_argument("env", help="Environment name (e.g. dev, demo).")
    parser.add_argument("--format", choices=("csv", "json"), default="csv", help="Output format (default: csv).")
    parser.add_argument("--output", help="Write to this path instead of stdout.")
    parser.add_argument(
        "--region",
        default=os.environ.get("AWS_REGION", "us-east-1"),
        help="AWS region (default: $AWS_REGION or us-east-1).",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = _parse_args(argv)

    session = boto3.session.Session(region_name=args.region)
    cfn = session.client("cloudformation")
    cognito = session.client("cognito-idp")

    user_pool_id = _stack_user_pool_id(cfn, args.env)
    registrations = _list_registrations(cognito, user_pool_id)

    writer = _write_csv if args.format == "csv" else _write_json
    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="") as stream:
            writer(registrations, stream)
        print(f"Wrote {len(registrations)} registration(s) from {user_pool_id} to {args.output}", file=sys.stderr)
    else:
        writer(registrations, sys.stdout)
        print(f"Wrote {len(registrations)} registration(s) from {user_pool_id}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
