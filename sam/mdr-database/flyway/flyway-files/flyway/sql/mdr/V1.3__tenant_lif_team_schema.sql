-- Issue #883 Phase 2 PR 3: Cut over — provision tenant_lif_team schema.
--
-- This is the destination for the internal "lif-team" Cognito group (added
-- to the Cognito stack in this PR) and the default target for API-key
-- service callers once MDR__TENANT_ROUTING__ENABLED is flipped to true.
--
-- The clone copies every public row into tenant_lif_team, so the team's
-- workspace carries the full current demo data model. Public is left
-- intact: the feature flag can be flipped back to false for emergency
-- rollback, at which point traffic resumes hitting public directly. A
-- later cleanup migration may empty public's data tables once we're
-- confident in the cutover — not this PR.
--
-- Idempotent per the CLAUDE.md "MDR Schema Migrations (V1.2+)" convention:
-- safe to re-run after local `docker compose down -v` cycles.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'tenant_lif_team') THEN
        PERFORM public.clone_lif_schema('tenant_lif_team', TRUE);
    END IF;
END
$$;
