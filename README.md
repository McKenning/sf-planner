# FICSIT Planner

A self-hosted production planner for [Satisfactory](https://www.satisfactorygame.com/) 1.0. Plan individual factories, aggregate them into a world view, balance nuclear waste chains, track power budgets, and export everything to Excel.

Built to answer the question: *how many producers do I build, at what speed, to keep my plans within the limits of the game?*

## Features

### Production Planning
- **Solver** — Set target products and rates. The solver walks the full recipe tree to calculate machines needed, clock speeds, power draw, and raw resource demand.
- **All 243 recipes** from Satisfactory 1.0, including alternates with community tier ratings (S through F).
- **Recipe overrides** — Choose alternate recipes per product. Overrides are per-factory, so different factories can use different recipes for the same product.
- **Clock speed overrides** — Set target clock speeds (1–250%) per product. The solver adjusts machine counts and power accordingly.
- **Cyclic recipe support** — Handles feedback loops like Recycled Rubber/Plastic through iterative demand propagation.

### Factories & World View
- **Factories** — Save named snapshots of production targets + recipe choices (e.g. "Uranium Rod Production", "Plutonium Rod Production", "Ficsonium Rod Production").
- **Editable factories** — Add, update, and delete targets directly on the factory detail page. Change recipe choices per factory. The full chain re-solves on every change.
- **World view** — Aggregates all saved factories into a combined production chain, resource budget, and power demand.

### Nuclear & Power
- **Power plants** — Define generators with fuel type, count, and clock speed. Supports Coal, Fuel, Nuclear (Uranium/Plutonium/Ficsonium), and all generator types.
- **Fuel chain solving** — For power plants without a factory producing their fuel, the solver computes the full upstream production chain. When a factory already supplies the fuel, only the deficit (PP demand minus factory supply) is solved independently—no double-counting.
- **Nuclear waste balance** — Tracks waste produced by generators vs. waste consumed by production (e.g. Uranium Waste → Non-Fissile Uranium → Plutonium Fuel Rods). Shows net surplus or deficit.
- **Awesome Sink tracking** — Shows surplus fuel production (factory output beyond what power plants burn) destined for the sink.

### Resource Budget
- **World resource nodes** — Set pure/normal/impure node counts per resource. These are fixed map values; the only variables are miner tier and overclock (assumed Mk.3 at 250%).
- **Utilization tracking** — Demand vs. available for all 13 raw resources with utilization bars and shortfall warnings.

### Export
- **Excel export** — 7-sheet formatted workbook: Production Chain, Resource Budget, Targets, Recipe Choices, Power Plants, Clock Overrides, and Resource Nodes. Styled with frozen headers, auto-width columns, and conditional highlighting.
- **JSON export** — Raw plan state for programmatic access.

## Quick Start

```bash
git clone https://github.com/McKenning/sf-planner.git
cd sf-planner
docker compose up -d --build
```

Open `http://localhost:8042`

## Pages

| Route | Description |
|---|---|
| `/` | Main planner — set targets, recipes, clock speeds, resources, power plants |
| `/factory/<id>` | Factory detail — full production chain for a saved factory with editable targets and recipe choices |
| `/world` | World view — aggregated factories + power plants with waste balance and resource budget |
| `/power` | Power overview — all generators with fuel chains |
| `/powerplant/<id>` | Power plant detail — single generator with full fuel production chain |
| `/api/plan/export/xlsx` | Excel export |
| `/api/plan/export` | JSON export |

## Configuration

Environment variables in `docker-compose.yml`:

| Variable | Default | Description |
|---|---|---|
| `PLANNER_HOST` | Container hostname | Display name shown in footer |
| `TZ` | `America/Denver` | Timezone for timestamps |

To change the exposed port, edit the `ports` mapping (e.g. `"3000:8000"` for port 3000).

## Data

Plan data is stored in a SQLite database at `data/planner.db`, persisted via Docker volume mount. Back up this file to preserve your plans.

### Database Tables

| Table | Purpose |
|---|---|
| `plans` | Plan metadata (only one active plan currently) |
| `targets` | Production targets for the active plan |
| `recipe_choices` | Alternate recipe overrides (plan-level) |
| `clock_overrides` | Per-product clock speed overrides |
| `resources` | World resource node allocations (pure/normal/impure counts + miner tier) |
| `factories` | Named factory snapshots |
| `factory_targets` | Per-factory production targets |
| `factory_choices` | Per-factory recipe overrides |
| `power_plants` | Generator definitions (type, fuel, count, clock) |

## Architecture

- **Backend**: Python 3.12 / FastAPI / Jinja2 / SQLite
- **Solver**: Recursive dependency resolver with topological ordering, cycle detection, and iterative demand propagation for feedback loops
- **Frontend**: Vanilla HTML/CSS/JS with server-side Jinja2 templates (no build step, no framework)
- **Styling**: Custom dark theme with JetBrains Mono, Inter, and Bebas Neue fonts
- **Deployment**: Single Docker container, ~50MB image

## How the World View Works

The world view solves each factory and power plant independently, then aggregates the results:

1. **Factory solves** — Each factory's targets are solved with its own recipe choices. Raw resource demands are summed into `world_raws`.
2. **Fuel deficit calculation** — For each fuel type, total PP demand is compared against total factory supply. If a factory produces the fuel (e.g. Plutonium Fuel Rods), only the deficit is solved as an independent chain.
3. **Waste balance** — Generator waste output (Uranium Waste, Plutonium Waste) is compared against total consumption from all production chains. The display shows produced, consumed, and net balance.
4. **Sink calculation** — Factory production of fuels that exceeds PP consumption is reported as surplus destined for the Awesome Sink.

## License

[MIT](LICENSE)


## SF Planner 2.0 (in `v2/`, in progress)

Fresh rewrite for Satisfactory 1.1, built beside 1.x, which it replaced on 2026-11-01. Live at https://sfplanner.kenningfamily.org. Plan: `v2/docs/PLAN.md`; build log: `v2/docs/PROGRESS.md`.

- Phase 1 (done): game data generated from the game's Docs file (`v2/tools/build_gamedata.py` → `v2/core/gamedata.json`), 1.1 power maths (`v2/core/power.py`), SQLite migrations, 1.x importer, read-only World/Factories/Power pages.
- Phase 2 (done): solver with byproducts and loops (`v2/core/solver.py`), factory page with inline recipe/clock/Somersloop edits and a recipe comparison, Excel/JSON export; every imported 1.x factory matches 1.x's solver (power differs by design). Parity report: `v2/docs/PARITY-1x-*.md`.
- Phase 3 (done): World home (resource budget bars, power generated vs used, item ledger with deficits first, warnings), top-down Goals with a production tree and split into factories (auto-created flows), Flows, Resources (node counts → budget), editable Power plants.
- Phase 4 (done): **Import** page — pick a `.sav`; a Web Worker parses it in the browser (vendored `@etothepii/satisfactory-file-parser` 4.1.2, MIT, in `v2/static/vendor/`) and only a compact building list goes to the server, which groups it by connection and by distance (shown side by side), labels factory/outpost/power, and saves built factories with production lines, power plants and flows. Re-import matches factories by ≥50 % building overlap; an identical save changes nothing. Rebuild the parser bundle (dev only): `cd v2/tools/vendor && npm ci && npm run build`.
- Runs as container `sf-planner-v2` on host port **8042** since the cutover (`v2/docker-compose.yml`; dev server uses 8043). Dev: `cd v2 && python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt && .venv/bin/pytest`, then `uvicorn app.main:app --port 8043`.

**Operating 2.0** (run, tests, deploy, backup/restore, and how to bring 1.x back from `v1-final` after the cutover): see [`v2/docs/OPERATIONS.md`](v2/docs/OPERATIONS.md). `/health` at https://sfplanner.kenningfamily.org/health reports the current phase/tag.

**Repository layout after the cutover:** 2.0 lives in `v2/` and is what runs at https://sfplanner.kenningfamily.org (docker02 nginx terminates TLS and proxies to the container on 127.0.0.1:8042). The old 1.x app is kept in `legacy/` (its `docker-compose.yml` runs from there, data in the repo-root `data/`), and the annotated tag `v1-final` is the last 1.x commit. See the operations guide for bringing 1.x back.
