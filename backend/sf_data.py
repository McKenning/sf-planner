"""
Satisfactory 1.0 MASTER Planner data module.
Source: MAZ01001/SatisfactoryFlowchart data.json (game Docs.json-derived)
"""

# Machine power consumption (MW base, at 100% clock)
# Source: Satisfactory wiki
MACHINES = {
    "Smelter":              {"power": 4,    "inputs": 1, "outputs": 1},
    "Foundry":              {"power": 16,   "inputs": 2, "outputs": 1},
    "Constructor":          {"power": 4,    "inputs": 1, "outputs": 1},
    "Assembler":            {"power": 15,   "inputs": 2, "outputs": 1},
    "Manufacturer":         {"power": 55,   "inputs": 4, "outputs": 1},
    "Refinery":             {"power": 30,   "inputs": 2, "outputs": 2},
    "Blender":              {"power": 75,   "inputs": 4, "outputs": 2},
    "Packager":             {"power": 10,   "inputs": 2, "outputs": 2},
    "Particle Accelerator": {"power": 1000, "inputs": 3, "outputs": 1},  # avg, varies
    "Quantum Encoder":      {"power": 2000, "inputs": 4, "outputs": 2},  # avg
    "Converter":            {"power": 500,  "inputs": 2, "outputs": 1},  # avg
    "Crafting Bench":       {"power": 0,    "inputs": 4, "outputs": 1},  # manual
    "Equipment Workshop":   {"power": 0,    "inputs": 4, "outputs": 1},  # manual
}

# Miner throughput (items/min) at 100% clock speed
# Source: Satisfactory wiki. Oil Extractor and Water Extractor values included.
MINER_RATES = {
    # Miner Mk.1
    ("Miner Mk.1", "Impure"): 30,
    ("Miner Mk.1", "Normal"): 60,
    ("Miner Mk.1", "Pure"):   120,
    # Miner Mk.2
    ("Miner Mk.2", "Impure"): 60,
    ("Miner Mk.2", "Normal"): 120,
    ("Miner Mk.2", "Pure"):   240,
    # Miner Mk.3
    ("Miner Mk.3", "Impure"): 120,
    ("Miner Mk.3", "Normal"): 240,
    ("Miner Mk.3", "Pure"):   480,
    # Oil Extractor (m^3/min of Crude Oil)
    ("Oil Extractor", "Impure"): 60,
    ("Oil Extractor", "Normal"): 120,
    ("Oil Extractor", "Pure"):   240,
    # Water Extractor (m^3/min)
    ("Water Extractor", "Normal"): 120,
    # Resource Well Extractor (per satellite node, multiplied by purity of that node)
    ("Resource Well Extractor", "Impure"):  30,
    ("Resource Well Extractor", "Normal"):  60,
    ("Resource Well Extractor", "Pure"):   120,
}

# Raw resources available to the world (pioneer-extractable at 100% Mk.3 overclocked / Mk.2 base — actual node counts)
# Source: user's Resources sheet image + satisfactory-calculator node totals
# Format: {resource: {"pure": n_nodes, "normal": n_nodes, "impure": n_nodes, "total_mk2": items_per_min_total}}
RESOURCES = {
    "Limestone":     {"pure": 29, "normal": 50, "impure": 15, "total_mk2": 69900},
    "Iron Ore":      {"pure": 46, "normal": 42, "impure": 39, "total_mk2": 92100},
    "Copper Ore":    {"pure": 13, "normal": 29, "impure": 13, "total_mk2": 36900},
    "Caterium Ore":  {"pure": 8,  "normal": 9,  "impure": 0,  "total_mk2": 15000},
    "Coal":          {"pure": 16, "normal": 31, "impure": 15, "total_mk2": 43300},
    "Raw Quartz":    {"pure": 7,  "normal": 7,  "impure": 3,  "total_mk2": 13500},
    "Sulfur":        {"pure": 5,  "normal": 5,  "impure": 6,  "total_mk2": 10800},
    "Bauxite":       {"pure": 6,  "normal": 6,  "impure": 5,  "total_mk2": 12300},
    "Nitrogen Gas":  {"pure": 36, "normal": 7,  "impure": 2,  "total_mk2": 12000},  # from wells
    "Uranium":       {"pure": 0,  "normal": 2,  "impure": 3,  "total_mk2": 2100},
    "SAM":           {"pure": 3,  "normal": 6,  "impure": 10, "total_mk2": 10200},
    "Crude Oil":     {"pure": 12, "normal": 18, "impure": 18, "total_mk2": 12480}, # nodes+wells combined
    "Water":         {"pure": 0,  "normal": 0,  "impure": 0,  "total_mk2": 999999}, # unlimited via extractors
}

