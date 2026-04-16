# FICSIT Planner

A self-hosted production planner for [Satisfactory](https://www.satisfactorygame.com/) 1.0. Plan individual factories, then combine them into a world view to see your total resource budget, power demand, and production chain at a glance.

## Features

- **Production solver** — Add target products and rates, and the solver walks the full recipe tree to calculate machines, power, clock speeds, and raw resource demand
- **Recipe overrides** — Choose alternate recipes per product, with community tier ratings (S through F) shown inline
- **Resource budget** — Set your world's node counts and miner tier to see utilization and shortfalls at a glance
- **Factories** — Save snapshots of your current plan as named factories (e.g. "Iron Mall", "Oil Processing", "Space Elevator")
- **World view** — Aggregates all saved factories into a combined production chain and resource budget
- **All 243 recipes** from Satisfactory 1.0, including alternates

## Quick Start

```bash
git clone https://github.com/McKenning/sf-planner.git
cd sf-planner
docker compose up -d --build
```

Open `http://localhost:8042`

## Configuration

All configuration is via environment variables in `docker-compose.yml`:

| Variable | Default | Description |
|---|---|---|
| `PLANNER_HOST` | Container hostname | Display name shown in the footer |
| `TZ` | `America/Denver` | Timezone for timestamps |

To change the exposed port, edit the `ports` mapping (e.g. `"3000:8000"` for port 3000).

## Data

Plan data is stored in a SQLite database at `data/planner.db`, persisted via Docker volume mount. Back up this file to preserve your plans.

## Stack

- **Backend**: Python / FastAPI / Jinja2 / SQLite
- **Frontend**: Vanilla HTML/CSS/JS (single-file templates, no build step)
- **Deployment**: Docker

## License

[MIT](LICENSE)
