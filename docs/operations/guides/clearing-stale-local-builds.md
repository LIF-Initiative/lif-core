# Clearing Stale Local Builds

How to clear out locally built LIF images, caches and environments so the next build starts clean, and how to check that a rebuilt image no longer trusts the emSign roots removed in #1480 (#1516).

## When you need this

#1510 and #1516 make every LIF image distrust three eMudhra emSign roots that Mozilla dropped in NSS 3.131.1: **emSign Root CA - C1**, **emSign ECC Root CA - C3** and **emSign ECC Root CA - G3**. Python has two trust stores, and the fix covers both:

| Trust store | Used by | Fixed by |
|---|---|---|
| `certifi` bundle | `requests`, `httpx`, anything using `certifi.where()` | `certifi` 2026.10.23 in the `uv.lock` files |
| Debian `ca-certificates` in `python:3.13-slim` | `ssl.create_default_context()`, `urllib`, OpenSSL | A step after the runtime stage's `FROM` in each `Dockerfile`, `Dockerfile2` and Dagster Dockerfile |

A rebuild with a warm cache can keep an old layer, an old base image or an old `certifi`. If you built LIF before these fixes, follow the steps below once. They're optional and don't change the repo.

## Clean up and rebuild

Run from the `lif-core` repo root. **Step 4 with `-v` deletes local database volumes**, so leave out `-v` if you want to keep local data.

```bash
# 1. Git: get the fix and drop stale worktree records
git fetch origin && git switch main && git pull --ff-only
git worktree prune -v

# 2. Python: rebuild the local virtualenv from the lock, discarding any cached certifi
rm -rf .venv
uv cache clean certifi
uv sync --locked

# 3. Build outputs: remove wheels and exported requirements left by build.sh
rm -rf projects/*/dist projects/*/requirements.txt

# 4. Docker: stop each LIF stack and remove the images it built
for f in deployments/advisor-demo-docker/docker-compose.yml \
         development/docker-compose.yml \
         development/docker_compose_dagster.yaml \
         development/advisor-demo-1org/docker-compose.yml \
         development/advisor-demo-3orgs/docker-compose.yml; do
  [ -f "$f" ] && docker compose -f "$f" down --rmi local --remove-orphans   # add -v to also drop volumes
done
docker image rm dagster-code-location-image 2>/dev/null || true

# 5. Docker: drop the stale base image and the build cache, including uv cache mounts
docker image rm python:3.13-slim 2>/dev/null || true
docker builder prune -af

# 6. Rebuild from fresh bases and recreate containers (repeat with -f for each stack you use)
docker compose -f deployments/advisor-demo-docker/docker-compose.yml build --pull --no-cache
docker compose -f deployments/advisor-demo-docker/docker-compose.yml up -d --force-recreate
```

Images built with `projects/*/build-docker.sh` aren't in any compose file. Remove them by tag (`docker image ls`) and rebuild them the same way.

## Verify

Run this against a running stack. For each Python container it prints the emSign roots in the system store, and the `certifi` version with the emSign roots in its bundle. After the fix, each list holds only `emSign Root CA - G1`, which Mozilla still trusts.

```bash
for c in $(docker compose -f deployments/advisor-demo-docker/docker-compose.yml ps -q); do
  echo "== $(docker inspect -f '{{.Name}}' "$c")"
  docker exec "$c" python -c '
import ssl
system = sorted({dict(x[0] for x in ca["subject"]).get("commonName", "") for ca in ssl.create_default_context().get_ca_certs() if "emSign" in str(ca["subject"])})
print("system store:", system)
try:
    import certifi
    labels = [l.split(":", 1)[1].strip().strip(chr(34)) for l in open(certifi.where()) if l.startswith("# Label") and "emSign" in l]
    print("certifi", certifi.__version__, labels)
except ImportError:
    print("certifi not installed")
' 2>/dev/null || echo "  (no python in this container)"
done
```

Containers without Python print the last line.