# Alternate recipe tier list (from Wrigh516 and community consensus)
# Tiers: S (must-have), A (great), B (solid), C (situational), D (niche), F (avoid)
ALT_TIERS = {
    "Alternate: Heavy Encased Frame": "S",
    "Alternate: Caterium Computer": "S",
    "Alternate: Crystal Computer": "S",
    "Alternate: Silicon Circuit Board": "S",
    "Alternate: Heavy Flexible Frame": "S",
    "Alternate: Caterium Circuit Board": "S",
    "Alternate: Super-State Computer": "S",
    "Alternate: Copper Alloy Ingot": "S",
    "Alternate: Automated Speed Wiring": "S",
    "Alternate: Silicon High-Speed Connector": "S",
    "Alternate: Coke Steel Ingot": "S",
    "Alternate: Turbo Pressure Motor": "S",
    "Alternate: Turbo Blend Fuel": "S",
    "Alternate: Pure Aluminum Ingot": "S",
    "Alternate: Solid Steel Ingot": "S",
    "Alternate: Steeled Frame": "S",
    "Alternate: Sloppy Alumina": "S",
    "Alternate: Encased Industrial Pipe": "S",
    "Alternate: Heat-Fused Frame": "S",
    "Alternate: Pure Iron Ingot": "S",
    "Alternate: Pure Copper Ingot": "S",
    "Alternate: Pure Caterium Ingot": "S",
    "Alternate: Pure Quartz Crystal": "S",
    "Alternate: Heat Exchanger": "S",
    "Alternate: Flexible Framework": "S",
    "Alternate: Steel Rotor": "A",
    "Alternate: Plastic AI Limiter": "A",
    "Alternate: Electrode Aluminum Scrap": "A",
    "Alternate: Recycled Plastic": "A",
    "Alternate: Recycled Rubber": "A",
    "Alternate: Diluted Fuel": "A",
    "Alternate: Nitro Rocket Fuel": "A",
    "Alternate: Cast Screw": "A",
    "Alternate: Steel Screw": "A",
    "Alternate: Stitched Iron Plate": "A",
    "Alternate: Iron Alloy Ingot": "A",
    "Alternate: Quickwire Cable": "A",
    "Alternate: Radio Control System": "A",
    "Alternate: Steel Cast Plate": "A",
    "Alternate: Molded Beam": "A",
    "Alternate: Molded Steel Pipe": "A",
    "Alternate: Heavy Oil Residue": "A",
    "Alternate: Compacted Coal": "A",
    "Alternate: Fine Concrete": "A",
    "Alternate: Rigor Motor": "A",
    "Alternate: Steamed Copper Sheet": "A",
    "Alternate: Fused Wire": "B",
    "Alternate: Fused Quickwire": "B",
    "Alternate: Caterium Wire": "B",
    "Alternate: Coated Iron Plate": "B",
    "Alternate: Coated Cable": "B",
    "Alternate: Electromagnetic Connection Rod": "B",
    "Alternate: Insulated Cable": "B",
    "Alternate: Insulated Crystal Oscillator": "B",
    "Alternate: Rubber Concrete": "B",
    "Alternate: Wet Concrete": "B",
    "Alternate: Bolted Iron Plate": "B",
    "Alternate: Steel Rod": "B",
    "Alternate: OC Supercomputer": "B",
    "Alternate: Radio Connection Unit": "B",
    "Alternate: Quickwire Stator": "B",
    "Alternate: Plastic Smart Plating": "B",
    "Alternate: Diluted Packaged Fuel": "B",
    "Alternate: Copper Rotor": "B",
    "Alternate: Polyester Fabric": "B",
    "Alternate: Fused Quartz Crystal": "B",
    "Alternate: Electric Motor": "B",
    "Alternate: Basic Iron Ingot": "C",
    "Alternate: Coated Iron Canister": "C",
    "Alternate: Steel Canister": "C",
    "Alternate: Bolted Frame": "C",
    "Alternate: Cooling Device": "C",
    "Alternate: Aluminum Beam": "C",
    "Alternate: Aluminum Rod": "C",
    "Alternate: Fine Black Powder": "C",
    "Alternate: Adhered Iron Plate": "C",
    "Alternate: Instant Scrap": "C",
    "Alternate: Classic Battery": "C",
    "Alternate: Distilled Silica": "C",
    "Alternate: Quartz Purification": "C",
    "Alternate: Tempered Copper Ingot": "C",
    "Alternate: Tempered Caterium Ingot": "C",
    "Alternate: Compacted Steel Ingot": "C",
    "Alternate: Turbo Electric Motor": "C",
    "Alternate: Turbo Heavy Fuel": "C",
    "Alternate: Uranium Fuel Unit": "C",
    "Alternate: Plutonium Fuel Unit": "C",
    "Alternate: Leached Iron ingot": "D",
    "Alternate: Leached Copper Ingot": "D",
    "Alternate: Leached Caterium Ingot": "D",
    "Alternate: Iron Pipe": "D",
    "Alternate: Iron Wire": "D",
    "Alternate: Infused Uranium Cell": "D",
    "Alternate: Instant Plutonium Cell": "D",
    "Alternate: Automated Miner": "D",
    "Alternate: Oil-Based Diamonds": "D",
    "Alternate: Petroleum Diamonds": "D",
    "Alternate: Pink Diamonds": "D",
    "Alternate: Turbo Diamonds": "D",
    "Alternate: Dark Matter Trap": "D",
    "Alternate: Dark Matter Crystallization": "D",
    "Alternate: Electrode Circuit Board": "D",
    "Alternate: Polymer Resin": "D",
    "Alternate: Dark-Ion Fuel": "F",
    "Alternate: Fertile Uranium": "F",
    "Alternate: Cloudy Diamonds": "F",
    "Alternate: Biocoal": "F",
    "Alternate: Charcoal": "F",
}
print(f"Module loaded. Machines: {len(MACHINES)}, Resources: {len(RESOURCES)}, Tiered alts: {len(ALT_TIERS)}")


# Power generators: type -> {power_mw, fuels: {fuel: consumption_per_min at 100%}}
# All generators scale linearly with clock speed
GENERATORS = {
    "Coal Generator": {
        "power_mw": 75,
        "fuels": {
            "Coal": 15,
            "Compacted Coal": 7.143,
            "Petroleum Coke": 25,
        },
        "water_per_min": 45,
    },
    "Fuel Generator": {
        "power_mw": 250,
        "fuels": {
            "Fuel": 20,
            "Liquid Biofuel": 20,
            "Turbofuel": 7.5,
            "Rocket Fuel": 4.167,
            "Ionized Fuel": 3,
        },
        "water_per_min": 0,
    },
    "Nuclear Power Plant": {
        "power_mw": 2500,
        "fuels": {
            "Uranium Fuel Rod": 0.2,
            "Plutonium Fuel Rod": 0.1,
            "Ficsonium Fuel Rod": 0.1,
        },
        "water_per_min": 240,
    },
}
