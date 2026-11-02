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

## 2026-11-01 — Phase 2, step 1: solver + 1.x parity

- Added `core/recipes.py` (planner-recipe filter, default recipe — same priority rules as 1.x, ported to Docs class data), `core/solver.py` (pure; one line per chosen recipe, byproduct credits, shared recipes, loops via Gauss–Seidel fixed point, sloops as integer count, even clock distribution, power from `core/power.py`), `tools/parity_1x.py` (runs 1.x's `backend/solver.py` read-only against the 1.x DB copy and diffs per item), tests (`test_solver.py`, `test_parity.py`).
- Importer fix found by parity: 1.x merges the active plan's clock overrides under every factory's own; the importer now does the same (factory value wins). Existing deployed DB is backfilled once at startup (fill-only, never overwrites; marker `PRAGMA user_version=1`).
- **Parity result (all 4 imported 1.x factories):** `docs/PARITY-1x-stock.md` / `docs/PARITY-1x-tight.md`.
  - vs stock 1.x: Heavy Modular Frames identical. The three fuel-rod factories differ only in the Rubber/Plastic/Heavy Oil Residue/Fuel loop (+ resulting Crude Oil and Water raws), by ≤0.3% (e.g. Rubber 979.85 vs 980.00/min, Plutonium Crude Oil 537.3 vs 538.2). **Cause:** 1.x stops iterating at 0.01% total change and 50 iterations, so its loop answer is under-converged; 2.0 solves the loop exactly (balances to 1e-11).
  - vs 1.x with only its tolerance tightened (same code, read in memory): **all four factories identical** — every item rate, machine count, clock % and raw total. `test_parity_with_1x_solver_at_tight_tolerance` pins this.
  - Power differs as expected (linear in 1.x, 1.1 formula in 2.0): Plutonium 67 188 → 63 557 MW, Ficsonium 130 607 → 114 688, Uranium 26 326 → 27 500, HMF 7 640 → 9 969.
  - 2.0 additionally reports byproduct **surplus** (e.g. Polymer Resin 359/min in Plutonium) which 1.x ignores.
- pytest 25 pass on 3.14 and in the 3.12 image (`tools/test312.sh` now copies `backend/` next to the app so parity runs).

### Decisions

- Solver keeps one line per *recipe* (not per item): a recipe chosen for two items (e.g. both outputs of Heavy Oil Residue) is one set of machines; 1.x double-counted that case. Not present in current data, so parity unaffected.
- Loop/byproduct solve by Gauss–Seidel to 1e-11, not a matrix inverse — the balance is piecewise linear (credits floor at 0); no solver library needed (plan).
- Parity compares against 1.x with tightened tolerance as the pass criterion and lists the stock-1.x deltas with their cause — comparing to an under-converged answer would pin a 1.x defect.
- Plan-level 1.x clock overrides merged into every factory on import (matches 1.x's factory view); backfill is fill-only and one-shot.
- Raw = raw resources plus anything no planner recipe makes (leaves, slugs, alien protein, power shards) — covers 1.x's TREAT_AS_RAW without a hand-typed list.

### Phase 2, step 1 deploy note

- Deployed `4cc0c88` via pull + restart; `/health`, `/`, `/factories`, `/power` 200. The startup backfill ran once on docker02 (`backfilled: 56`).
- **Open: `ssh docker02-deploy backup` failed ("mkdir: Permission denied")** and my deploy chain did not stop on it (pipe to `tail`), so that restart ran without a dated backup. Impact is nil here (the DB held only the re-creatable 1.x import and the backfill is fill-only; 1.x remains the source), but the backup command needs fixing on docker02 (the forced-command user cannot create the backup directory) before users edit data in 2.0. I will check the exit status of `backup` from now on and stop deploying migrations/data changes if it fails.

BLOCKED: `docker02-deploy backup` fails with "mkdir: Permission denied" — needs an overseer/Michael fix on docker02 (permissions on the backup dir used by /usr/local/bin/sf-deploy). Not blocking code work; the app also writes its own `planner2.pre-migration-*.db` copies before schema migrations. Phase 2 UI will start letting users edit data, so please fix before the Phase 2 tag. Recommendation: create the dir owned by the deploy user, or point backups into `/opt/sf-planner/v2/data/backups/`.

## 2026-11-01 — Phase 2, step 2: factory page, recipe picker, exports

- `app/factory_service.py` (load → solve → present, recipe comparison, JSON/Excel export), `app/factory_routes.py` (create factory; add/update/remove outputs; set recipe/clock/Somersloops per line with validation: clock 1–250 %, sloops 0..slots of that recipe's machine, recipe must make the item; archived = read-only), templates `factory.html` (header strip: power, Somersloops used, machines, raw inputs, outputs; outputs editor; raw inputs + byproduct surplus; lines grouped by stage raw→final with inline clock/sloop forms; "Compare recipes" per line showing machine, machines needed, power @100 %, inputs/min and byproducts), `/factories` list now shows solved power/machines per factory with a "New factory" form, exports `/api/factory/{id}/export.xlsx|json` and `/api/factory/{id}/solve`.
- Browser check (Playwright, real Chromium, `tests/browser_check.py`) at 1440 px and 1024 px: create factory → add Iron Plate 60/min → raw Iron Ore 90.00/min shown → clock override → recipe picker opens → ≥40 px touch target → exports 200 → no console errors. It caught two real bugs, both fixed: (1) Jinja `l.items[0]` resolved to `dict.items()` so the override form posted a blank item (now `l["items"][0]`); (2) page-level horizontal overflow at 1024 px (tables now scroll inside their cards).
- pytest 30 pass on 3.14 and in the 3.12 image. Every imported 1.x factory solves with no warnings (`test_every_imported_factory_solves`).
- Deploy: `backup` still fails (see BLOCKED above); this step has no migration, so deployed via pull + restart.

### Decisions

- Playwright: the distro `python3-playwright` is broken (no driver). Installed the official package + Chromium into a separate dev-only venv `~/pw-venv` (outside the repo, never in the image) and unpacked 6 missing shared libs (atk, atspi, asound, xdamage, xres) with `apt-get download` + `dpkg -x` into `~/pw-libs` (no sudo, no system change); run with `LD_LIBRARY_PATH` pointing there. Dev tooling only — CLAUDE.md names Playwright as the browser-check tool.
- Edits are plain HTML forms with POST→redirect (no JS) — simplest thing that works at desktop and tablet, no build step; JS comes where it earns its place (Ctrl+K, import worker).
- Override form applies clock + sloops together; picking a recipe from the comparison keeps the clock but clears sloops (slot counts differ per machine).
- Recipe comparison is per-step at 100 % clock and ignores sub-ingredient chains (deeper comparison can use the solver later) — keeps the picker instant.
- Factories are not deletable in the UI yet (deleting data is a major-decision area); archived factories are read-only.

## 2026-11-01 — Phase 2 complete (`v2-p2`)

**Done-when:** every imported 1.x factory solves with the same rates as 1.x; only power differs; differences listed — ✔ (see "Phase 2, step 1" for the full list and causes; `docs/PARITY-1x-stock.md`, `docs/PARITY-1x-tight.md`). Deployed at `8e42ce3`; all 2.0 pages and exports 200 on :8043. Root README updated. Ready for overseer review.

Still open: `docker02-deploy backup` fails (BLOCKED entry above); not part of Phase 2's done-when, so the tag proceeds, but it must be fixed before Phase 3 adds migrations to the live DB. Phase 3 migrations will be deployed only after a successful `backup`; until then Phase 3 work continues on sfdev1 and is pushed but not deployed if it needs a migration.
