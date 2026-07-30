# demo_personas

Single source of truth for the six curated **demo learner personas** used across
LIF demo surfaces.

## Why

The Advisor app and the LDE test/export playground (#1036) both present the same
set of demo learners. Defining them once here prevents a second copy drifting.

## Public surface

- `DemoPersona` — frozen dataclass: `username`, `firstname`, `lastname`,
  `identifier`, `identifier_type`, `identifier_type_enum`.
- `get_demo_personas() -> list[DemoPersona]`
- `get_demo_personas_as_dicts() -> list[dict]` — convenience for building the
  Advisor's `users_db` or a JSON response.

## Consumers

- `bases/lif/advisor_restapi` — builds its demo-login `users_db` from this list.
- LDE test/export playground (planned, #1036) — the learner picker; uses the
  identity fields (ignores `username`). Browser delivery is via a small
  read-only endpoint rather than baking the list into the bundle.

The data is synthetic and safe to surface in demo UIs. This is the *curated*
demo set — deliberately unrelated to Query Planner cache state (see the
control-plane monitoring note on #1041) and not an authoritative learner
directory (LIF is federated).
