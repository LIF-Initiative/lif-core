"""Tenant-schema resolution for multi-tenant LIF services (issue #883).

Pure functions with no framework or service dependencies. Currently used by
the MDR auth middleware (to set ``request.state.tenant_schema``) and the
MDR tenant-provisioning service (to derive the schema name for a new
Cognito group). Extracted from ``lif.mdr_auth.tenant`` so other auth-gated
services — Advisor, LIF API — can reuse the same sanitize/resolve contract
without taking a dependency on MDR.

Tenant schemas are named ``tenant_{sanitized-group-name}`` and must fit PG's
63-char identifier limit. Group names come from Cognito and can contain
characters (hyphens, case mix) that PostgreSQL treats as identifier-hostile
without quoting; we sanitize rather than quote so the schema name is stable
across every code path that constructs it.
"""

import re

MAX_GROUP_NAME_LEN = 55
"""Max sanitized group length so ``tenant_{name}`` stays within PG's 63-char identifier limit."""

SCHEMA_PREFIX = "tenant_"

_SANITIZE_RE = re.compile(r"[^a-z0-9_]+")
_LEADING_NON_LETTER_RE = re.compile(r"^[^a-z]+")


def sanitize_group_name(group: str) -> str:
    """Convert a Cognito group name into a PG-identifier-safe token.

    - Lowercased
    - Non-[a-z0-9_] runs collapsed to a single underscore
    - Leading non-letter chars stripped so the result starts with a letter
    - Truncated to ``MAX_GROUP_NAME_LEN``

    Returns an empty string if nothing usable remains; callers must treat
    that as "no tenant derivable" rather than route to a bogus schema.
    """
    lowered = group.lower().strip()
    collapsed = _SANITIZE_RE.sub("_", lowered).strip("_")
    trimmed = _LEADING_NON_LETTER_RE.sub("", collapsed)
    return trimmed[:MAX_GROUP_NAME_LEN]


def tenant_schema_for_group(group: str) -> str | None:
    """Return the ``tenant_{group}`` schema name for a Cognito group, or None.

    None means the group sanitizes to an empty string — the caller should
    fall back to the service/default schema rather than constructing
    ``tenant_`` with an empty suffix.
    """
    sanitized = sanitize_group_name(group)
    if not sanitized:
        return None
    return f"{SCHEMA_PREFIX}{sanitized}"


def resolve_tenant_schema(
    *, enabled: bool, is_service_principal: bool, cognito_groups: list[str] | None, service_schema: str
) -> str | None:
    """Resolve which PG schema a request should run against.

    Args:
        enabled: The ``mdr__tenant_routing__enabled`` feature flag.
        is_service_principal: True when the caller authenticated via API key.
        cognito_groups: The ``cognito:groups`` claim, or None for non-Cognito
            callers (API key, legacy HS256 JWT).
        service_schema: The schema API-key callers (and Cognito users with no
            resolvable group) route to. Configured per-env; "public" until
            the PR 3 cutover renames it to "tenant_lif_team".

    Returns:
        The schema name to set via ``SET search_path``, or None to leave the
        connection on its default (PG's own ``"$user", public``). None means
        the session will behave exactly as it did before tenant routing was
        introduced — this is the short-circuit for the feature flag.
    """
    if not enabled:
        return None

    if is_service_principal:
        return service_schema

    if cognito_groups:
        schema = tenant_schema_for_group(cognito_groups[0])
        if schema is not None:
            return schema

    return service_schema
