# SF Planner 2.0 — run, deploy, restore

## Run locally (dev, sfdev1)

```
cd ~/sf-planner/v2
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
SFP_1X_DB=~/sf-inputs/planner-1x.db .venv/bin/uvicorn app.main:app --port 8043   # data in v2/data/ (gitignored)
```

First start creates `v2/data/planner2.db` (numbered migrations in `v2/migrations/`, a dated
`planner2.pre-migration-*.db` copy is taken before any later migration) and, if `SFP_1X_DB` points at a
copy of 1.x's `planner.db`, imports it once (read-only; never writes to 1.x). Fresh copy of the live 1.x DB:
`ssh docker02-deploy seed1x > ~/sf-inputs/planner-1x.db`.

Checks: `.venv/bin/pytest` (fast), `v2/tools/test312.sh` (pytest in the python:3.12 image — run before every
deploy), browser checks `~/pw-venv/bin/python tests/browser_check*.py` against a dev server (needs
`LD_LIBRARY_PATH` from `~/pw-libs`, see PROGRESS.md Phase 2 decisions). Rebuild the vendored save parser
(dev only): `cd v2/tools/vendor && npm ci && npm run build`. Regenerate game data after a game update:
`v2/.venv/bin/python v2/tools/build_gamedata.py` and review the diff.

## Deploy to docker02 (container `sf-planner-v2`, host port 8042 since the cutover)

```
ssh docker02-deploy backup     # check it printed a file name and exit status 0 — stop if not
ssh docker02-deploy pull       # git pull --ff-only
ssh docker02-deploy up         # rebuild image (deps/Dockerfile changed, or first time)
ssh docker02-deploy restart    # code/templates/static only (they are bind-mounted)
ssh docker02-deploy status     # container health + /health
ssh docker02-deploy logs
```

Order: push → `backup` → `pull` → `up` or `restart` → `status` → check `/health` and every page on
https://sfplanner.kenningfamily.org (nothing should answer on :8043 any more). `ssh docker02-deploy status` probes the container on docker02 (127.0.0.1:8042); from elsewhere use https://sfplanner.kenningfamily.org/health. `/health` reports `version`, `tag` and `state` (from `v2/app/version.py`).
If a deploy breaks: `git revert` the commit, push, `pull`, `restart`, then report. History is the rollback;
never force-push `main`.

## Back up and restore the 2.0 database

- Backups: `ssh docker02-deploy backup` writes a consistent, integrity-checked copy of `planner2.db` to
  `v2/data/backups/` on docker02 (`planner2-YYYYMMDD-HHMMSS.db`). Startup migrations also leave
  `planner2.pre-migration-*.db` beside the DB.
- Restore (needs a shell on docker02 — the forced-command key has no restore verb; ask the overseer):
  stop the container (`docker compose stop` in `/opt/sf-planner/v2`), copy the chosen backup over
  `/opt/sf-planner/v2/data/planner2.db`, remove any `planner2.db-wal`/`-shm`, start it, then check `/health`.
- Start from scratch: stop, move `planner2.db` aside, start — it re-imports 1.x from the read-only mount of
  1.x's data directory and re-runs migrations. Save-imported factories are not re-created that way
  (re-import the save on the Import page).

## 1.x and getting it back

Cutover done (2026-11-01): 2.0 serves :8042. 1.x was stopped and its container removed (image kept); its code
is under `legacy/` and annotated tag `v1-final` (commit `99716bd`, the last 1.x commit) marks the exact
version that was live. 1.x's database is the untouched `data/planner.db` at the repo root (plus the overseer's
copy `data/planner-v1-final-20261101.db`); 2.0 mounts that directory read-only for its first-start import.

To bring 1.x back (needs a docker02 shell — ask the overseer; nothing here is automatic):
1. Stop 2.0: `cd /opt/sf-planner/v2 && docker compose stop` (frees :8042).
2. Start 1.x from `legacy/`: `cd /opt/sf-planner/legacy && docker compose up -d --build`
   (container `ficsit-planner`, port 8042, data from `../data`). Or from the tag:
   `git checkout v1-final` and use the original root layout.
3. Check `https://sfplanner.kenningfamily.org/health`. 1.x data is whatever `data/planner.db` holds (2.0 never writes it).
4. To return to 2.0: stop 1.x, `docker compose up -d` in `v2/`.

## Access, DNS and TLS (2026-11-02)

- URL: **https://sfplanner.kenningfamily.org** (LAN only). AD A record `sfplanner.kenningfamily.org -> 192.168.23.86` (docker02).
- docker02 host nginx: `/etc/nginx/sites-available/sfplanner` — :80 redirects to :443; :443 terminates TLS (HSTS) and proxies to `127.0.0.1:8042`. `client_max_body_size 32m` for save imports.
- The container publishes **only on 127.0.0.1:8042** (`v2/docker-compose.yml`), so the app is not reachable on a raw port from the LAN.
- Certificate: Let's Encrypt via `certbot certonly --dns-cloudflare` (credentials `/etc/letsencrypt/cloudflare.ini`, same Cloudflare token as Parts Hunter, 1Password `Automation / mcp-cloudflare-token`). `certbot.timer` renews; `/etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh` reloads nginx.
- CSRF guard compares the browser Origin with the Host header; nginx passes `Host` through, so same-site posts via the hostname work.

