# `reference_data/transformations/` — versioned transformation groups

| File | What it is | Loaded by |
|---|---|---|
| `Ed-Fi-v5_StateU-LIF__v1.0.json` | Ed-Fi v5 → StateU LIF | [`scripts/import-transformations.sh`](../../scripts/import-transformations.sh) |
| `StateU-LIF_CLR-v2-Open-Badges-v3__v1.0.json` | StateU LIF → CLR v2 / Open Badges v3 | same |
| `StateU-LIF_Ed-Fi-v5-v1.0__v1.0.json` | StateU LIF → Ed-Fi v5 | same |
| [`StateU-LIF_Sample-LDE-Target-Test__v1.0.json`](StateU-LIF_Sample-LDE-Target-Test__v1.0.json) | **Test artifact.** StateU LIF → Sample LDE Target Test, 56 rules | `POST /transformation_groups/{id}/import` — see below |

> **`import-transformations.sh` does not load the last one.** It globs `*.json` in this directory
> and posts each match to `POST /transformation_groups/`, which requires numeric
> `SourceDataModelId` / `TargetDataModelId`. This group deliberately carries model *names*
> instead, so that endpoint answers **422** and the script exits 1. Until the script learns to
> skip it, either pass the other three explicitly or expect that one failure line.

---

## The Sample LDE Target Test artifacts

