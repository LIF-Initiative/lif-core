# Issue Prioritization — Q1 2026

**Date:** 2026-02-24
**Context:** 2 devs at ~50% capacity for 3 months (through end of March for feature work), then docs and cleanup through end of June (contract end).
**Capacity:** ~520 dev-hours through March, then docs/cleanup mode.

---

## Likely Already Done — Verify and Close

These open issues have merged PRs and should just need verification before closing:

| # | Title | Evidence |
|---|-------|----------|
| 833 | Convert legacy entityIdPaths to CSV | PRs #834, #831 merged |
| 830 | EntityAttributeAssociation missing Extension field | PR #850 merged |
| 812 | Review GH workflow scripts for consistency | PR addressed |
| 811 | MDR API: Don't allow spaces in name/uniqueName | PR merged (UI side in PR #822) |
| 799 | Remove need for docker in pytest tests | PR merged |
| 771 | Expose export transformation group endpoint | PR merged |
| 715 | SPIKE: Review Advisor/Semantic Search tuning | PR merged |
| 717 | Fetch OpenAPI schema from MDR instead of file | Done via PRs #854, #853 (schema loading refactor) |
| 670 | Add PR Template & Reviewer Checklist | PR #829 merged |
| 674 | Implement Flyway for MDR Schema Changes | Already in place (SAM + Flyway infrastructure exists) |
| 741/743 | Advisor login hangs on bad password | Likely resolved by PR #861 (demo user password to env var) |

**Action: Verify and close ~11 issues. Estimated effort: 1–2 hours.**

---

## Tier 1: Must Do — Demo Stability & Data Quality

**Estimated effort: 60–80 hours**

Fixes broken demo functionality or blocks the evaluator experience.

| # | Title | Est | Assignee | Notes |
|---|-------|-----|----------|-------|
| 847 | MDR dev issue (duplicate ID sequences) | 4–6h | cbeach47 | Active bug, blocks dev work |
| 851 | Partner Filter/View for OrgLIF always empty | 4–6h | — | Broken demo feature |
| 756 | MDR schema creation by upload not honoring refs | 6–8h | cbeach47 | Core MDR functionality |
| 776 | MDR responds with database error in response | 4–6h | — | Leaks internal details |
| 757 | Org3 proficiency names not displayed in Advisor | 4–6h | — | Broken demo data |
| 810 | Remove spaces in MDR entity/attribute names | 6–8h | thelmick | Data cleanup, blocks #801 |
| 801 | MDR UI: Don't allow spaces in name/uniqueName | 4–6h | cbeach47, ahungerford | PR #822 open — needs regex fix (see PR review comment about dots in UniqueName) |
| 729 | Query Planners for Org2/Org3 not finding data | 6–8h | — | Broken multi-org demo |
| 816 | Moving multi-source transform loses attributes | 4–6h | — | Data loss bug in MDR UI |

---

## Tier 2: High Value — MDR Portability & Self-Serve Foundation

**Estimated effort: 80–120 hours**

Enables the tenant isolation work (`mdr-tenant-isolation-cognito.md`) and data portability. These are pre-requisites for the self-serve demo capability.

| # | Title | Est | Assignee | Notes |
|---|-------|-----|----------|-------|
| 772 | Expose import transformation group endpoint | 6–8h | cbeach47 | Needed for data portability |
| 773 | MDR Transformation Portability: UX Support | 8–12h | ahungerford | Pairs with #772 |
| 774 | Expose UX widget to delete transformation group | 4–6h | — | Completes transformation portability |
| 762 | Portable search for existing attributes on upload | 4–6h | cbeach47 | Part of portable upload set |
| 763 | Portable search for existing valuesets on upload | 4–6h | cbeach47 | Part of portable upload set |
| 764 | Portable search for existing values on upload | 4–6h | cbeach47 | Part of portable upload set |
| 765 | Portable search for existing entities on upload | 4–6h | cbeach47 | Part of portable upload set |
| 768 | Support data model ID mapping on upload | 8–12h | ahungerford | Key for import portability |
| 746 | Enforce unique names for exportable items | 4–6h | cbeach47 | Data integrity guardrail |
| 858 | Don't allow mapping unmapped entities/attributes | 4–6h | — | MDR quality guardrail |
| 856 | Align association create/update logic | 6–8h | — | MDR consistency |
| 857 | Association extension data cleanup | 4–6h | — | MDR data quality |

