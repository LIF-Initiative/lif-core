# MDR: validate transformation output against the target schema

**Status:** Proposed
**Date:** 2026-06-02
**Author:** bjagg
**Tracking issue:** [#973](https://github.com/LIF-Initiative/lif-core/issues/973)

> Validate the assembled output of the MDR bulk-transform preview against the target LIF JSON Schema (Ajv) and surface shape/casing/required-field errors at authoring time, instead of only at runtime in the translator.

## Problem

The MDR Mappings "bulk transformations" preview evaluates a group of JSONata expressions, deep-merges their results into a combined output object, and shows it next to the (optionally displayed) target schema. It catches **JSONata evaluation** errors per expression — but it does **not** check whether the *assembled output* actually conforms to the target LIF schema. An author can write transformations that evaluate cleanly yet emit data the translator will later reject (wrong shape, wrong PascalCase/camelCase casing, missing required fields, wrong scalar type). That failure only surfaces at runtime, far from where the mapping was authored.

The runtime translator already validates against the schema (`components/lif/translator/core.py` — applies JSONata then validates the result). This proposal brings the same check forward into the authoring UI for fast feedback.

## Current state

- `frontends/mdr-frontend/src/utils/jsonataUtils.ts` → `evaluateAndCombineExpressions(expressions, inputSample)` returns `{ output, errors }`, where `errors` are **JSONata evaluation** errors only (per expression). The merged object is `output` (built via `deepMerge`).
- `frontends/mdr-frontend/src/pages/Explore/Mappings/components/BulkTransformationsBody.tsx`:
  - Already receives a **`targetSchema` prop** — currently commented "reserved for future use" (line ~13). It is in fact **already wired**: `MappingsView.tsx:2967` passes `targetSchema={targetJsonSchema}` → `BulkTransformationsDialog` → `BulkTransformationsBody`. So the target JSON Schema is available in the component today with no new plumbing.
  - Already renders `targetSchema` in the output pane's "Schema" view (line ~372), and holds `combinedOutput` + `errorMap` state, recomputed in a debounced effect.
- **`ajv` is not yet a dependency** of `mdr-frontend` (only `jsonata`).

## Approach

1. **Add `ajv` (+ `ajv-formats`)** to `frontends/mdr-frontend` dependencies. Both are **MIT-licensed** (the same permissive license as the `jsonata` dependency already in `mdr-frontend`), so they're clear for open-source use.
2. **New pure util** `validateOutputAgainstSchema(output, schema) → { valid: boolean; errors: { path: string; message: string }[] }` (e.g. in `src/utils/schemaValidation.ts`):
   - Compile with `new Ajv({ allErrors: true, strict: false })` + `ajv-formats` so unknown/format keywords don't throw; **memoize the compiled validator per schema reference** (compiling is the expensive step).
   - Map Ajv errors to friendly rows: `instancePath` (or `/` for root) + `message` (+ the offending keyword, e.g. `required`, `type`, `additionalProperties`).
   - MDR-generated schemas **inline all `$ref`s** (per CLAUDE.md "MDR schemas have no `$ref`"), so no ref-resolution/meta-schema loading is needed.
3. **Wire into the preview effect** in `BulkTransformationsBody`: after `combinedOutput` is computed, if `targetSchema` is present, run the validator and store results in **new state `schemaErrors`**, kept distinct from the JSONata `errorMap` (different failure class, different fix).
4. **Surface in the output pane:** a small validity indicator — `✓ Valid against target schema` or `N schema issue(s)` — with an expandable list of `path → message` rows. Visually separate from the per-card JSONata evaluation errors so authors can tell "expression failed to run" from "result doesn't fit the schema."

## Design considerations

- **`additionalProperties` noise.** If the target schema sets `additionalProperties: false`, a stray output key (often a casing mistake) flags as an error. That error **is the feature working as intended**: surfacing a PascalCase/camelCase slip at authoring time — rather than letting it through to fail at runtime in the translator — is precisely the value this check adds. But it can be noisy; consider grouping "unexpected property" separately from "missing required / wrong type," or a toggle to mute extra-property findings. Decide during implementation against a real generated schema.
- **Casing convention.** Ajv validates structure; the generated target schema already encodes the LIF PascalCase-entity / camelCase-scalar convention, so a casing error manifests as `additionalProperties` (wrong key) + `required` (missing correct key) — exactly the feedback we want.
- **Performance.** Compile once per schema (`useMemo` on the schema reference); validation itself is fast and runs inside the existing **debounced recompute effect** — the `useEffect` in `BulkTransformationsBody` that already rebuilds `combinedOutput` a short delay *after* the author stops editing (so it fires once per edit-pause, not on every keystroke). Schema validation piggybacks on that same effect, adding no new render path.
- **Non-blocking.** This is authoring feedback only — it does **not** block saving transformations. It mirrors, and front-runs, the translator's runtime validation.

## Testing

`mdr-frontend` currently has **no test runner** (no vitest/jest; `package.json` scripts are dev/build/lint/preview only). The validation util is pure and the prime candidate for a unit test. Recommend adding a minimal **vitest** harness to `mdr-frontend` (mirroring what PR #982 did for `lif_advisor_app`) and testing: valid output → `{valid:true}`; a missing-required field; a wrong-type scalar; an unexpected (mis-cased) property; empty/no schema → no-op. If a harness is deemed out of scope, fall back to manual verification — the util is small and low-risk — and track the harness under the frontend-CI follow-up (#981 covers the advisor app; MDR would be analogous).

## Sequencing

**Independent of the advisor streaming/auth stack.** #973 touches only `mdr-frontend` (`jsonataUtils.ts`/a new util + `BulkTransformationsBody.tsx` + `package.json`); no file overlap with #970/#971/#972/#974 or PRs #975/#978/#982/#984. It can be implemented at any time.

## Out of scope

- Validating each individual expression's partial output (we validate the merged result).
- Blocking save on schema-invalid output.
- Schema authoring / editing the target schema.
- A general MDR frontend test harness beyond the one util (track separately).
