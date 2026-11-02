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

BLOCKED (RESOLVED 2026-11-01 ~20:49 by overseer — wrapper bug, data dir was root-owned; backup now writes a consistent sqlite copy with integrity_check to v2/data/backups/): `docker02-deploy backup` fails with "mkdir: Permission denied" — needs an overseer/Michael fix on docker02 (permissions on the backup dir used by /usr/local/bin/sf-deploy). Not blocking code work; the app also writes its own `planner2.pre-migration-*.db` copies before schema migrations. Phase 2 UI will start letting users edit data, so please fix before the Phase 2 tag. Recommendation: create the dir owned by the deploy user, or point backups into `/opt/sf-planner/v2/data/backups/`.

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

## 2026-11-01 — Phase 3: World (complete, `v2-p3`; **deploy held**, see below)

- **Schema 002** (`migrations/002_world.sql`): `world_resource` (node counts per resource, extractor, clock), `factory_input` (items a factory takes from elsewhere = split cut points), `flow.auto`. Importer now also brings in 1.x's resource node counts (insert-only; startup marker `user_version=2`).
- **Core (pure, tested):** `core/budget.py` (per-node rate = extractor data × purity × clock; Iron/Copper etc. match 1.x's budget exactly), `core/ledger.py` (generator MW/fuel/water/waste from Docs energy values — matches the game and 1.x's table, e.g. nuclear 100×250 % = 625 000 MW, 50 rods/min, 2 500 waste/min; item ledger supply vs demand with deficits first; raw budget with over-budget first; flow allocation), solver `external=` (items taken from other factories are treated like raw inputs).
- **App:** `app/world_service.py` (overview, goal tree, `assign` = split, `rebuild_auto_flows`), `app/world_routes.py`, pages: **World** home (strip: power used/generated, factories, flows, warnings; warnings list; resource budget bars with OVER BUDGET word+colour; ledger with Link-a-deficit action; factory cards), **Goals** (world goals + power goal, raw totals vs budget, production tree with recipe comparison at world level, assign each item to a new/existing factory "with everything below" or alone), **Flows** (auto + manual, transport belt/train/drone/truck), **Resources** (editable node counts, extractor, clock), **Power** (add/edit/remove plants with MW, fuel, water, waste).
- Factory solving now uses world default recipes (`world_recipe`) under the factory's own overrides, and honours `factory_input`.
- **Done-when:** "a Project Assembly goal planned top-down shows raw totals vs budget and splits into ≥ 2 factories with auto-created flows" — ✔ `tests/test_world.py::test_project_assembly_top_down_split` (5 Project Assembly parts → raws vs budget → 3 factories, Smart Plating→Engines flow, Control's ingredients external → deficits reported and sorted first, flows idempotent) and a Playwright run (`tests/browser_check_world.py`, 1440 px and 1024 px: all pages 200, no overflow, no console errors, goal → split → flow visible).
- pytest 36 pass on 3.14 and in the 3.12 image. The Playwright run caught a template bug class again (`<form>` directly inside `<tr>`), fixed with `form=` attributes.
- **World numbers worth a look:** the imported world shows deficits that are real in the 1.x data — the "Rocket Fuel ×32" plant burns Rocket Fuel that no factory makes (short 1 333/min) and Uranium Waste demand slightly exceeds nuclear waste supply (10/min).
- **Deploy held:** schema 002 is a migration, and CLAUDE.md requires `ssh docker02-deploy backup` first; it still fails ("mkdir: Permission denied", see the BLOCKED entry under Phase 2). The migration runner makes its own dated copy of `planner2.db` in the data volume before applying (tested) and the live DB holds only the re-creatable 1.x import, so risk is low — but I am respecting the rule: **Phase 3 is pushed and tagged but not deployed to docker02**. The moment `backup` works (or you tell me to deploy without it) it is `backup → pull → restart`. Phase 4 work continues on sfdev1 meanwhile.

### Decisions

- Resource budget uses node **counts** (from 1.x) × Docs extractor rates × purity × clock (default 250 % = the 1.x assumption, so budgets match). Individual `resource_node`/`node_claim` rows need node data from the save → deferred to Phase 4's import; claimed-vs-available bars are driven by factory demand until then. The plan's "community node table" fallback is not needed, so no licence question arises.
- Nitrogen Gas: 1.x budgeted it at the Oil Extractor rate (24 000/min); 2.0 uses the Resource Well Extractor from the Docs (1 000 mL/s ⇒ 60 m³/min normal) = 12 000/min with the same node counts. Intentional: accuracy to the Docs. Edit on Resources if you disagree.
- Fluid energy values converted to MJ per m³ (×1000) in the builder so generator fuel rates match the game (Turbofuel 7.5 m³/min etc.).
- Power "used" = factory machines only (extractors excluded for now); said so on the page.
- Ledger counts only `planned`/`built` factories; `draft`/`archived` are ignored.
- Split semantics: assigning an item sets that factory's output to the world's required rate; "with everything below" makes the factory build the whole subtree except items other factories already make (those become external inputs → flows); unticked = only that item, direct ingredients external. Any other factory that was building the assigned item internally switches to taking it from the new maker.
- Auto flows are rebuilt from scratch on every split (`auto=1` rows only); hand-made flows (`auto=0`) are never touched. Flows allocate producers in factory-id order, shortfalls stay as ledger deficits.
- Removing goals, manual flows and power plants is allowed (user-initiated UI actions); factories still cannot be deleted.

## 2026-11-01 — Phase 4: Save import (complete, `v2-p4`; **deploy held**)

- **Vendored parser:** `@etothepii/satisfactory-file-parser` 4.1.2 (MIT) bundled with esbuild 0.28.2 into `static/vendor/satisfactory-file-parser.bundle.js` (334 KB) + `VERSION` + `satisfactory-file-parser.LICENSE`; build files in `tools/vendor/` (`package.json`, lockfile, `entry.mjs`, `build.mjs`; `node_modules` ignored). Dev tooling only; not in the image's runtime.
- **Browser side:** `static/js/import.worker.js` (module worker) → `extract.js` (parsed save → compact buildings + links; belts/lifts/pipes collapsed into links with a length) → server. `selective.js` wraps three hot spots of the *unmodified* parser (skip objects the planner never reads; decompress by offset — the library re-slices the whole remaining file after every chunk, O(n²); faster string reads). Output is byte-identical to the unpatched parser on MK1-2i.
- **Server side:** `core/grouping.py` + `core/importer.py` (distance and connection grouping, stations/Dimensional-Depot uploaders never join groups and attach to their neighbours' group, links over the long-belt limit become flows not joins, labels, per-recipe production lines with clock/sloops, net outputs/needs, flows with transport belt/train/drone/truck, power plants from generator groups, re-import overlap matching), `app/import_service.py` (save, match ≥ 50 %, attach to an existing planned factory, flag-not-delete of vanished factories, idempotent digest), `app/import_routes.py`, **Import** page (progress bar, both groupings side by side with top-down SVG plots and sliders for distance threshold and long-belt length, review table with rename/type/merge/split/attach/include, save). Factory page now has **Built vs planned** (machines built from the save vs the solver's plan, with SHORT/Extra/Matches words).
- **Done-when:**
  - *MK1-2i acceptance* ✔ `test_mk1_acceptance_hmf_factory` and the Playwright run: connection grouping puts all 10 `Alternate: Heavy Modular Frame` machines in **one** factory group ("Heavy Modular Frame factory", 400 buildings, 134 machines over ≥ 3 floors, with its 5 train platform/station buildings, receiving ingots/cement/beams); distance grouping also keeps it whole. It is fed by ≥ 3 separate groups, including two 20-smelter "Iron Ingot outposts" ~260–300 m away. **Honest note:** in this save those feeders reach the HMF factory over 430–530 m *belts* (so they show as belt flows over the 300 m limit), not train links; the 14 train stations in the save are all in the HMF group and in a second area, and a save contains no timetable, so train flows are only inferred when two groups both have train stations and no belt joins them.
  - *M1-8m parses < 30 s without freezing the page* ✔ **10.2 s** in headless Chromium inside a worker; worst main-thread frame gap 332 ms (node, same bundle: 11.6 s). Stock parser: 79 s in Chromium.
  - *Re-importing the same save changes nothing* ✔ (second import returns "No changes", row counts identical for factories, lines, flows, plants, outputs — pytest and browser).
- pytest 45 pass on 3.14; 42 pass + 3 skipped in the 3.12 image (the skipped ones need node and the saves' parser, which the image has not). Playwright: factory, world and import checks at 1440 and 1024 px, no console errors.
- **Deploy held** (same reason as Phase 3: `backup` still fails — BLOCKED entry under Phase 2). Phase 3 + 4 are pushed and tagged; deploying them is `backup → pull → up` (the image needs no new dependencies, but static/vendor is new so a plain `restart` also works since static is mounted).

### Decisions

- Outpost rule: a group is an *outpost* if it has extractors, ≤ 60 machines and every machine recipe takes only raw resources (ore→ingot, pure ingots, wet concrete…). The plan's "a few smelters" would have called 20-smelter feeders factories; recipe-based is the same idea made precise. `power` = generators and no machines; `other` = nothing productive.
- Names come from the group's deepest product (recipe-chain depth, then rate), so the HMF area is "Heavy Modular Frame factory", not "Steel Pipe factory"; a coordinate suffix keeps duplicates unique.
- Resource-node purity and type are not stored per node in a save (they are blueprint defaults), so no `resource_node` rows are created; extractors' resource is read from their output inventory. Budget stays the 1.x node counts (Phase 3 decision).
- Imported groups become `built` factories with `origin='import'`; "attach" puts lines on an existing planned factory and leaves its status alone. Power plants are upserted by a key stable across saves.
- Splitting a group re-groups just its buildings with the *other* method at half the distance threshold; merging recomputes rates server-side at save time.
- The server is stateless during review (the page resends the compact list, a few hundred KB, ~4.5 MB for the 34 MB save) — no upload storage, nothing to clean up.
- No new tables: `imported_building`/`import_run` from the plan hold the raw buildings and the fingerprint (`summary.digest`).

## 2026-11-01 — BLOCKED resolved; Phase 3 + 4 deploy

- The `docker02-deploy backup` BLOCKED entry (Phase 2 deploy note) is **resolved** by the overseer (history kept above). Deploying the held work now: `backup` (exit status checked) → `pull` → `up` → `status` → page checks on :8043. Result recorded below.
- **Deploy result (commit `bd602f4`, includes tags `v2-p3`, `v2-p4`):** `backup` exit 0 (`planner2-20261101-205007.db`), `pull` exit 0, `up` exit 0, container healthy. Migration 002 applied on startup (the migration runner also keeps its own pre-migration copy); the one-shot startup import added 13 resource rows (`resources: 13`). Page checks against http://192.168.23.86:8043 all 200: `/health`, `/`, `/goals`, `/factories`, `/flows`, `/power`, `/resources`, `/import`, `/factory/1,2,5`, both exports, `import.js`, `import.worker.js`, the parser bundle. Read-only browser check on the live site: `/import` with MK1-2i.sav parses in the worker and lists 48 groups by connection / 30 by distance with no console errors (nothing saved to the live DB). Phase 4 itself was already complete and tagged before this deploy.

## 2026-11-01 — Phase 5 (polish done; cutover pending) — deployed `9d006c7`

- **Polish shipped** (deployed after a successful `backup`, `pull`, `restart`; all pages and the new routes 200 on :8043): theme toggle (system → light → dark, remembered, no flash), **Ctrl+K** search over items, recipes and factories (arrow keys, Enter, Esc; focus returns), read-only `/item/<class>` and `/recipe/<class>` pages (who makes/uses an item; per-minute rates and power at 100 %/250 %/fully slooped), 44 px minimum for buttons, selects, inputs, summaries and nav links. `tests/browser_check_shell.py` scans every control on every page at 1024 px (≥ 40 px, no horizontal page scroll), exercises the toggle and the palette; the factory, world and import checks still pass. pytest 46 pass (3.14), 43 pass + 3 skipped in the 3.12 image. Excel/JSON export of a factory is kept from 1.x (Phase 2).
- Root README has the 2.0 section for Phases 1–4 (updated at each phase); the Phase 5 line is added when the cutover happens. The overseer updates the wiki.
- **Not done:** the cutover. Per PLAN.md and the autonomous-mode rules this is a MAJOR decision, so I am **not tagging `v2-p5`** (its done-when is "all pages 200 on :8042; 1.x restorable from the tag") and have not touched 1.x.

BLOCKED (RESOLVED 2026-11-01 21:25 — Michael approved; cutover done 21:31, v2-p5): Phase 5 cutover of 1.x — please confirm (Michael/overseer) and note the one thing I cannot do myself.
- **Proposed steps (nothing run):** (1) tag the current 1.x state `v1-final` (annotated, pushed) — 1.x code (`backend/`, `frontend/`, root `Dockerfile`, root `docker-compose.yml`) is unchanged since `99716bd`, so this tag is exactly what is live; (2) stop and remove the 1.x container `ficsit-planner` (keep its `data/` directory untouched on disk as the rollback copy — nothing is deleted); (3) `git mv` the 1.x code into `legacy/` (so a restart of the old stack is `git checkout v1-final`); (4) change `v2/docker-compose.yml` host port 8043 → **8042** and `up`; (5) check every 2.0 page returns 200 on :8042 and `/health`; (6) update the README, add `v2-p5` and tell the overseer to update the wiki.
- **Rollback:** `git checkout v1-final` + `docker compose up -d` in the old layout; 1.x's `data/planner.db` is never modified.
- **Why I'm stuck on step 2/4 regardless of the answer:** the deploy entry point (`docker02-deploy`) only offers status/backup/pull/up/restart/logs/seed1x and runs compose inside `v2/` — it cannot stop or remove the `ficsit-planner` container, and moving `backend/`+`frontend/` while that container (which bind-mounts them) is running would break it mid-flight. Needs a new forced-command verb (e.g. `cutover`: `docker compose -f /opt/sf-planner/docker-compose.yml down` then restart v2 on 8042) or someone running those two commands on docker02. Recommendation: add a one-shot `cutover` verb, then I run steps 1–6 in order and report.
- Also changes **port/exposure** (8042 now served by 2.0; 8043 retired), which is why this is blocked rather than decided.

## 2026-11-01 — /health version + operations docs (waiting for the cutover decision)

- `/health` now reports `version` (`2.0-p4`), `tag` (`v2-p4`, the last tagged phase) and `state` from `v2/app/version.py` (update it with each phase tag); test added.
- New `v2/docs/OPERATIONS.md`: run locally, tests (incl. the 3.12 image runner), deploy order with `backup`, rollback by revert, database backup/restore, starting from scratch, and how 1.x comes back — untouched and live today; after the cutover via the `v1-final` tag. README links to it. The restore procedure needs a docker02 shell (no verb for it), so it names the overseer.
- Per the overseer: the cutover is with Michael; I have not started it and added nothing to `docker02-deploy`. If approved, the overseer stops 1.x and tells me to move 2.0 to :8042. Stopping here after this deploy.

## 2026-11-01 — Phase 5 cutover: code pushed, deploy stopped at `pull`

- Committed and pushed `eecd6ca`: `v2/docker-compose.yml` host port 8043 → **8042** (read-only `../data` mount kept); `backend/`, `frontend/`, root `Dockerfile` and root `docker-compose.yml` `git mv`'d to `legacy/` with `legacy/docker-compose.yml` data path fixed (`../data:/app/data`; `docker compose config` resolves for both files; not started); README, CLAUDE.md (:8042 wording, 1.x retired), `v2/docs/OPERATIONS.md` (cutover done, how to bring 1.x back from `legacy/` or `v1-final`) and PLAN.md status updated; parity tooling/test runner now read `legacy/backend` (pytest 47 pass on 3.14, 44 + 3 skipped on 3.12, parity not skipped).
- Deploy: `backup` exit 0 (`planner2-20261101-212743.db`). **`pull` failed (exit 1):** docker02's working tree has an uncommitted local change to the root `docker-compose.yml` ("Your local changes … would be overwritten by merge"), which the commit moves to `legacy/`. Nothing was changed on docker02: 2.0 is still running on :8043 as before, :8042 is still free. I cannot see or fix the working tree through `docker02-deploy`, and I will not force anything.

BLOCKED (RESOLVED by overseer: docker02 had an assume-unchanged local edit to the old root docker-compose.yml — PLANNER_HOST=docker02 — saved to data/docker-compose.v1-docker02-local.yml and discarded; docker02 then pulled to 07403c5): `ssh docker02-deploy pull` aborts on docker02 because the root `docker-compose.yml` there has local edits (probably made while stopping 1.x). Needs the overseer on docker02: look at `git diff docker-compose.yml` in `/opt/sf-planner`, then `git checkout -- docker-compose.yml` (or `git stash`) so the fast-forward can apply. Then I continue: `pull` → `up` → verify :8042 (and nothing on :8043) → tag `v2-p5`.

## 2026-11-01 — Phase 5 complete: cutover done (`v2-p5`)

- After the overseer cleaned docker02's working tree: `up` exit 0 → container `sf-planner-v2` healthy, **published on :8042**. `status` (now checking :8042) healthy.
- Verified on http://192.168.23.86:8042, all 200: `/health`, `/`, `/factories`, `/power`, `/goals`, `/resources`, `/import`, `/flows`, `/factory/2`, `/api/factory/2/export.xlsx`. **Nothing answers on :8043** (connection refused, curl exit 7). Existing data intact (imported 1.x factories, plants, resources as before).
- `/health` now reports `2.0-p5` / tag `v2-p5` / "all phases complete; 2.0 serves :8042; 1.x retired to legacy/ (tag v1-final)" (small code change deployed with `pull` + `restart`; no migration).
- 1.x: stopped by the overseer; code in `legacy/`; tag `v1-final` = `99716bd`; data untouched at `data/planner.db` (+ `data/planner-v1-final-20261101.db`, `data/docker-compose.v1-docker02-local.yml`). To bring it back: `v2/docs/OPERATIONS.md`, section "1.x and getting it back".
- **Phase 5 done-when:** all pages 200 on :8042 ✔; 1.x restorable from the tag ✔ (tag exists; `legacy/` compose resolves — never started, as instructed). Wiki update is the overseer's. Plan status: Phases 1–5 complete.
- Open: nothing blocking. Note for the overseer: the `ssh docker02-deploy status` output works again against :8042; CLAUDE.md's dev-server port (sfdev1 :8043) is unchanged and is not the docker02 port.