---

## Tier 3: Documentation & Cleanup (post-March)

**Estimated effort: 40–60 hours**

Ideal for the April–June docs/cleanup phase.

| # | Title | Est | Assignee | Notes |
|---|-------|-----|----------|-------|
| 805 | MDR technical documentation (single source of truth) | 8–12h | thelmick | |
| 785 | LIF MDR Guide (Documentation) | 8–12h | thelmick | |
| 661 | Document: how LIF data model differs from a standard | 4–6h | — | Key conceptual doc |
| 733 | Add builder-focused explanation of demo | 4–6h | — | Community onboarding |
| 740 | Document recommended branching strategy | 4–6h | — | Infrastructure docs |
| 739 | Document GitHub Actions pathing | 2–4h | — | Infrastructure docs |
| 736 | Docs: Review Adapter design docs | 4–6h | — | Orchestrator docs |
| 732 | Finalize README for Dagster OSS release | 4–6h | — | Release prep |
| 708 | Delete spreadsheets and python script from repo | 1–2h | — | Quick cleanup |
| 678 | Clean up leftover code from initial buildout | 8–12h | cbeach47 | |
| 660 | Clean up MDR Frontend in lif-main | 4–6h | — | UI tech debt |
| 664 | MDR Frontend cleanup & structure improvements | 4–6h | — | UI tech debt |
| 751 | Publish LIF test plan | 4–6h | — | |
| 693 | Add component-level captured I/O tests | 6–8h | — | |
| 826 | Prevent referencing non-embedded entities/attributes | 4–6h | — | MDR guardrail |
| 775 | On upload, list which data model IDs are in import file | 4–6h | — | MDR UX improvement |
| 848 | Visible version number for MDR/LIF codebase | 2–4h | — | Quick win |
| 814 | Change refs to start with lowercase in JSON samples | 2–4h | — | Quick cleanup |
| 788 | MDR: Prompt for organization name | 2–4h | — | MDR UX improvement |

---

## Tier 4: Spikes & Nice-to-Have (Defer or Descope)

These are investigation items or features that likely don't fit the remaining window. Recommend closing with a "deferred" comment or moving to a backlog milestone.

### Research Spikes

| # | Title | Notes |
|---|-------|-------|
| 804 | SPIKE: Get data out of LIF in non-LIF format | Defer unless directly needed |
| 723 | SPIKE: Bidirectional translations | Defer |
| 721 | SPIKE: Alternative translation patterns | Defer |
| 720 | SPIKE: Custom code translations | Defer |
| 719 | SPIKE: Enum translation approach | Defer |
| 714 | SPIKE: Review x-queryable usage and configuration | Defer |
| 713 | SPIKE: Advisor prompting for job position preferences | Defer |
| 688 | Spike: GraphQL behavior & library evaluation | Defer |
| 684 | Spike: Revisit data issues from R1.1 | Defer |
| 683 | Spike: Update MDR to allow mapping to Base LIF | Defer |
| 694 | Spike: Query Planner job cache | Defer |

### Feature Work

| # | Title | Notes |
|---|-------|-------|
| 808 | Add Organization as queryable root entity | Feature — defer |
| 692 | Add top-level GraphQL queries for Org, Course, Credential | Feature — defer |
| 689 | Build processor to unroll non-person references | Feature — defer |
| 696 | Build processor to make entities lowercase for GraphQL | Feature — defer |
| 690 | Normalize SEDS Title Case vs GraphQL enum ALL_CAPS | Feature — defer |
| 654 | Integrate identity mapper with Orchestrator | Large feature — defer |
| 803 | Spike: Frontends deployed in shared S3 bucket | Infrastructure — defer |

