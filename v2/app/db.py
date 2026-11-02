"""SQLite access and numbered-migration runner."""
import os
import re
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS = ROOT / "migrations"
DATA_DIR = Path(os.environ.get("SFP_DATA_DIR", ROOT / "data"))
DB_PATH = DATA_DIR / "planner2.db"


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path or DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _migration_files(directory: Path):
    out = []
    for p in sorted(directory.glob("*.sql")):
        m = re.match(r"(\d+)_", p.name)
        if m:
            out.append((int(m.group(1)), p))
    return out


def applied_versions(conn) -> set[int]:
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_version'").fetchone()
    if not exists:
        return set()
    return {r[0] for r in conn.execute("SELECT version FROM schema_version")}


def migrate(path: Path | str | None = None, directory: Path = MIGRATIONS) -> list[int]:
    """Apply pending migrations. Takes a dated backup first if the DB already has data."""
    path = Path(path or DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(path)
    try:
        done = applied_versions(conn)
        pending = [(v, p) for v, p in _migration_files(directory) if v not in done]
        if not pending:
            return []
        if done:  # existing schema -> back up before changing it
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            backup = path.with_name(f"{path.stem}.pre-migration-{stamp}{path.suffix}")
            src = sqlite3.connect(str(path))
            dst = sqlite3.connect(str(backup))
            with dst:
                src.backup(dst)
            src.close()
            dst.close()
        conn.execute("CREATE TABLE IF NOT EXISTS schema_version ("
                     "version INTEGER PRIMARY KEY, name TEXT NOT NULL, "
                     "applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
        applied = []
        for v, p in pending:
            try:
                conn.executescript("BEGIN;\n" + p.read_text() +
                                   f"\nINSERT INTO schema_version(version, name) VALUES ({v}, '{p.name}');\nCOMMIT;")
            except Exception:
                conn.rollback()
                raise
            applied.append(v)
        return applied
    finally:
        conn.close()
