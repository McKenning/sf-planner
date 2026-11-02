# SF Planner 2.0 — Plan

**Status (2026-11-01): Phases 1–5 complete; cutover done, 2.0 on :8042, 1.x in `legacy/` and tag `v1-final`.** Approved by Michael Kenning, 2026-11-01. Source: the "SF Planner 2.0 — Plan" doc in the claude.ai Project "Satisfactory Planner". This file is the copy the build session works from; if they ever disagree, ask.

Build 2.0 fresh beside 1.x, using 1.x only as reference, in five phases on sfdev1. Each phase ships to docker02 as soon as its checks pass, with tagged commits so any step can be reverted.

## Decisions

| Topic | Michael's answer | What the plan does with it |
| --- | --- | --- |
| Build host | Create the VM | sfdev1 (VM 124, 192.168.23.84); Claude Code logged in as Michael ("Timmy") |
| Deploy cadence | As fast as possible, keep build commits | Ship each passing step; tag every phase so any step can be reverted |
| Game version | 1.1 | Game data generated from the install's Docs file (build 25782416) |
| Save parser | Browser-side | Vendored MIT parser in a Web Worker; only a compact building list goes to the server |
| Grouping imports | Try distance; connectedness probably better | Both run; review screen shows them side by side. MK1-2i's Rocky Desert HMF factory is the acceptance test |
| Planning direction | Both; top-down first, like Satisfactory Modeler | World goals and factory targets share one item ledger |
| Old plan scratchpad | Archive it | Becomes an archived draft factory, read-only |
| Rewrite vs migrate | Fresh 2.0 if easier | New `v2/` tree in the same repo; 1.x stays live until cutover |
| pytest | OK | Dev only; not in the image |
| Devices | Desktop first, tablet for out-of-game planning | Desktop layout; one tablet pass at 1024 px |
| Exposure | LAN only | No auth; port 8043 during the build, :8042 since the cutover (2026-11-01) |

## Architecture

2.0 keeps the same stack and lives in `v2/`. During the build it runs as a second container `sf-planner-v2` on docker02, host port **8043**. At cutover it takes over :8042.

- **Stack, unchanged:** Python 3.12, FastAPI, Jinja2, SQLite, vanilla JS (plain ES modules, no build step).
- **Layout:** `v2/app/` (routes, services), `v2/core/` (game data, math, solver — pure functions, no DB or web code, so pytest tests them directly), `v2/static/` (JS modules, CSS, `vendor/`), `v2/templates/`, `v2/migrations/`, `v2/tools/` (game-data builder, 1.x importer), `v2/tests/`.
- **Separate data:** `v2/data/planner2.db`. Never writes to 1.x's `planner.db`; the 1.x importer reads a copy.
- **Migrations:** numbered SQL files applied at startup, recorded in `schema_version`. Dated DB backup before any migration runs.
- **Dependencies:** pytest (dev only) and the vendored save parser. Anything else: ask first.
- **Cutover (Phase 5):** tag `v1-final`, point :8042 at 2.0, stop and remove the 1.x container, move 1.x code under `legacy/`. 1.x restorable from the tag.

## Game data and math

All game data comes from the install's `en-US.json` (UTF-16), which has class names (`Recipe_IronPlate_C`, `Build_ConstructorMk1_C`) that save import needs.

- `v2/tools/build_gamedata.py` reads the file and writes `v2/core/gamedata.json` (committed): items, recipes (class + display names, alternate flag, producing machine, inputs/outputs, duration), buildings (power, clock exponent, Somersloop slots, variable-power min/max), extractors and generators.
- When the game updates, re-run the builder and review the diff.
- 1.x treats power as linear in machine count — wrong for 1.0/1.1, so every power figure changes vs 1.x.

Per machine (constants read from the file: clock exponent 1.321929 for every production building, Somersloop power exponent 2.0):