Hand-authored artifacts for proving, by manual steps, that every field the demo test users
actually populate in **StateU LIF** survives a Learner Data Export. Backing issue: [#1224 — LDE
export fidelity](https://github.com/LIF-Initiative/lif-core/issues/1224). Two halves:

| File | What it is |
|---|---|
| [`../schemas/sample-lde-target-test-model.json`](../schemas/sample-lde-target-test-model.json) | Target data model **Sample LDE Target Test v1.0**. Upload to MDR via `POST /datamodels/open_api_schema/upload`. |
| [`StateU-LIF_Sample-LDE-Target-Test__v1.0.json`](StateU-LIF_Sample-LDE-Target-Test__v1.0.json) | Its transformation group. Import via `POST /transformation_groups/{id}/import`. |

Guard tests for the two derived-value rules live in
[`test/reference_data/test_lde_export_test_transformations.py`](../../test/reference_data/test_lde_export_test_transformations.py).

---

## What the target model looks like

Deliberately **not** shaped like StateU LIF — the point is to exercise the translator, not to
rename fields. Six root entities, two of them with an embedded child:

```
Learner            (object)  identity header: keys, names, e-mails, provenance roll-up
Enrollment         (array)   one row per course; the resulting credential flattened to text
Award              (array)   one row per credential award; status re-coded
WorkHistory        (array)   one row per employment experience
  └ RelatedAward   (object)  the LIF *reference* to an award, embedded as a child
Skill              (array)   one row per proficiency; description truncated
CareerPreference   (object)  LIF EmploymentPreferences + PositionPreferences merged
  └ Mobility       (object)  relocation / remote / travel, re-expressed as codes and a phrase
```

The transformation group shows a range of translator behavior rather than 1:1 renames:

| Pattern | Example rule |
|---|---|
| Combine two attributes into one | `Learner.displayName` (`firstName` + `lastName`) |
| Select one item out of a multi-source list | `Learner.learnerKey` (predicate on `identifierType`) |
| De-duplicate across sources | `Learner.contactEmails`, every `sourceSystems` |
| Provenance roll-up | `WorkHistory.sourceSystems` — 7 LIF `informationSourceId` stamps → 1 list |
| Derived value the source model lacks | `Enrollment.status`, `WorkHistory.isCurrent` |
| Value mapping with a default | `Award.awardState` (`Granted`/`Completed` → `AWARDED`, else `UNKNOWN`) |
| Format normalization | `Award.awardedOn` (ISO timestamp *and* plain date → `YYYY-MM-DD`) |
| Truncation with a null guard | `Skill.skillSummary`, `WorkHistory.roleSummary` |
| Reference flattened to a string | `Enrollment.credentialEarned`, `WorkHistory.assertedByOrg` |
| Reference promoted to embedded child | `WorkHistory.RelatedAward.*` |
| Two source entities merged into one | all of `CareerPreference.*` |

Every expression that leans complex carries a JSONata `/* ... */` comment explaining the
non-obvious part, and each transformation's `Notes` field repeats the gist for the MDR UI.
The comments are worth reading — several document real traps (`(path)[0]` needs the
parentheses; a literal object passed inline to `$lookup` is silently re-read as a grouping
expression; `$length(null)` raises; `&` stringifies an array as JSON).

---

## Manual steps

Ports below are the local `deployments/advisor-demo-docker` stack; swap in an environment's
URLs and its MDR key to run elsewhere. `changeme3` is the local MDR service key.

**1 — Upload the target model.** Returns the new model's `Id`.

```bash
curl -s -X POST -H "X-API-Key: changeme3" \
  -F "file=@reference_data/schemas/sample-lde-target-test-model.json;type=application/json" \
  -F "data_model_name=Sample LDE Target Test" \
  -F "data_model_version=1.0" \
  -F "data_model_type=SourceSchema" \
  -F "contributor_organization=Unicon" \
  -F "state=Draft" \
  http://localhost:8012/datamodels/open_api_schema/upload
```

**2 — Create an empty seed group.** `POST /transformation_groups/{id}/import` derives the
source and target models from an existing group, so one has to exist first. Use
`SourceDataModelId` = StateU LIF and `TargetDataModelId` = the `Id` from step 1.

```bash
curl -s -X POST -H "X-API-Key: changeme3" -H "Content-Type: application/json" \
  -d '{"SourceDataModelId":17,"TargetDataModelId":30,"GroupVersion":"0.1",
       "Name":"StateU LIF_Sample LDE Target Test (seed)"}' \
  http://localhost:8012/transformation_groups/
```

**3 — Import the transformation group** against the seed group's id, into version `1.0`.
Expect `"ImportedTransformationCount": 56, "SkippedTransformationCount": 0`.

```bash
curl -s -X POST -H "X-API-Key: changeme3" -H "Content-Type: application/json" \
  --data @reference_data/transformations/StateU-LIF_Sample-LDE-Target-Test__v1.0.json \
  "http://localhost:8012/transformation_groups/30/import?version=1.0"
```

Any rule that did not land is listed in `SkippedTransformations` with a reason — that list is
the first thing to read if the export later looks thin.

**4 — Delete the seed group** so the LDE advertises only version `1.0`:
`DELETE /transformation_groups/{seed id}`.

**5 — Confirm the LDE offers the format.** `Sample LDE Target Test` should appear with
`TransformationVersions: ["1.0"]`:

```bash
curl -s http://localhost:8013/available-data-formats
```

**6 — Export a learner.**

```bash
curl -s -G http://localhost:8013/exports \
  --data-urlencode "learnerId=100004" \
  --data-urlencode "dataModelName=Sample LDE Target Test" \
  --data-urlencode "dataModelVersion=1.0" \
  --data-urlencode "dataModelContributorOrganization=Unicon"
```

**7 — Read the translator's counters**, which are the actual pass/fail signal (#1174):

```bash
docker logs --tail 50 advisor-demo-docker-lif-translator-org1-1 | grep "Translation complete"
# mappings=56 applied=56 discarded=0 eval_errors=0 non_object=0
```

`applied=56` with zero discards means every rule contributed. Anything less means the export
lost data, and `discarded` vs. `eval_errors` says which mechanism did it.

### Portability notes

- Every numeric `<id>:` prefix inside an `EntityIdPath` is **ignored** on import — paths resolve
  by `UniqueName`. The prefixes in these files (`17:` for StateU LIF, `30:` for the target) are
  documentation only, so the files import unchanged into any environment that has both models.
- `POST /transformation_groups/` accepts only `CreateTransformationGroupDTO`, which has no
  `Transformations` field. Posting a whole exported group file there creates an **empty** group
  and silently drops the rules; `/{id}/import` is the endpoint that carries them.

---

## Scope of the mapping, and what it cannot cover

The mapping targets the record the Query Planner actually composes for the LDE, not the raw
sample data. Two things narrow that record before the translator ever sees it:

1. **`/exports` requests nine fragments only** — `Person.Name`, `.Contact`, `.Identifier`,
   `.EmploymentLearningExperience`, `.PositionPreferences`, `.CredentialAward`,
   `.CourseLearningExperience`, `.Proficiency`, `.EmploymentPreferences`
   (hardcoded in `bases/lif/learner_data_export_api/learner_data_export_endpoints.py`, flagged
   there as FUTURE WORK). Sample-data fragments outside that list — `Birth`, `Demographics`,
   `Language`, `SexAndGender`, `Residency`, `MilitaryLearningExperience`,
   `AssessmentLearningExperience`, `ProgramLearningExperience` — are unreachable by the LDE
   regardless of the transformation group.
2. **Per-source GraphQL queries select a subset** of each fragment's attributes, so e.g.
   `Contact.Address` and `Contact.Telephone` are populated in the sample data but never appear
   in the composed record.

Within that record, the mapping covers **all 84 populated leaf paths** observed across the test
users, and every one of the 56 target attributes is populated for at least one of them.

**Three groups of rules carry approximate source lineage**, marked in their `Notes`. The
composed LIF record contains data that the StateU LIF model does not declare, so there is no
legal `EntityIdPath` for it and the rule declares its nearest owning attribute instead:

- `Person.EmploymentLearningExperience.{Asserted,Offered,Approved}ByRefOrganization.*` and
  `RefPosition.OfferedByRefOrganization.*` — `Organization` is not an entity in StateU LIF (17)
  at all.
- `Person.CredentialAward.id` — `id` is not a declared attribute of `Person.CredentialAward`.

The JSONata reads those paths fine; only the declared lineage is approximate. Worth folding
into #1224 as evidence: a transformation author cannot express, in MDR, a mapping for data the
org's own model does not declare.

---

## Known gap found while verifying this (not fixed here)

- **Sarah (100003) and Tracy (100006) cannot be exported at all** — `/exports` returns 404
  because the Query Planner returns `[]` for them. Its own log shows it *received* full
  fragments from org2 and the example data source and saved them to the query cache, then
  re-queried the cache, found 0 records, and returned nothing. The other four test users work.
  This is upstream of the translator; the transformation group is not involved.

---

## Keeping the two files in sync

They are two halves of one thing: every transformation's `TargetAttribute.EntityIdPath` has to
name an entity and attribute that exist in the model file, by `UniqueName`. Adding or renaming a
target attribute means editing both. After any edit, re-run the manual steps and check that
`applied` in the translator's counter line still equals the number of rules in the group — a
mismatch is the whole failure mode #1224 is about, and it is silent in the HTTP response.
