# SF Planner — instructions for Claude Code (sfdev1)

You are the **build session** for SF Planner 2.0. The approved plan is `v2/docs/PLAN.md` — read it first, every new session. The overseer (a separate Claude session in Michael's claude.ai Project) reviews your work from git between phases. Michael is the owner and approver.

## Ground rules

- **2.0 lives in `v2/`.** Do not modify 1.x (`backend/`, `frontend/`, root `Dockerfile`, root `docker-compose.yml`, `data/`) before Phase 5. 1.x is live on docker02 :8042 and docker02 pulls this repo's `main`, so a change there goes live on its next restart.
- **Stack:** Python 3.12, FastAPI, Jinja2, SQLite, vanilla JS (ES modules, no frontend build step, no frameworks).
- **Approved dependencies only:** the existing runtime deps (fastapi, uvicorn, jinja2, python-multipart, openpyxl), pytest (dev only, never in the image), and `@etothepii/satisfactory-file-parser` vendored as a single browser bundle in `v2/static/vendor/` (built once with Node + esbuild on sfdev1; commit the bundle, its version and its MIT licence; Node/esbuild are dev tools, not runtime). **Ask Michael before adding anything else.**
- **Game data must be accurate to Satisfactory 1.1** (build 25782416). Source of truth: `~/sf-inputs/docs/en-US.json` (UTF-16). Never hand-type recipe numbers; generate them. If unsure of a game mechanic, look it up — don't guess.
- **Power per machine:** `P = P_base * (clock/100)^1.321929 * (1 + sloops/slots)^2`; output × `(1 + sloops/slots)`. Constants come from the Docs file (`mPowerConsumptionExponent`, `mProductionBoostPowerConsumptionExponent`, `mProductionShardSlotSize`). Variable-power machines use the mean of `mEstimatedMininumPowerConsumption` / `mEstimatedMaximumPowerConsumption`. Golden test: 1 Constructor @ 250% = 13.43 MW.
- **Never write to 1.x's `data/planner.db`.** The 1.x importer reads a copy.

## Ask Michael first (stop and ask in the session)

New dependencies; deleting any data; changing ports or exposure; anything touching 1.x before Phase 5; a schema decision the plan doesn't cover; anything irreversible.

## Commits

- Small, frequent, each one passes `pytest` and starts cleanly. Push to `origin main` right away (remote alias `github-sf-planner`, deploy key with write access).
- Never squash, rebase published commits, or force-push `main`. History is the rollback mechanism.
- Tag each finished phase: `v2-p1` … `v2-p5` (annotated, pushed).
- Commit messages: imperative summary line, body says what/why.

## Dev loop on sfdev1

- Venv: `~/sf-planner/v2/.venv` (gitignored). Dev server: `uvicorn` on sfdev1 port 8043, data in `v2/data/` (gitignored), seeded from a copy of 1.x's DB.
- Copy of 1.x DB for the importer: a snapshot is at `~/sf-inputs/planner-1x.db`. For a fresh consistent copy: `ssh docker02-deploy seed1x > ~/sf-inputs/planner-1x.db` (read-only sqlite backup of the live 1.x DB).
- Browser checks: Playwright (Python) against the dev server for every UI change.
- Test inputs: `~/sf-inputs/saves/MK1-2i.sav` (current world, 4.2 MB), `~/sf-inputs/saves/M1-8m.sav` (34 MB stress test). Never commit saves.

## Deploying to docker02 (do it as soon as checks pass)

docker02 runs 2.0 as container `sf-planner-v2` on host port **8043** from `/opt/sf-planner/v2/docker-compose.yml` (you create that file in Phase 1; container name must be `sf-planner-v2`, data volume `./data`).

You have one SSH entry point, a forced command — nothing else is possible:

```
ssh docker02-deploy status    # container status + /health on :8043
ssh docker02-deploy backup    # dated copy of v2/data/planner2.db (run before any deploy that adds a migration)
ssh docker02-deploy pull      # git pull --ff-only on docker02
ssh docker02-deploy up        # docker compose up -d --build in v2/
ssh docker02-deploy restart   # docker compose restart in v2/
ssh docker02-deploy logs      # last 200 log lines of sf-planner-v2
ssh docker02-deploy seed1x    # stdout: consistent read-only copy of 1.x's planner.db
```

Order: push → `backup` (if migration) → `pull` → `up` (deps/Dockerfile changed or first time) or `restart` → `status`. After a deploy, `/health` and every 2.0 page must return 200 from `http://192.168.23.86:8043`. If a deploy breaks, revert the commit, push, pull, restart — then report.

## Reporting

After every step, append to `v2/docs/PROGRESS.md`: date/time, what changed, commit hash(es), what was verified, anything open or questionable. Keep it factual. At each phase end, also update the root `README.md` section for 2.0, and note in PROGRESS.md that the phase is ready for overseer review (the overseer updates the wiki).

## Phase order

Follow `v2/docs/PLAN.md` → "Phases". Do not start a phase until the previous one's "done when" criteria are met and recorded in PROGRESS.md.