```
P = P_base * (clock/100)^1.321929 * (1 + sloops/slots)^2
output multiplier = 1 + sloops/slots
```

Slots: Constructor 1, Converter 2, Particle Accelerator 4 (read from file). A full set doubles output and quadruples power. Variable-power machines (Particle Accelerator, Converter, Quantum Encoder) use the mean of the file's min and max. Golden tests pin these, e.g. one Constructor at 250% = 13.43 MW.

## Data model

Everything belongs to a **world**; factories are the only planning unit (1.x's duplicated plan/factory tables go away).

| Table | Holds |
| --- | --- |
| `world` | Name, linked save name, game build |
| `world_goal` | Top-down targets: item + rate/min, or MW |
| `world_recipe` | Default recipe per item for the world |
| `factory` | Name, status (planned / built / draft / archived), location x,y,z, notes, origin (manual / import) |
| `factory_output` | What a factory is meant to make: item + rate/min |
| `factory_recipe` | Per-factory, per-item override: recipe (nullable), `clock_pct` (nullable, NULL = 100), `sloops` (integer count, 0..slots of that recipe's machine, NULL = 0). Added 2026-11-01 at Michael's direction so 1.x clock/sloop overrides survive import; 1.x `slooped=1` maps to the machine's full slot count |
| `production_line` | Item, recipe, machine, count, clock %, sloops. Solver writes these for planned factories; import writes them for built ones |
| `flow` | Item between factories: from, to, item, rate/min, transport (belt, train, drone, truck) |
| `resource_node` | Node id, resource, purity, position |
| `node_claim` | Which factory uses a node, miner tier, clock |
| `power_plant` | Generators: type, fuel, count, clock |
| `import_run` | One save import: file name, time, summary |
| `imported_building` | Raw buildings from an import: instance name, class, recipe, clock, sloops, position, group |
| `schema_version` | Applied migrations |

1.x importer: 1.x factories → factories in world "Main"; 1.x power plants → power plants; 1.x scratchpad → archived draft factory "1.x plan (archived)" (currently empty in live data: 0 targets).

## World workflow

Top-down and bottom-up both write to one **item ledger**: per item, supply (factory outputs, flows in) vs demand (factory inputs, world goals).

**Top-down (default, like Satisfactory Modeler):**
1. Set world goals: Project Assembly parts at a rate, a sink target, or X MW.
2. Solver expands the full demand tree and compares raw totals with the world node budget. Over-budget resources show red immediately.
3. Choose recipes per item for the world, with side-by-side comparison of inputs, power, machines.
4. Split the tree into factories: assign an item (or an item and everything under it) to a new or existing factory. Cross-factory items become flows automatically.

**Bottom-up:** create a factory, set outputs, solver fills lines. Unmet inputs show as world deficits, spare outputs as surplus. One click links a deficit to a factory with surplus, creating a flow.

**World view is the home screen:** resource budget bars (claimed vs available), power (generated vs used), the ledger (deficits first), factory cards or a simple position map, warnings (unbalanced flows, over-budget nodes, missing recipes).

Solver handles byproducts and loops by solving the item balance as a small linear system in pure Python. Automatic recipe optimisation would need a solver library — out unless Michael asks.

## Save import

Pick a `.sav` in the browser. A Web Worker parses it with the vendored parser and posts only a compact building list (a few hundred KB even for 34 MB saves).

1. **Extract:** production buildings, extractors, generators (instance name, class, recipe, clock `mCurrentPotential`, Somersloops, position); also belts, pipes, lifts, splitters, mergers, storage, and train/drone/truck stations for grouping.
2. **Group two ways, side by side:**
    - *Distance:* buildings closer than a threshold (slider, default 60 m) form a group.
    - *Connection:* buildings joined by belts/pipes/lifts (through splitters, mergers, storage) form a group. Train, drone and truck stations break the chain (hand-off between factories). Very long belts (default > 300 m, adjustable) become a flow between groups, not a join.
3. **Label:** only extractors plus a few smelters = **outpost**; bigger = **factory**.
4. **Review:** top-down plot of groups next to a list; rename, merge, split, mark outpost, attach to an existing planned factory; save.
5. **Result:** built factories get real production lines and output rates; flows get transport types from stations; built vs planned side by side with gaps.
6. **Re-import:** each factory keeps its source instance names; a new save matches by overlap (>= 50% = same factory) and updates. New groups offered as new factories; unmatched factories flagged, never deleted.

**Acceptance test:** `MK1-2i.sav` with connection grouping gives the Rocky Desert HMF factory (standalone, train station, multiple floors, receives materials) as one factory, with its three adjacent feeder areas as separate outposts linked by train flows. `M1-8m.sav` (34 MB) parses in under 30 s without freezing the page.

## Interface

Every screen answers one question; the number that answers it is at the top. Details open in a side drawer.

- **Layout:** left nav (World, Goals, Factories, Power, Resources, Import), main pane, right detail drawer. Ctrl+K searches items, recipes, factories.
- **Factory page:** header strip (inputs, outputs, power, Somersloops); lines grouped by stage raw -> final; recipe, clock, sloops edited inline; recipe picker compares inputs per output, power, machine count; imported factories add built vs planned columns.
- **Clarity rules:** rates always per minute with units; one number per concept; colour always paired with a word/icon; deficits and warnings sorted to the top; nothing hover-only.
- **Theme:** follows system (dark/light) with a toggle.
- **Tablet:** works at 1024 px, touch targets >= 40 px.
- **Kept from 1.x:** Excel and JSON export.
- **Not included:** game item icons (game artwork); items shown by name.

## Phases

Each ships to docker02 as soon as its checks pass and ends with a tag (`v2-p1` ... `v2-p5`).

| Phase | Ships | Done when |
| --- | --- | --- |
| 1. Foundation | `v2/` skeleton + container on :8043; game-data builder; 1.1 math library; migrations; 1.x importer; read-only list of imported factories | pytest passes incl. power golden tests; recipe count matches the Docs file; all 1.x factories and power plants appear in 2.0 |
| 2. Factory planner | Solver with byproducts and loops; factory page; recipe picker; clocks and sloops; Excel/JSON export | Every imported 1.x factory solves with the same rates as 1.x; only power differs (expected); differences listed in PROGRESS.md |
| 3. World | World view; ledger; goals + split (top-down); deficits + links (bottom-up); flows; power plants; resource budget; node claims | A Project Assembly goal planned top-down shows raw totals vs budget and splits into >= 2 factories with auto-created flows |
| 4. Save import | Worker parser; extraction; distance + connection grouping; review screen; re-import matching; built vs planned | MK1-2i acceptance test passes; M1-8m parses < 30 s; re-importing the same save changes nothing |
| 5. Polish + cutover | Tablet pass; README; 2.0 moves to :8042; 1.x removed, tagged `v1-final`; wiki updated | All pages 200 on :8042; 1.x restorable from the tag |

Phase 5 cutover touches 1.x — confirm with Michael before running it.

## Open items and risks

- Done 2026-11-01: deploy keys added (docker02 read-only, sfdev1 write); sfdev1 -> docker02 deploy via forced-command key (see CLAUDE.md).
- Old GitHub PAT: Michael to revoke.
- Parser vendoring needs a one-off bundle step (Node + esbuild on sfdev1, dev only); commit the output.
- Resource node positions/purity are not in the Docs file. Phase 3 first tries the save; if absent, propose a community node table and check its licence with Michael.
- Not a node-graph canvas: ledger + split rather than a free-form graph editor, unless Michael asks.
- Port 8043 was temporary; 2.0 has served :8042 since the cutover (2026-11-01). Dev server on sfdev1 still uses 8043.
- 1.x power numbers will differ from 2.0 — that's the fix.
