# ADR 0008: A control-plane key's owner is a Cognito sub, and its workspace is the tenant schema name

Date: 2026-11-03

## Status

Accepted

Extends [ADR 0006](0006-control-plane-key-store-ownership.md), decision 3, which gave the control
plane's key store an explicit workspace column but left open what identifies a workspace and how
issuance checks that the caller belongs to it. Decided on #1190 (Q1 and Q2), part of epic #1041.

## Context

The control plane's key table (#1182) has to fix two columns before its first migration ships, and
both are expensive to change afterwards, because #1183 copies the live dev and demo keys into that
table.

- **The owner.** Today's keys are owned by `OwnerSub`, the caller's Cognito `sub`. MDR refuses to
  issue a key without one: `_require_owner_sub` returns a `400` when `request.state.cognito_sub` is
  unset (`bases/lif/mdr_restapi/developer_api_key_endpoints.py:20-29`). Local logins (#1316) carry only
  a username and no `cognito_sub`, so they can't issue keys. If they could, a bare `sub` would no
  longer identify an owner uniquely, and the column would have to become issuer-qualified (for
  example `cognito:<sub>` / `local:<username>`).
- **The workspace.** No table records a workspace. A workspace is the pair (Cognito group,
  `tenant_{sanitized group}` schema), worked out on every request (`components/lif/tenant_routing/core.py`,
  `components/lif/mdr_services/workspace_service.py:119`). The schema is its only durable record. In
  MDR, a key's workspace is whichever schema the request's `search_path` selected, and the row itself
  has no workspace column (ADR 0006, Context).
- **Choosing a workspace.** MDR picks among a user's groups with the `lif_workspace` cookie, which is
  HMAC-signed with MDR's JWT secret and rechecked against `cognito:groups` on each request
  (`components/lif/mdr_auth/workspace_cookie.py`). The control plane doesn't hold that secret, so it
  can't read the cookie.

The options were laid out on #1190 in a comment dated 2026-10-07.

## Decision

1. **Local-login users can't issue developer keys (#1190 Q1).** The owner column stays a bare
   Cognito `sub` (`OwnerSub`), as it is in MDR today, so #1183 copies existing values unchanged. The
   control plane authenticates Cognito tokens only (`lif.auth`'s `cognito_strategy`, ADR 0007).
2. **A workspace is identified by its tenant schema name, stored as an opaque string (#1190 Q2).**
   The control plane stores and compares the value, but never parses it or builds it from parts, and
   never relies on the `tenant_` prefix. The group-to-schema rule stays in the pure `tenant_routing`
   brick, which the control plane imports without depending on MDR.
3. **The request names the workspace explicitly**, as a field or query parameter, since the control
   plane can't read MDR's signed cookie.
4. **Membership is checked against the token on every request that names a workspace.** A caller
   belongs to workspace `W` when one of their `cognito:groups` satisfies
   `tenant_schema_for_group(group) == W`, the same rule MDR's `find_workspace` applies. A caller who
   doesn't belong gets a `403`.
5. **Issuing and listing are per workspace, and revoking is by owner.** Creating a key and listing
   keys both name a workspace and require membership. Listing returns only the caller's own keys in
   that workspace. Revoking needs only ownership of the key, so someone who has left a group can
   still revoke a key they issued while in it. A key that isn't the caller's is a `404`, as in MDR,
   so other users' key ids aren't revealed.

## Alternatives

- **Let local logins issue keys, with an issuer-qualified owner.** Not chosen now. It would change
  the column's format and make #1183 rewrite every existing value to `cognito:<sub>`. If local-login
  keys are wanted later, that rewrite is the cost.
- **Identify a workspace by its Cognito group name.** Rejected. Local logins have no group, renaming
  a group would orphan its workspace's keys, and two group names can map to one schema (below).
- **A new control-plane workspace ID**, from a `Workspaces` table that maps an ID to a schema and an
  identity-provider group. Deferred, not rejected. It's the most correct shape, but owning workspace
  records is the identity-ownership question the rest of #1190 holds. If that work adopts it, the
  switch is a one-time backfill from the schema names.
- **Per-workspace revocation as well.** Rejected (Dereck, 2026-11-03): a user removed from a group
  couldn't revoke the keys they issued there.

## Consequences

- **The smallest change from what runs today.** The owner column keeps its values, and the workspace
  column for each copied row is just the schema it came from, so #1183 has nothing to look up or
  invent.
- **The workspace matches what key consumers route on.** The LDE and the Translator reach MDR by
  schema name (`components/lif/mdr_client/core.py`, `components/lif/translator_client/core.py`).
- **The control plane depends on the `tenant_routing` brick**, so its project packages that brick and
  its deploy workflow's `paths:` must watch it (#1171).
- **It inherits MDR's naming, despite ADR 0006's caution.** Treating the value as opaque limits that:
  if the schema rule changes, only `tenant_routing` changes. A rename of existing schemas would need
  a data migration of the workspace column too.
- **Two group names can map to one schema.** For example, `Foo-Bar` and `foo_bar` both give
  `tenant_foo_bar`, and nothing detects it. A member of either group passes the membership check for
  that workspace. That matches what MDR does with the same groups today, so it adds no new access, but
  it's an existing gap (noted on #1190).
- **Local-login deployments get no developer keys from the control plane.** A Cognito-less test drive
  (#1316) that wants developer keys can't have them until this decision is revisited.
- **Removing a user from a group doesn't revoke their keys.** They can no longer list or issue keys
  in that workspace, but keys already issued stay valid until revoked. Revoking on membership change
  is out of scope here. Until #1184 makes keys authenticate anything, a stale key grants nothing.

## References

- #1190 (options laid out 2026-10-07; Q1/Q2 answered by bjagg 2026-11-03),
  #1182 (the key table and endpoints), #1183 (the copy), #1184 (key validation), epic #1041
- [ADR 0006](0006-control-plane-key-store-ownership.md) (extended), [ADR 0002](0002-lif-control-plane-vs-mdr-host.md),
  [ADR 0007](0007-single-auth-brick-with-provider-adapters.md)
- #1316 (local logins)
