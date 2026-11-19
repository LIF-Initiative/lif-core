# Clearing Stale Local Builds

How to clear out locally built LIF images, caches and environments so the next build starts clean, and how to check that a rebuilt image no longer trusts the roots distrusted in #1480 (#1516).

## When you need this

#1510 and #1516 make every image LIF builds distrust four roots:

- **emSign ECC Root CA - G3** and **Comodo AAA Services root**. These are the two roots the [eMudhra incident advisory](https://emudhra.we-have-a-problem.com) says to distrust on Debian. The compromised intermediates chain to G3, and Sectigo's AAA root cross-signs each of them. The advisory lists NSS 3.131.1 and Debian `ca-certificates` 20250419+deb13u1 as fixed.
- **emSign Root CA - C1** and **emSign ECC Root CA - C3**. The advisory doesn't name these. They're on the list because `certifi` 2026.10.23, which follows Mozilla's store, no longer carries them (#1480). Debian's patched `ca-certificates` (20250419+deb13u1, in today's `python:3.13-slim`) has dropped G3 and AAA but still trusts C1 and C3, so the step is what removes them from the system store. **emSign Root CA - G1** is in both and stays trusted.

Background: [Google's announcement](https://blog.google/security/protecting-chrome-and-android-users-from-compromised-emudhra-intermediate-ca-certificates/). Python has two trust stores, and the fix covers both:

| Trust store | Used by | Fixed by |
|---|---|---|
| `certifi` bundle | `requests`, `httpx`, anything using `certifi.where()` | `certifi` 2026.10.23 in the `uv.lock` files. The Dagster+ hybrid agent's image isn't built from a lock file, so its `Dockerfile` pins `certifi==2026.10.23` with `pip` |
| Debian `ca-certificates` | `ssl.create_default_context()`, `urllib`, OpenSSL | A step after the runtime stage's `FROM` in each `Dockerfile`, `Dockerfile2` and Dagster Dockerfile, including the Dagster+ hybrid agent's |

The step deny-lists the four roots in `/etc/ca-certificates.conf`, then fails the build if any of them is still trusted under a name its `sed` doesn't match, so a renamed entry can't pass silently. The base images use floating tags or older Debian releases, which is why the step doesn't rely on today's `ca-certificates` already dropping them: the Dagster+ agent's Debian 12 image (`ca-certificates` 20230311+deb12u1) still trusted all four before the step.

Images LIF doesn't build, such as MongoDB, MariaDB and nginx, aren't covered (#1480).

A rebuild with a warm cache can keep an old layer, an old base image or an old `certifi`. If you built LIF before these fixes, follow the steps below once. They're optional and don't change the repo.

## Clean up and rebuild

Run from the `lif-core` repo root. Two warnings:

- **Step 4 with `-v` deletes local database volumes**, so leave out `-v` if you want to keep local data.
- **Step 5 acts on the whole machine, not just LIF.** `docker builder prune -af` deletes every project's build cache, and removing `python:3.13-slim` affects any other project that uses it. Skip step 5 if you'd rather keep those, and rely on step 6's `--pull --no-cache` instead.

The block runs in a subshell with `set -e`, so it stops at the first failure, for example when `git switch` refuses because of uncommitted changes, instead of rebuilding from the wrong branch.

```bash
(
set -euo pipefail

# 1. Git: get the fix and drop stale worktree records
git fetch origin
git switch main
git pull --ff-only
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
         development/advisor-demo-3orgs/docker-compose.yml \
         projects/lif_mdr_api/docker-compose.yml; do
  if [ -f "$f" ]; then
    # add -v to also drop volumes
    docker compose -f "$f" down --rmi local --remove-orphans \
      || echo "!! $f was not cleared; see the note below the block"
  fi
done
docker image rm dagster-code-location-image 2>/dev/null || true

# 5. Docker: drop the stale base image and the build cache, including uv cache mounts
docker image rm python:3.13-slim 2>/dev/null || true
docker builder prune -af

# 6. Rebuild from fresh bases and recreate containers (repeat with -f for each stack you use)
docker compose -f deployments/advisor-demo-docker/docker-compose.yml build --pull --no-cache
docker compose -f deployments/advisor-demo-docker/docker-compose.yml up -d --force-recreate
)
```

**If step 4 prints `!! ... was not cleared`:** `docker compose down` reads the whole file, so it fails when a variable the file marks required (`${VAR:?...}`) is unset, for example `development/docker-compose.yml` with no `.env`. Its images are then left behind. Run that one `down` again with the variable it names set; any value works for `down`. Then remove its images.

Images built with `projects/*/build-docker.sh` aren't in any compose file. Remove them by tag (`docker image ls`) and rebuild them the same way.

## Verify

Run this against a running stack. For each Python container it prints the emSign and AAA roots in the system store, and the `certifi` version with the same roots in its bundle. After the fix, each list holds only `emSign Root CA - G1`, which Mozilla still trusts.

```bash
for c in $(docker compose -f deployments/advisor-demo-docker/docker-compose.yml ps -q); do
  echo "== $(docker inspect -f '{{.Name}}' "$c")"
  if ! docker exec "$c" sh -c 'command -v python' > /dev/null 2>&1; then
    echo "  (no python in this container, or it isn't running)"
    continue
  fi
  docker exec "$c" python -c '
import ssl
match = lambda s: "emSign" in s or "AAA" in s
system = sorted({dict(x[0] for x in ca["subject"]).get("commonName", "") for ca in ssl.create_default_context().get_ca_certs() if match(str(ca["subject"]))})
print("system store:", system)
try:
    import certifi
    labels = [l.split(":", 1)[1].strip().strip(chr(34)) for l in open(certifi.where()) if l.startswith("# Label") and match(l)]
    print("certifi", certifi.__version__, labels)
except ImportError:
    print("certifi not installed")
' || echo "  !! the check failed; the error is above"
done
```

A container without Python, or one that isn't running, prints a note and is skipped. If the check itself fails, its error is shown rather than hidden.
