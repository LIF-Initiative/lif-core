"""Fail-fast handling for auth secrets (#1191, #1179; ADR 0007).

Deliberately no fallbacks. A default secret would be a convenience for
developers that makes insecurity the default: a missing or misnamed variable
would stop being a loud startup failure and become a service running happily on
a publicly-known value. Callers resolve their secrets at import so a
misconfigured service fails to start instead of failing at a user's first login.
"""

import os
from typing import Optional

# Values that have shipped in this repo as code defaults, compose defaults, or
# documentation examples. They are public, so a secret set to one of them is
# treated as missing. Exact matches only: a longer local value that merely
# starts with "changeme" is the operator's explicit choice.
KNOWN_PLACEHOLDERS: frozenset[str] = frozenset(
    {
        "changeme",
        "changeme1",
        "changeme2",
        "changeme3",
        "changeme4",
        "changeme5",
        "changeme6",
        "change4",
        "replace",
        "replace-with-a-long-random-string",
    }
)


def resolve_secret(value: Optional[str], name: str, *, reject_placeholders: bool = True) -> str:
    """Return ``value`` stripped, or raise naming ``name`` if it is unset, blank, or a placeholder.

    ``reject_placeholders=False`` is for shared credentials that are not signing
    secrets and whose local demo value is a placeholder on both ends (e.g. the
    Example Data Source's ``API_TOKEN``). They must still be set.
    """
    if value is None or not value.strip():
        raise RuntimeError(
            f"{name} is not set. It is a signing secret, so there is no safe default. "
            f"Set {name} to a strong secret (in AWS it is supplied from SSM via the "
            f"service's taskdef-includes; locally, export it or set it in your .env)."
        )
    value = value.strip()
    if reject_placeholders and value in KNOWN_PLACEHOLDERS:
        raise RuntimeError(
            f"{name} is set to a placeholder value that is published in this repository. Set {name} to a strong secret."
        )
    return value


def require_env(name: str, *, reject_placeholders: bool = True) -> str:
    """Read the secret ``name`` from the environment via :func:`resolve_secret`."""
    return resolve_secret(os.environ.get(name), name, reject_placeholders=reject_placeholders)
