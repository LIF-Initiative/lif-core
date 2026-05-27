"""Workspace listing for MDR self-serve (issue #884 Phase 3 PR 1).

Pure helpers — given a list of Cognito groups (from the JWT
``cognito:groups`` claim), build the list of workspaces the user has
access to. Each workspace is a (group, tenant_schema) pair.

Schema existence is *not* verified here; the post-confirmation Lambda
provisions a schema for every group it creates, so a group claim that
sanitizes to a valid schema name is treated as a usable workspace. If a
group somehow exists in Cognito without a matching PG schema, queries
against it will fail loudly at session time — that's the right place to
surface the divergence rather than papering over it in this listing.
"""

from dataclasses import dataclass

from pydantic import BaseModel

from lif.tenant_routing import tenant_schema_for_group


@dataclass(frozen=True)
class Workspace:
    """A tenant workspace the caller has access to."""

    group: str
    tenant_schema: str


class WorkspaceItem(BaseModel):
    """API response shape for a workspace.

    Separate from the internal ``Workspace`` dataclass so the wire
    contract can evolve independently of in-process types.

    ``display_name`` is the human-friendly label the SPA shows in the
    workspace picker + header indicator (issue #943). For a user's own
    auto-created personal tenant (``eval-<their-cognito-sub>``), this is
    their email — meaningful to the user and consistent with how the
    rest of the LIF stack identifies them. For shared / invited groups
    (``lif-team`` and future named teams), it's the group name itself.
    The technical ``tenant_schema`` stays on every record so the picker
    can still surface it as secondary text.
    """

    group: str
    tenant_schema: str
    display_name: str


def compute_display_name(group: str, cognito_sub: str | None, principal: str | None, tenant_schema: str) -> str:
    """Resolve a friendly display name for a Cognito group (issue #943).

    For the user's own personal tenant (``eval-<their-sub>``), where we
    can confidently match the JWT's ``sub`` against the group's suffix,
    use the user's email — which the auth middleware stores as
    ``request.state.principal`` for Cognito users with a verified
    email claim. The ``@`` is intentional; PM call on 2026-05-26
    explicitly confirmed it's fine in the UI.

    For any group that isn't the caller's own ``eval-<sub>``, use the
    group name. That covers shared groups (``lif-team``, future named
    teams), invited memberships, and the edge case where ``principal``
    is a raw sub (legacy HS256 path, no email claim).

    ``tenant_schema`` is the ultimate fallback. The wire contract for
    ``display_name`` is "never empty"; if both the personal and group
    paths somehow produced an empty/whitespace-only string (group is
    impossibly empty, principal is whitespace-only, etc.), the schema
    name is preferable to a blank label in the SPA. Per Adam Hungerford
    review of #947 — defense in depth on a server-side invariant the
    frontend now relies on.
    """
    if cognito_sub is not None and principal is not None and "@" in principal and group == f"eval-{cognito_sub}":
        candidate = principal
    else:
        candidate = group
    candidate = candidate.strip()
    return candidate if candidate else tenant_schema


def to_workspace_item(
    workspace: Workspace, *, cognito_sub: str | None = None, principal: str | None = None
) -> WorkspaceItem:
    """Project a service-layer ``Workspace`` into its API response shape.

    Computes ``display_name`` from the optional caller-identity hints.
    Callers without identity context (tests that don't care about the
    friendly label) get ``display_name = group`` (or ``tenant_schema``
    if the group somehow sanitizes to empty), matching pre-#943
    behavior modulo the empty-string defense.
    """
    return WorkspaceItem(
        group=workspace.group,
        tenant_schema=workspace.tenant_schema,
        display_name=compute_display_name(workspace.group, cognito_sub, principal, workspace.tenant_schema),
    )


def list_workspaces_for_groups(cognito_groups: list[str] | None) -> list[Workspace]:
    """Map Cognito groups to the user's accessible workspaces.

    Skips groups that sanitize to an empty schema name (e.g., punctuation-
    only group names that shouldn't have produced a tenant in the first
    place). Preserves Cognito's group ordering so the first entry matches
    the default-fallback used by ``resolve_tenant_schema``.
    """
    if not cognito_groups:
        return []
    workspaces: list[Workspace] = []
    for group in cognito_groups:
        schema = tenant_schema_for_group(group)
        if schema is None:
            continue
        workspaces.append(Workspace(group=group, tenant_schema=schema))
    return workspaces


def find_workspace(cognito_groups: list[str] | None, group: str) -> Workspace | None:
    """Return the Workspace for ``group`` if and only if the caller has access.

    Used by the /tenants/select endpoint and the auth middleware's cookie
    validator: in both cases, the caller proposes a group name and we need
    to confirm it's actually one of theirs (defense in depth — the Cognito
    JWT is the source of truth for group membership; never trust the
    client's request body or cookie alone).
    """
    if not cognito_groups or group not in cognito_groups:
        return None
    schema = tenant_schema_for_group(group)
    if schema is None:
        return None
    return Workspace(group=group, tenant_schema=schema)