### Advisor-Specific

| # | Title | Notes |
|---|-------|-------|
| 731 | Advisor: Refactor API in Polylith | Large refactor, assigned to cbeach47 — evaluate scope |
| 734 | Advisor: Reduce hallucinations and circular loops | Tuning work — defer unless blocking demos |
| 735 | Disable prompts for unanswerable follow-up questions | Demo polish — defer |
| 737 | Lock input + show busy state while thinking | UI polish — defer |
| 726 | Advisor not returning proficiency topics | May overlap with #757 |
| 728 | Advisor not returning Remuneration info | Data issue — evaluate |
| 711 | Advisor: Lots of data in response for employment prefs | Tuning — defer |
| 718 | Advisor: Failed to trim messages before summarization | Error handling — evaluate |
| 700 | SPIKE: Advisor fails to recover after LIF-610 | Assigned to cbeach47, resilience — evaluate |
| 691 | Remove over-pruning of fields in Advisor/MCP | Feature — defer |
| 716 | Semantic Search: Fix descriptions of informationSourceId | Data model fix — evaluate |

### Infrastructure

| # | Title | Notes |
|---|-------|-------|
| 675/676 | OpenTelemetry strategy & tracing | Nice-to-have — defer |
| 677 | Draft CI smoke test compose up + health check | CI improvement — defer |
| 738 | Script to validate workflow watch paths | CI improvement — defer |
| 673 | Enable Dependabot | Quick setup — could be a small win if time permits |
| 671 | Canonicalize Docker Compose & clean dev variants | Infrastructure cleanup — defer |
| 682 | Deploying MDR database from Mac fails | Platform-specific — defer |
| 685 | Fix flyway configs for MDR/Dagster OS | May already be resolved |

### Orchestrator / Data

| # | Title | Notes |
|---|-------|-------|
| 730 | Orchestrator: Deeper review of design doc | Docs — could fit in Tier 3 |
| 725 | Bug: Bad Dagster name | Quick fix if still relevant |
| 710 | Orchestrator: Double Dagster runs | May be resolved |
| 704 | Renee's user fails to call the Orchestrator | May be resolved |
| 709 | Update lif-sample.json and lif-sample_clean.json | Data cleanup |
| 745 | Audit source data models for unique names | Assigned to thelmick |
| 712 | LIF API: Identification system error | Evaluate |
| 687 | Investigate: School Assigned Number issue | Evaluate |
| 722 | Investigate and improve Translator performance | Optimization — defer |
| 668 | MDR API import service method not found | May be resolved by portability work |
| 662 | Export/import translations into MDR | May overlap with #771/#772 |

---

## Suggested Sprint Plan

| Timeframe | Focus | Target Issues |
|-----------|-------|---------------|
| **Week 1** (now) | Close done issues, fix critical bugs | Verify/close ~11 issues, start Tier 1 bugs |
| **Weeks 2–4** | Demo stability | Complete Tier 1 (60–80h) |
| **Weeks 5–8** | Portability + tenant isolation POC | Tier 2 portability issues, POC for schema isolation |
| **Weeks 9–12** (March) | Tenant isolation build (if POC validates), stabilize | Integration testing, remaining Tier 2 |
| **April–June** | Docs and cleanup | Tier 3 documentation, close/defer Tier 4 |

---

## Open Questions for Team

1. **Advisor scope:** Several Advisor issues (#726, #728, #734, #735) are open. Are we actively maintaining the Advisor through March, or is it stable enough to leave as-is?
2. **Orchestrator/Dagster:** Issues #710, #704, #725 may already be resolved. Who can verify?
3. **thelmick capacity:** Issues #805, #785, #810, #745 are assigned to thelmick. Is this person still active on the project?
4. **ahungerford capacity:** Issues #773, #768 are assigned. Is this person still available?
5. **Tenant isolation priority:** Does the POC for schema isolation (4–6 hours, see `mdr-tenant-isolation-cognito.md`) fit into the first two weeks alongside bug fixes?
