# ADR 0002: LIF control plane for identity & developer keys (MDR as interim host)

Date: 2026-07-13

## Status

Proposed

Extends [ADR 0001: API and User Auth](auth.md) and amends the #1000 design spike (which proposed
storing developer keys "in MDR"). Extraction tracked by the epic #1041.

## Context

A core LIF goal is that components/microservices stay independent enough for deployers to choose what
they run alongside their existing data infrastructure. MDR's unique value is the **metadata/schema
registry**.

The LDE self-service API-key work (#1000) initially placed key issuance + management and the Cognito
identity it depends on **in MDR** (#1033 store/endpoints, #1035 UI). Taken literally, that makes MDR a
**fleet-wide auth dependency**: any API service that wants API-key auth — and any deployer who wants,
say, only the Learner Data Export API over their own warehouse — would have to stand up the full MDR
just to issue/manage keys. That conflates two domains (metadata registry vs. platform auth/admin) and
cuts against the independence goal.

Two things are worth separating, because only one is actually coupled:

- **Validation** is *not* coupled. With signed API keys (`lifk_<payload>.<hmac>`, payload carrying the
  key id + owner + workspace, signed with a shared secret), a service like LDE **verifies a key
  offline** — no runtime call to the issuer. The only residual coupling is *revocation freshness*,
  handled by short expiry or a small cached revocation list, not a per-request hop.
- **Issuance + management + identity** *is* centralized: the "generate / list / revoke" UI, the key
  store, and the Cognito sign-in they hang off. This is the only piece that needs a home.

## Decision

The key/identity **control plane** — identity (Cognito), developer-key issuance/management, and
cross-cutting **admin dashboards/monitoring** — is conceptually a **dedicated LIF control-plane
service**, not MDR. MDR remains the metadata registry and consumes the control plane like any other
service.

We phase into it rather than greenfield it now:

1. **Near-term:** host the LDE keys "in MDR" but as **self-contained Polylith bricks** — `developer_keys`
   (store + issuance) and `cognito_auth` (verify) — with **no imports into MDR-domain services**. MDR is
   the *interim host, not the owner*.
2. API services validate keys via **signed-token offline verification** (shared secret), so they take
   **no runtime dependency on MDR**.
3. Because the logic is bricked and validation is offline, **extracting the bricks into the control-plane
   service later is a re-deploy, not a rewrite** — callers keep verifying tokens identically; only the
   issuance host moves.

## Alternatives

- **MDR as the permanent host.** Rejected: couples fleet-wide auth to MDR, conflates the metadata and
  platform-admin domains, and forces MDR onto deployers who don't otherwise need it.
- **Build the dedicated control-plane service now.** Rejected for the near term: the team needs LDE keys
  soon, and the self-serve Cognito identity already lives around MDR (#882/#883/#884), so greenfielding
  the service (and moving identity) is a larger effort than the immediate need — and it can be reached
  incrementally via the bricks path above.
- **Per-service embedded keys / no central issuer.** Rejected: fragments the developer experience and
  identity, and scatters key state across services.

## Consequences

- Near-term LDE keys ship hosted in MDR (interim), implemented as portable bricks; #1033/#1035 PRs and
  issues are annotated as "MDR = interim host per this ADR."
- API services stay free of a runtime MDR dependency (offline signed-token validation); revocation
  freshness is a deliberate trade handled by expiry / cached revocation.
- A follow-up **epic (#1041)** tracks the extraction into a control-plane service.
- **Identity ownership is the bigger open question.** The Cognito self-serve identity is MDR's today;
  moving it to the control plane is broader than keys and needs its own design spike before we commit —
  this ADR does not decide it, only names it.

## References

- #1000 (LDE: expand auth) and its design spike; children #1033–#1036
- Epic #1041 (control-plane extraction)
- [ADR 0001: API and User Auth](auth.md)
- [`docs/design/cross-cutting/self-serve-tenant-auth.md`](../../cross-cutting/self-serve-tenant-auth.md)
