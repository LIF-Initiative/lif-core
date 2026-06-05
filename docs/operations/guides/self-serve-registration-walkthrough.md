# Self-Serve Registration Walkthrough

End-to-end walkthrough of the self-registration → workspace selection → invite flow shipped under issue **#884**. Use this to validate the feature on `dev` or `demo`, or to onboard a tester.

For the architectural backstory (Cognito self-serve stack, post-confirmation Lambda, schema-per-tenant), see [`docs/design/cross-cutting/self-serve-tenant-auth.md`](../../design/cross-cutting/self-serve-tenant-auth.md).

## Environments

| Environment | Frontend URL | API URL |
|---|---|---|
| dev | https://mdr.dev.lif.unicon.net | https://mdr-api.dev.lif.unicon.net |
| demo | https://mdr.demo.lif.unicon.net | https://mdr-api.demo.lif.unicon.net |

Pick a fresh email address per tester — Cognito won't let two users share an email, and registration leaves a persistent user pool record.

## Tester walkthrough

### 1. Register

1. Go to the frontend URL.
2. Click **Sign In / Register** on the landing page.
3. Cognito's hosted UI loads. Click **Sign up**.
4. Fill in:
   - **Email** (will receive a 6-digit confirmation code)
   - **Password** (Cognito enforces complexity rules)
   - **Organization** (free text — your school / employer)
   - **Role** (free text — your title or function)
   - **Reason** (free text — why you're evaluating LIF)
5. Submit. Cognito sends a confirmation code by email.
6. Enter the code on the next screen.

Behind the scenes: Cognito fires its post-confirmation Lambda, which calls the MDR's `POST /tenants/provision`. That clones the `public` schema into a new `tenant_<your_group>` schema in Postgres. **This is idempotent and async** — if you reach step 7 below before it finishes (rare; sub-second in practice), retry the page.

### 2. First sign-in → workspace landing

7. After confirmation, you're redirected back through the SPA. Auth callback completes, then you land on **`/workspaces`**.
8. Because you have exactly one workspace (the one just provisioned for you), the page auto-selects it and forwards you to **`/explore`**. You should not need to click anything.
9. If something fails — wrong cookie origin, race with provisioning, etc. — the auto-forward stops and you'll see the picker with an error callout. Refresh the page.

### 3. Generate an invite link

10. Click **Workspaces** in the top nav (or **Switch workspace** in the user dropdown). You're back at `/workspaces`.
11. Click **Invite** on your workspace card. A dialog opens: *"Invite someone to '\<your group\>'"*.
12. Click **Generate invite link**. The dialog shows:
    - A URL of the form `https://mdr.dev.lif.unicon.net/invite/accept?token=…`
    - An expiry timestamp ("Expires \<7 days from now\>")
    - A copy-to-clipboard button
13. Copy the URL. Send it to a second tester (or paste it into a different browser profile for solo testing).

### 4. Accept an invite (second tester)

The recipient needs their own Cognito account first. They can:
- Register fresh (step 1 above), then visit the invite URL while signed in, **or**
- Sign in to an existing account, then visit the invite URL.

14. Visit the invite URL. The page is `/invite/accept` and shows **Accept invite**.
15. If you're not signed in, the AuthGuard bounces you through Cognito login first; you'll land back on the invite page after sign-in (search params preserved).
16. Click **Accept invite**.
17. Success state: **"You're in."** with a button **Sign in again to refresh**.
18. Click that button. You'll be logged out and bounced back through Cognito's login. After sign-in, you'll see *both* workspaces at `/workspaces` — your original (if any) and the invited one.

**Why the re-sign-in is required:** the Cognito JWT was issued before the new group was added; it doesn't reflect the new membership until refreshed. Forcing a re-login is the cheapest way to get a fresh ID token with the updated `cognito:groups` claim.

### 5. Switch workspaces

19. On `/workspaces`, click **Open** on a different workspace card. The page navigates to `/explore`, but you're now operating against the other tenant's data.
20. The selection is stored in an HMAC-signed cookie (`lif_workspace`, `SameSite=Lax`). It survives browser restarts until expiry.

### Edge cases to spot-check

| Scenario | Expected behavior |
|---|---|
| Visit `/invite/accept` with no `?token=` | **"Missing invite token"** card |
| Visit an expired invite link (> 7 days) | **"This invite has expired"** card (HTTP 410 under the hood) |
| Visit a tampered invite link (bad signature) | **"Invite link is invalid"** card |
| Click **Open** on workspace A, then quickly **Open** workspace B | Both buttons disabled while either select is in flight; first wins, second is a no-op |
| Network failure during accept | **"Something went wrong"** card with **Try again** button |
| Legacy username/password mode (Cognito disabled) | `/invite/accept` shows **"Invites require Cognito sign-in"** card before any backend call |

## Admin / operator notes

### Monitor a registration

Cognito console → **User pools** → `\<env\>-lif-mdr-selfserve` → **Users**. Newly confirmed users show up with status `CONFIRMED` and a `custom:organization` / `custom:role` / `custom:reason` attribute set.

Group membership for a user: **Users** → click the user → **Group memberships**. The post-confirmation Lambda adds them to a group named after their sub.

### Export the registration list

For outreach (who has signed up, what they wrote in `reason`, etc.):

```bash
# Dry-run / preview (read-only, no --apply needed)
AWS_PROFILE=lif uv run scripts/export_cognito_registrations.py dev

# Write to a file
AWS_PROFILE=lif uv run scripts/export_cognito_registrations.py dev --output dev-registrations.csv

# JSON instead of CSV
AWS_PROFILE=lif uv run scripts/export_cognito_registrations.py dev --format json
```

IAM permissions required: `cognito-idp:ListUsers`, `cognito-idp:AdminListGroupsForUser`, `cloudformation:DescribeStacks`. The script reads the UserPoolId from the `<env>-lif-mdr-cognito` stack outputs.

### Verify a tenant schema was provisioned

The post-confirmation Lambda's job is to make `tenant_<sanitized_group>` exist in the MDR Postgres database. To check:

```bash
# Connect to the MDR DB via the bastion / however you normally reach it
psql "$MDR_DB_URL" -c "\dn tenant_*"
```

You should see one `tenant_<group>` schema per confirmed user (plus `tenant_lif_team` as the default service schema).

### When something goes wrong

| Symptom | Likely cause | Where to look |
|---|---|---|
| User confirms email but lands on **"No workspaces yet"** | Post-confirmation Lambda failed | CloudWatch Logs → `/aws/lambda/<env>-lif-mdr-cognito-PostConfirmationLambda-*` |
| Invite link 400s with "Token signature invalid" (or workspace cookie silently ignored) | The shared HMAC secret rotated between issue and accept | Check `/<env>/mdr-api/MdrAuthJwtSecretKey` SSM parameter — this single key signs HS256 JWTs *and* HMACs the workspace cookie *and* HMACs invite tokens, so rotating it invalidates all three simultaneously |
| Invite link 400s with `cognito_sub` error | Frontend has Cognito disabled but backend has it enabled (or vice-versa) | `VITE_COGNITO_DOMAIN` / `VITE_COGNITO_CLIENT_ID` in the frontend build vs. backend `cognito_auth__*` settings |
| `/tenants/select` returns 200 but `/explore` still shows the wrong data | Workspace cookie not being sent | Check axios `withCredentials: true` (PR #934) and CORS `allow_credentials=true` on the backend; both required for cross-origin |
| Two registrations from the same email | They aren't; Cognito rejects duplicate emails. The second registrant is silently re-using the first account. | Cognito console → user pool → look at sign-in counts on the existing user |

### Reset / clean up test users

In dev or demo, to clean out test registrants between demo runs:

1. **Cognito side:** User pool → select user → **Actions** → **Delete user**. This frees the email for re-use.
2. **Database side:** the orphaned `tenant_<group>` schema stays. To drop it:
   ```sql
   DROP SCHEMA tenant_<sanitized_group> CASCADE;
   ```
   Use the [#931 workspace-reset endpoint](https://github.com/LIF-Initiative/lif-core/pull/931) if you want a programmatic path; the SQL above is the manual equivalent.

There is currently **no UI** to delete a workspace — by design for v1. Operators handle it.

## Out of scope (known v1 limitations)

These are deliberate cuts for the 2026-05-27 demo. Flagged here so testers don't report them as bugs:

- No header indicator of *which* workspace is currently selected (cookie is HttpOnly; surfacing the value needs localStorage / a context wired in)
- No reset-workspace button in the UI (backend [#931](https://github.com/LIF-Initiative/lif-core/pull/931) exists; UI wiring deferred)
- Invite tokens are **reusable** until expiry (no single-use enforcement; would need a server-side store)
- Invites only work for users with an existing Cognito account; the invite flow doesn't compose with the sign-up flow yet (sign up first, *then* click the invite)

## Related docs

- [`docs/design/cross-cutting/self-serve-tenant-auth.md`](../../design/cross-cutting/self-serve-tenant-auth.md) — architectural narrative (Cognito → Lambda → schema-per-tenant → cookies → invites)
- [`docs/proposals/mdr-self-serve-registration.md`](../../proposals/mdr-self-serve-registration.md) — the broader self-serve roadmap proposal
- [`docs/operations/guides/demo-environment-update.md`](demo-environment-update.md) — how to promote dev → demo (use this *before* a tester runs through the above on `demo`)
