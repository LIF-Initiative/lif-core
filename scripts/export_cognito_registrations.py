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
  AWS_PROFILE=lif uv run scripts/export_cognito_registrations.py dev
  AWS_PROFILE=lif uv run scripts/export_cognito_registrations.py demo --format json
  AWS_PROFILE=lif uv run scripts/export_cognito_registrations.py demo --output demo-registrations.csv
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
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError

# Adaptive retries with a generous attempt cap. The export does one
# AdminListGroupsForUser call per user (N+1); on larger pools that can
# brush against Cognito's per-account throttle. botocore's adaptive mode
# adds client-side congestion control on top of standard exponential
# backoff, which is exactly the shape we want for a "best-effort,
# eventually-completes" bulk read.
_RETRY_CONFIG = Config(retries={"mode": "adaptive", "max_attempts": 10})

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

# Cognito custom attributes — stored on the user as `custom:organization` etc.
# (see cloudformation/cognito-selfserve.yml). Inlined at the read sites rather
# than indexed positionally; reordering a constant tuple would silently scramble
# columns without that field-name anchor.


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
        # Cognito returns email_verified as the literal string "true" / "false"
        # when present; missing → not verified.
        email_verified=attrs.get("email_verified") == "true",
        organization=attrs.get("custom:organization", ""),
        role=attrs.get("custom:role", ""),
        reason=attrs.get("custom:reason", ""),
        status=user.get("UserStatus", ""),
        enabled=bool(user.get("Enabled", False)),
        # Cognito returns timezone-aware datetimes; isoformat is stable across
        # CSV/JSON consumers and trivially sortable as a string.
        created_at=user["UserCreateDate"].isoformat() if user.get("UserCreateDate") else "",
        last_modified_at=user["UserLastModifiedDate"].isoformat() if user.get("UserLastModifiedDate") else "",
        groups=";".join(groups),
    )


def _list_registrations(cognito_client, user_pool_id: str) -> list[Registration]:
    """Fetch every user + group membership. N+1 calls (one per user); prints a
    per-page count to stderr so the operator knows it's progressing — large
    pools can take minutes."""
    registrations: list[Registration] = []
    paginator = cognito_client.get_paginator("list_users")
    for page_num, page in enumerate(paginator.paginate(UserPoolId=user_pool_id), start=1):
        for user in page.get("Users", []):
            username = user.get("Username", "")
            if not username:
                continue
            groups = _group_names(cognito_client, user_pool_id, username)
            registrations.append(_build_registration(user, groups))
        print(f"  ...page {page_num}: {len(registrations)} users so far", file=sys.stderr)
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
        # Honor both env var conventions. AWS_REGION wins (matches boto3's own
        # precedence); fall back to AWS_DEFAULT_REGION (used by other scripts
        # in this repo, e.g. cfn-deploy.sh). Last-resort default: us-east-1.
        default=os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1",
        help="AWS region (default: $AWS_REGION, then $AWS_DEFAULT_REGION, else us-east-1).",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = _parse_args(argv)

    # All AWS calls happen inside this try, including session / client
    # construction. `boto3.session.Session(...)` can raise `ProfileNotFound`
    # (a BotoCoreError subclass) if AWS_PROFILE points at a missing profile;
    # `session.client(...)` can fail similarly. Keeping them inside the try
    # turns those into the same one-line operator-friendly message on stderr
    # instead of letting a traceback escape.
    # RuntimeError covers our own _stack_user_pool_id check when the stack
    # has no UserPoolId output (typo'd env, partially-deployed stack).
    try:
        session = boto3.session.Session(region_name=args.region)
        cfn = session.client("cloudformation", config=_RETRY_CONFIG)
        cognito = session.client("cognito-idp", config=_RETRY_CONFIG)
        user_pool_id = _stack_user_pool_id(cfn, args.env)
        registrations = _list_registrations(cognito, user_pool_id)
    except NoCredentialsError:
        print("error: no AWS credentials. Set AWS_PROFILE (e.g. AWS_PROFILE=lif) and retry.", file=sys.stderr)
        return 1
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "Unknown")
        msg = e.response.get("Error", {}).get("Message", str(e))
        print(f"error: AWS API call failed ({code}): {msg}", file=sys.stderr)
        return 1
    except BotoCoreError as e:
        print(f"error: AWS transport error: {e}", file=sys.stderr)
        return 1
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    writer = _write_csv if args.format == "csv" else _write_json
    # Catch I/O errors around both the open() and the write itself.
    # BrokenPipeError fires when the consumer (e.g. `... | head`) closes
    # the pipe early — exit silently with 0, that's not an error condition.
    # Other OSErrors (unwritable path, full disk, permission denied) get
    # the same one-line treatment as the AWS errors above.
    try:
        if args.output:
            with open(args.output, "w", encoding="utf-8", newline="") as stream:
                writer(registrations, stream)
            print(f"Wrote {len(registrations)} registration(s) from {user_pool_id} to {args.output}", file=sys.stderr)
        else:
            writer(registrations, sys.stdout)
            print(f"Wrote {len(registrations)} registration(s) from {user_pool_id}", file=sys.stderr)
    except BrokenPipeError:
        return 0
    except OSError as e:
        print(f"error: failed to write output: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
