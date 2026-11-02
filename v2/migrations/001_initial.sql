CREATE TABLE world (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    save_name TEXT,
    game_build TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE world_goal (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    world_id INTEGER NOT NULL REFERENCES world(id) ON DELETE CASCADE,
    item TEXT,                 -- item class, NULL for a power goal
    rate_per_min REAL,         -- items/min
    power_mw REAL,             -- or MW
    CHECK ((item IS NOT NULL AND rate_per_min IS NOT NULL) OR power_mw IS NOT NULL)
);

CREATE TABLE world_recipe (
    world_id INTEGER NOT NULL REFERENCES world(id) ON DELETE CASCADE,
    item TEXT NOT NULL,
    recipe TEXT NOT NULL,      -- recipe class
    PRIMARY KEY (world_id, item)
);

CREATE TABLE factory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    world_id INTEGER NOT NULL REFERENCES world(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'planned'
        CHECK (status IN ('planned', 'built', 'draft', 'archived')),
    x REAL, y REAL, z REAL,
    notes TEXT NOT NULL DEFAULT '',
    origin TEXT NOT NULL DEFAULT 'manual' CHECK (origin IN ('manual', 'import')),
    source_ref TEXT,           -- e.g. '1x:factory:12' for the 1.x importer (idempotency)
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX factory_source_ref ON factory(source_ref) WHERE source_ref IS NOT NULL;

CREATE TABLE factory_output (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    factory_id INTEGER NOT NULL REFERENCES factory(id) ON DELETE CASCADE,
    item TEXT NOT NULL,
    rate_per_min REAL NOT NULL
);

-- Per-factory, per-item overrides. Approved by Michael: clock/sloop live here.
CREATE TABLE factory_recipe (
    factory_id INTEGER NOT NULL REFERENCES factory(id) ON DELETE CASCADE,
    item TEXT NOT NULL,
    recipe TEXT,               -- recipe class override (NULL = world/default)
    clock_pct REAL,            -- NULL = 100
    sloops INTEGER CHECK (sloops >= 0),  -- Somersloop count, 0..slots of the recipe's machine; NULL = 0
    PRIMARY KEY (factory_id, item)
);

CREATE TABLE production_line (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    factory_id INTEGER NOT NULL REFERENCES factory(id) ON DELETE CASCADE,
    item TEXT NOT NULL,
    recipe TEXT NOT NULL,
    machine TEXT NOT NULL,
    count REAL NOT NULL,
    clock_pct REAL NOT NULL DEFAULT 100,
    sloops INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE flow (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    world_id INTEGER NOT NULL REFERENCES world(id) ON DELETE CASCADE,
    from_factory INTEGER REFERENCES factory(id) ON DELETE CASCADE,
    to_factory INTEGER REFERENCES factory(id) ON DELETE CASCADE,
    item TEXT NOT NULL,
    rate_per_min REAL NOT NULL,
    transport TEXT CHECK (transport IN ('belt', 'train', 'drone', 'truck'))
);

CREATE TABLE resource_node (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    world_id INTEGER NOT NULL REFERENCES world(id) ON DELETE CASCADE,
    node_ref TEXT,
    resource TEXT NOT NULL,
    purity TEXT NOT NULL CHECK (purity IN ('impure', 'normal', 'pure')),
    x REAL, y REAL, z REAL
);

CREATE TABLE node_claim (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id INTEGER NOT NULL REFERENCES resource_node(id) ON DELETE CASCADE,
    factory_id INTEGER NOT NULL REFERENCES factory(id) ON DELETE CASCADE,
    miner TEXT NOT NULL,       -- extractor class
    clock_pct REAL NOT NULL DEFAULT 100
);

CREATE TABLE power_plant (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    world_id INTEGER NOT NULL REFERENCES world(id) ON DELETE CASCADE,
    name TEXT NOT NULL DEFAULT '',
    generator TEXT NOT NULL,   -- generator class
    fuel TEXT NOT NULL,        -- fuel item class
    count INTEGER NOT NULL DEFAULT 1,
    clock_pct REAL NOT NULL DEFAULT 100,
    source_ref TEXT
);
CREATE UNIQUE INDEX power_plant_source_ref ON power_plant(source_ref) WHERE source_ref IS NOT NULL;

CREATE TABLE import_run (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    world_id INTEGER NOT NULL REFERENCES world(id) ON DELETE CASCADE,
    file_name TEXT NOT NULL,
    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    summary TEXT
);

CREATE TABLE imported_building (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    import_run_id INTEGER NOT NULL REFERENCES import_run(id) ON DELETE CASCADE,
    instance_name TEXT NOT NULL,
    class TEXT NOT NULL,
    recipe TEXT,
    clock REAL,
    sloops INTEGER,
    x REAL, y REAL, z REAL,
    factory_id INTEGER REFERENCES factory(id) ON DELETE SET NULL,
    grp TEXT
);
