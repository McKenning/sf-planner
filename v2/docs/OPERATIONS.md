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

## Deploy to docker02 (container `sf-planner-v2`, host port 8043)

```
ssh docker02-deploy backup     # check it printed a file name and exit status 0 — stop if not
ssh docker02-deploy pull       # git pull --ff-only
ssh docker02-deploy up         # rebuild image (deps/Dockerfile changed, or first time)
ssh docker02-deploy restart    # code/templates/static only (they are bind-mounted)
ssh docker02-deploy status     # container health + /health
ssh docker02-deploy logs
```

Order: push → `backup` → `pull` → `up` or `restart` → `status` → check `/health` and every page on
http://192.168.23.86:8043. `/health` reports `version`, `tag` and `state` (from `v2/app/version.py`).
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

- Before cutover 1.x (`ficsit-planner`, :8042) is untouched: `backend/`, `frontend/`, root `Dockerfile`,
  root `docker-compose.yml` and its `data/planner.db` are unchanged, and 2.0 only mounts that data directory
  read-only.
- The cutover is not done yet (needs Michael's approval; the overseer stops 1.x on docker02 and then asks for
  2.0 to move to :8042). It will create the annotated tag `v1-final` at the exact commit that is live now,
  move 1.x under `legacy/`, and keep `data/planner.db` on disk unchanged.
- After cutover, to bring 1.x back: on docker02 stop the 2.0 container, `git checkout v1-final` (or
  `git checkout v1-final -- backend frontend Dockerfile docker-compose.yml`), `docker compose up -d --build`
  in the repo root (container `ficsit-planner`, port 8042), and check `http://192.168.23.86:8042/health`.
  Its database is the untouched `data/planner.db`.
