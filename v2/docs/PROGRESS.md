# SF Planner 2.0 — Progress log

Newest entries at the bottom. One entry per step: date/time (MT), what changed, commits, what was verified, open questions.

## 2026-11-01 18:35 — setup (overseer)

- sfdev1 (VM 124) built and baselined; Claude Code installed; Michael logged in.
- Repo cloned to `~/sf-planner` (deploy key, write). docker02 pulls with a read-only deploy key.
- Deploy path: `ssh docker02-deploy <pull|backup|up|restart|status|logs|seed1x>` (forced command `/usr/local/bin/sf-deploy` on docker02, from 192.168.23.84 only).
- Inputs: `~/sf-inputs/docs/en-US.json` (build 25782416), `~/sf-inputs/saves/{MK1-2i,M1-8m}.sav`, `~/sf-inputs/planner-1x.db` (1.x snapshot: 4 factories, 4 factory targets, 3 power plants, scratchpad empty).
- Node 22 + npm installed (dev only, for bundling the save parser).
- Added `CLAUDE.md`, `v2/docs/PLAN.md`, this file.
- Next: Phase 1.

## 2026-11-01 — Phase 1, step 1: game data + power math

- Added `v2/tools/build_gamedata.py` → `v2/core/gamedata.json` (168 items, 291 machine recipes of which 110 alternate, 11 production buildings, 6 extractors, 4 generators). Fluid amounts converted mL → m³. Generated, never hand-typed.
- Added `v2/core/power.py` (1.1 power/output maths) and `v2/core/gamedata.py` loader.
- pytest: 13 pass incl. golden Constructor @250% = 13.43 MW, recipe count vs Docs file (291).
- Venv `v2/.venv` is Python **3.14** (sfdev1 has no 3.12); the container will run 3.12. Code is kept 3.12-compatible; no 3.13+ features. No httpx installed (not approved), so tests call functions directly rather than via TestClient.
- **Open / questionable:** the Docs file gives Smelter and Packager `mProductionShardSlotSize` = 0 (1.x had Smelter 1, Packager 2). Following the Docs as instructed, so those two can't be sloop'd in 2.0. Please confirm this matches the game.
- Added `.venv/`, `node_modules/`, `.pytest_cache/` to `.gitignore` (root, not 1.x code).

## 2026-11-01 — Phase 1, steps 2–4: schema, importer, app, container (deployed)

- Commits: `a7195d6` (skeleton, migration 001, importer, container config).
- Schema 001 follows PLAN.md. **Schema decision (approved by Michael):** `factory_recipe` is the per-factory/per-item override table: `recipe`, `clock_pct`, `sloops` (integer count 0..slots of the recipe's machine; 1.x `slooped=1` → full slot count). Recorded in the PLAN.md data model table.
- Migration runner (`app/db.py`): numbered SQL, `schema_version`, dated `.pre-migration-<ts>` backup before applying migrations to an existing DB.
- 1.x importer (`tools/import_1x.py`): reads a read-only copy, idempotent via `source_ref`. Result: world "Main", 4 factories + archived "1.x plan (archived)" (carries the old scratchpad's clock overrides; 0 targets), 3 power plants, all recipe/clock/sloop overrides. Container: on first start (no world) copies `planner.db` via the sqlite backup API from a **read-only** mount of `/opt/sf-planner/data` (`../data:/app/1x-data:ro`) and imports; 1.x DB never written.
- Pages: `/` World, `/factories`, `/power` (read-only), `/health`.
- Deployed: `pull` → `up` (first time) → `status` healthy. From the LAN, `/health`, `/`, `/factories`, `/power`, `/static/app.css` all 200 on http://192.168.23.86:8043; docker02 shows 5 factory cards and 3 power plants; 1.x on :8042 still 200. No backup run (no prior v2 DB).
- pytest: 16 pass (power golden, gamedata integrity + recipe count 291 vs Docs, migrations, importer incl. idempotency and sloop mapping).
- Open: (1) Smelter/Packager 0 sloop slots per Docs (see step 1). (2) Dev runs Python 3.14, image is 3.12 — the container ran the same code fine. (3) The importer maps a sloop override's slot count from the override recipe, else the first non-alternate recipe producing the item. (4) Compose mounts code read-write from the repo checkout, so `restart` picks up code changes (same pattern as 1.x). (5) Not done: Playwright browser check — no UI beyond static lists yet; I checked HTTP responses and rendered HTML only.

**Phase 1 done-when:** pytest passes incl. golden ✔; recipe count matches Docs ✔; all 1.x factories and power plants appear in 2.0 ✔. Phase 1 is ready for overseer review.

## 2026-11-01 — Phase 1 fix: sloop slots derived, 3.12 test step

- Per Michael: Smelter has 1 Somersloop slot in game; Packager 0 is right. The Docs' `mProductionShardSlotSize` is unreliable, so `build_gamedata.py` now derives slots = `round(1 / mProductionShardBoostMultiplier)` if `mCanChangeProductionBoost` is True, else 0. Regenerated `gamedata.json`: the only change is Smelter 0 → 1 (all others already matched: Constructor 1; Assembler/Foundry/Refinery/Converter 2; Manufacturer/Blender/Particle Accelerator/Quantum Encoder 4; Packager 0).
- Added `test_pinned_sloop_slots` (pins all 11).
- Added `v2/tools/test312.sh`: runs pytest in `python:3.12-slim` (repo read-only, `~/sf-inputs` mounted so nothing is skipped). **Run before every deploy.** Result now: 17 passed on 3.12.16 (also 17 on 3.14 locally).
- 1.x re-import: a fresh import into a clean DB gives identical results to before (183 override rows; only sloop override is Ficsite Trigon = 1, a Constructor item). No 1.x item with a sloop override is a Smelter item, so no stored values change. The importer is idempotent, so re-running it on docker02's existing DB is a no-op by design; I did not delete docker02 data.
- Deployed via pull + restart; see verification below.
