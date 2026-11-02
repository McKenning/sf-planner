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
