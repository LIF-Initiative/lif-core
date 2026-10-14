# Test-Driving the MDR Without AWS

Run the Metadata Repository (MDR) on any Docker host, such as a cloud VM, with a single schema and logins you configure yourself. No AWS and no Cognito required (#1316).

This is the MDR-only first stage of [#1290](https://github.com/lif-initiative/lif-core/issues/1290). Adding a full organization (GraphQL, Query Planner, and the rest of the stack) is tracked in #1317. For the whole-stack picture, start at [`deploying-lif-at-your-institution.md`](deploying-lif-at-your-institution.md).

## What you get

| Piece | Default port | Notes |
|---|---|---|
| MDR UI | 5173 | Password sign-in form, because the UI is built without Cognito settings |
| MDR API | 8012 | `/health-check` is public; the rest needs a sign-in token or a service API key |
| MDR Postgres | 5445 | Seeded with the LIF baseline data model on first start |

It runs as a single schema: tenant routing is off by default, so every request uses `public` (`mdr__tenant_routing__enabled` in `components/lif/mdr_utils/config.py`). Cognito is off whenever `MDR__AUTH__COGNITO_USER_POOL_ID` is empty (`components/lif/mdr_auth/core.py`), and the compose file never sets it.

## Prerequisites

- Docker with Compose v2
- `git`
- `python3`, standard library only, to generate password hashes
- For a reachable deployment: a Linux VM with about 2 vCPUs, 2 GB of RAM and 20 GB of disk (see [Sizing](#sizing)), and two DNS names you control

## Sizing

Measured on the MDR slice built from a fresh clone (2026-09-30, Docker Engine 29.7):

| | Memory | Disk |
|---|---|---|
| Running, idle | about 200 MiB in total: API 149, Postgres 39, UI 9 | |
| Running, after 40 parallel list calls and 10 full-schema generations | about 230 MiB: API 153, Postgres 69, UI 9 | |
| Building with `--no-cache` | about 550 MiB above idle at the peak | |
| Images after the build | | about 1.4 GB: API 618 MB, Postgres 671 MB, UI 80 MB, plus the 387 MB Node build image and the build cache |

**2 vCPUs, 2 GB of RAM and 20 GB of disk leaves comfortable headroom.** That is a recommendation from these numbers, not a measured minimum. The build took about 16 seconds on a 10-core machine that already had the base images. On a fresh VM, downloading the base images and dependencies dominates the first build.

## 1. Get the code

```bash
git clone https://github.com/lif-initiative/lif-core.git
cd lif-core
```

## 2. Create the logins

Generate a hash for each person. The script prompts twice and prints the hash:

```bash
python3 scripts/hash-mdr-password.py
```

The output looks like `scrypt:16384:8:1:<salt>:<key>`. It contains no `$`, `,` or `=`, so it pastes into `.env` as-is.

## 3. Write `deployments/advisor-demo-docker/.env`

Compose reads `.env` from the directory it runs in, and the file is gitignored. Every value marked "replace" has a well-known default in the compose file or in MDR's settings, so leaving one unset on a reachable host gives away access.

```bash
# --- Logins (#1316) -------------------------------------------------------
# Comma-separated username=hash pairs from scripts/hash-mdr-password.py.
# When set, these replace the built-in demo personas.
MDR__AUTH__LOCAL_USERS=alice@example.org=scrypt:...,bob@example.org=scrypt:...

# --- Secrets: replace every value ------------------------------------------
# Signs MDR sign-in tokens (compose default: change4).
MDR__AUTH__JWT_SECRET_KEY=replace-with-a-long-random-string
# Service API keys. Anyone holding one gets service-level API access
# (defaults: changeme1, changeme2, changeme3, changeme5, changeme6).
MDR__AUTH__SERVICE_API_KEY__GRAPHQL=replace
MDR__AUTH__SERVICE_API_KEY__SEMANTIC_SEARCH=replace
MDR__AUTH__SERVICE_API_KEY__TRANSLATOR=replace
MDR__AUTH__SERVICE_API_KEY__POST_CONFIRM=replace
MDR__AUTH__SERVICE_API_KEY__LEARNER_DATA_EXPORT=replace
# Postgres password (default: postgres). The three must match.
LIF_MDR__DATABASE__PASSWORD=replace
LIF_MDR__DATABASE_RESTORE__PASSWORD=replace
LIF_MDR__API__DATABASE_PASSWORD=replace

# --- Required by compose even for an MDR-only run ---------------------------
# Compose interpolates the whole file, so these must be set even though the
# services that use them are not started. With MDR__AUTH__LOCAL_USERS set,
# MDR ignores LIF_DEMO_USER_PASSWORD.
LIF_DEMO_USER_PASSWORD=replace
SECRET_KEY=replace

# --- Public URLs: only when not on localhost --------------------------------
# Baked into the UI at build time. Rebuild the UI after changing it.
# The GraphQL services read the same variable as their in-network MDR address.
# That doesn't matter for an MDR-only run, which doesn't start them (see #1317).
LIF_MDR_API_URL=https://mdr-api.example.org
# Browser origins allowed to call the API. The LDE service reads the same variable.
CORS_ALLOW_ORIGINS=https://mdr.example.org
```

Generate random values with something like `python3 -c "import secrets; print(secrets.token_hex(32))"`.

## 4. Start it

```bash
cd deployments/advisor-demo-docker
docker compose up -d --build lif-mdr-app
```

Naming `lif-mdr-app` starts only the MDR slice. Compose follows its dependencies: the API waits for Postgres to start and for the one-shot restore container to load the baseline and migrations, then the UI starts. The restore container shows as `Exited (0)` afterwards, which is expected.

## 5. Check it

```bash
curl -s localhost:8012/health-check
curl -s -X POST localhost:8012/login -H 'content-type: application/json' \
  -d '{"username":"alice@example.org","password":"<password for alice>"}'
```

The sign-in returns an `access_token`. Pass it as `Authorization: Bearer <token>`, for example to `GET /datamodels/`, which should list the seeded data models. Then open the UI on port 5173 and sign in with the same credentials.

A wrong password, or a demo persona once `MDR__AUTH__LOCAL_USERS` is set, gets `401`.

## Running on a reachable host

Serve the MDR over HTTPS from a reverse proxy on the same host, and keep every container port on loopback. These steps use Caddy, which obtains and renews its certificates by itself. Any reverse proxy works the same way.

**1. DNS and firewall.** Point two hostnames at the VM, one for the UI and one for the API: for example `mdr.example.org` and `mdr-api.example.org`. In your provider's firewall (a security group, network firewall rule or equivalent), allow inbound TCP 80 and 443 only. Caddy needs port 80 to obtain its certificates.

**2. Publish the containers on loopback only.** Docker's published ports bypass host firewalls such as `ufw`, so a host rule alone does not hide ports 5173, 8012 and 5445. Save this as `deployments/advisor-demo-docker/docker-compose.override.yml`. Compose loads it automatically, and `!override` replaces each port list instead of adding to it:

```yaml
services:
  lif-mdr-app:
    ports: !override
      - "127.0.0.1:5173:80"
  lif-mdr-api:
    ports: !override
      - "127.0.0.1:8012:8012"
  lif-mdr-database:
    ports: !override
      - "127.0.0.1:5445:5432"
```

**3. Point the build and CORS at the public names**, in `.env`:

```bash
LIF_MDR_API_URL=https://mdr-api.example.org
CORS_ALLOW_ORIGINS=https://mdr.example.org
```

The UI calls whatever `LIF_MDR_API_URL` was at build time. The default is `http://localhost:8012`, which only works in a browser on the same machine. After changing it, rebuild with `docker compose up -d --build lif-mdr-app`. The LDE service reads `CORS_ALLOW_ORIGINS` too.

**4. Install Caddy on the host** ([install guide](https://caddyserver.com/docs/install)), give it this `/etc/caddy/Caddyfile`, and reload it with `sudo systemctl reload caddy`:

```
mdr.example.org {
	reverse_proxy localhost:5173
}

mdr-api.example.org {
	reverse_proxy localhost:8012
}
```

**5. Check it from outside the VM.** `curl -s https://mdr-api.example.org/health-check` should answer, and `https://mdr.example.org` should show the sign-in form. The direct ports should not answer at all: `curl --max-time 5 http://<vm-ip>:8012/health-check` should time out or be refused.

### Rehearsing the HTTPS setup on one machine

You can run the same setup without DNS or a VM: names under `.localhost` resolve to loopback, and Caddy's `local_certs` issues certificates from its own CA instead of Let's Encrypt. This was verified on Docker Desktop for macOS. On Linux, `host.docker.internal` does not reach ports bound to `127.0.0.1`, so run Caddy on the host (or with `--network host`) and proxy to `localhost:5173` and `localhost:8012` instead. The Linux variant has not been verified.

1. In `.env`, set `LIF_MDR_API_URL=https://mdr-api.localhost:8443` and `CORS_ALLOW_ORIGINS=https://mdr.localhost:8443`, then start the slice as in step 4.
2. Save this as `Caddyfile`:

   ```
   {
   	local_certs
   }

   mdr.localhost:8443 {
   	reverse_proxy host.docker.internal:5173
   }

   mdr-api.localhost:8443 {
   	reverse_proxy host.docker.internal:8012
   }
   ```

3. Run Caddy and fetch its root certificate:

   ```bash
   docker run -d --name mdr-caddy -p 8443:8443 -v "$PWD/Caddyfile:/etc/caddy/Caddyfile:ro" caddy:2
   # Caddy creates its CA a moment after it starts, so wait for the file.
   until docker cp mdr-caddy:/data/caddy/pki/authorities/local/root.crt ./caddy-root.crt 2>/dev/null; do sleep 1; done
   curl --cacert caddy-root.crt https://mdr-api.localhost:8443/health-check
   ```

Browsers won't trust that certificate unless you install `caddy-root.crt` as a trusted root, so use `curl --cacert` for the checks or accept the browser warning.

## Data lifetime

The database keeps its data across `docker compose stop`/`start` and repeated `up`s. On each `up` the restore container runs again: it logs "already exists" errors for the baseline objects and leaves existing data unchanged. The database has no named volume, so treat `docker compose down` as a reset back to the baseline.

## Adding or changing a login

Edit `MDR__AUTH__LOCAL_USERS`, then recreate the API so it picks up the new value:

```bash
docker compose up -d lif-mdr-api
```

MDR refuses to start if an entry is malformed, such as a missing `=`, a hash not produced by the script, or the same username listed twice, and the error names the entry. Check `docker compose logs lif-mdr-api`.
