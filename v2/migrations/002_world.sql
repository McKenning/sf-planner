-- Phase 3: world budget, factory external inputs, auto flows.
CREATE TABLE world_resource (
    world_id INTEGER NOT NULL REFERENCES world(id) ON DELETE CASCADE,
    resource TEXT NOT NULL,            -- item class (raw resource)
    pure INTEGER NOT NULL DEFAULT 0,
    normal INTEGER NOT NULL DEFAULT 0,
    impure INTEGER NOT NULL DEFAULT 0,
    miner TEXT,                        -- extractor class used to budget this resource
    clock_pct REAL NOT NULL DEFAULT 250,
    PRIMARY KEY (world_id, resource)
);

-- Items a factory takes from other factories instead of building (the split's "cut points").
CREATE TABLE factory_input (
    factory_id INTEGER NOT NULL REFERENCES factory(id) ON DELETE CASCADE,
    item TEXT NOT NULL,
    PRIMARY KEY (factory_id, item)
);

-- auto = 1: derived from factory_input/outputs by the app (rebuilt on every change); 0 = entered by hand
ALTER TABLE flow ADD COLUMN auto INTEGER NOT NULL DEFAULT 0 CHECK (auto IN (0, 1));
