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
