// Pure extraction: parsed save -> compact building list + logistic links.
// Used unchanged by the browser worker and by tools/extract_save.mjs (so tests exercise the same code).
// Output coordinates are metres. Belts/lifts/pipes are collapsed into links with a length.

const MACHINE = /^Build_(Constructor|Smelter|Foundry|Assembler|Manufacturer|OilRefinery|Blender|Packager|HadronCollider|Converter|QuantumEncoder)(Mk\d+)?_C$/;
const EXTRACTOR = /^Build_(MinerMk\d|OilPump|WaterPump|FrackingExtractor)_C$/;
const GENERATOR = /^Build_Generator\w+_C$/;
const STATION = [
  [/^Build_TrainStation_C$|^Build_TrainDockingStation(Liquid)?(Mk\d)?_C$|^Build_TrainPlatform\w*_C$/, 'train'],
  [/^Build_DroneStation_C$/, 'drone'],
  [/^Build_TruckStation_C$|^Build_Truck\w*Station\w*_C$/, 'truck'],
];
const STORAGE = /^Build_(StorageContainer\w*|StorageIntegrated\w*|PipeStorageTank\w*|IndustrialTank\w*|CentralStorage\w*)_C$/;
const JUNCTION = /^Build_(ConveyorAttachmentSplitter\w*|ConveyorAttachmentMerger\w*|CA_\w+|PipelineJunction\w*|PipelinePump\w*|PipelineSupport\w*|ValveIntegrated\w*|Valve\w*)_C$/;
const EDGE = /^Build_(ConveyorBelt\w*|ConveyorLift\w*|Pipeline(MK2)?(_NoIndicator)?\w*|PipelineMK2\w*)_C$/;

const shortName = (p) => p.substring(p.indexOf('.') + 1).replace(/^PersistentLevel\./, '');
const clsOf = (typePath) => typePath.substring(typePath.lastIndexOf('.') + 1);
const lastSeg = (p) => p.substring(p.lastIndexOf('.') + 1);
const ownerOf = (p) => p.substring(0, p.lastIndexOf('.'));
const num = (prop, d) => (prop && typeof prop.value === 'number' ? prop.value : d);
const vlen = (a, b) => Math.hypot(a.x - b.x, a.y - b.y, a.z - b.z);

function kindOf(cls) {
  if (MACHINE.test(cls)) return ['machine', null];
  if (EXTRACTOR.test(cls)) return ['extractor', null];
  if (GENERATOR.test(cls) && !/Geo/.test(cls)) return ['generator', null];
  if (/Geo/.test(cls) && GENERATOR.test(cls)) return ['generator', null];
  for (const [re, mode] of STATION) if (re.test(cls)) return ['station', mode];
  if (STORAGE.test(cls)) return ['storage', null];
  if (JUNCTION.test(cls)) return ['junction', null];
  if (EDGE.test(cls)) return ['edge', null];
  return [null, null];
}

function edgeLength(o) {
  const sp = o.properties && o.properties.mSplineData;
  if (sp && sp.values && sp.values.length > 1) {
    let total = 0, prev = null;
    for (const v of sp.values) {
      const l = v.properties.Location.value;
      if (prev) total += vlen(prev, l);
      prev = l;
    }
    return total / 100;
  }
  const top = o.properties && o.properties.mTopTransform;
  if (top) return Math.abs(top.value.properties.Translation.value.z) / 100;
  return 0;
}

export function extract(save) {
  const objs = new Map();
  for (const lvl of Object.values(save.levels)) for (const o of lvl.objects) objs.set(o.instanceName, o);

  const ents = new Map(); // name -> {o, kind, mode, cls}
  const compOwner = new Map(); // component instanceName -> owner entity name
  for (const o of objs.values()) {
    if (o.type !== 'SaveEntity') continue;
    const cls = clsOf(o.typePath);
    const [kind, mode] = kindOf(cls);
    if (kind) {
      ents.set(o.instanceName, { o, kind, mode, cls });
      for (const c of o.components || []) compOwner.set(c.pathName, o.instanceName);
    }
  }

  // adjacency between entities through their connection components
  const adj = new Map();
  const link = (a, b) => {
    if (!a || !b || a === b) return;
    (adj.get(a) || adj.set(a, new Set()).get(a)).add(b);
    (adj.get(b) || adj.set(b, new Set()).get(b)).add(a);
  };
  for (const [name, e] of ents) {
    for (const c of e.o.components || []) {
      const co = objs.get(c.pathName);
      const tgt = co && co.properties && co.properties.mConnectedComponent;
      if (!tgt || !tgt.value || !tgt.value.pathName) continue;
      const other = compOwner.get(tgt.value.pathName);
      if (other) link(name, other);
    }
  }

  const buildings = [];
  const idx = new Map();
  const nodeSet = new Map();
  for (const [name, e] of ents) {
    if (e.kind === 'edge') continue;
    const p = e.o.properties || {};
    const t = e.o.transform.translation;
    const b = {
      id: shortName(name), cls: e.cls, kind: e.kind,
      x: Math.round(t.x) / 100, y: Math.round(t.y) / 100, z: Math.round(t.z) / 100,
    };
    if (e.mode) b.mode = e.mode;
    if (e.kind === 'machine') {
      const r = p.mCurrentRecipe && p.mCurrentRecipe.value && p.mCurrentRecipe.value.pathName;
      b.recipe = r ? lastSeg(r) : null;
    }
    if (e.kind === 'machine' || e.kind === 'extractor' || e.kind === 'generator') {
      b.clock = num(p.mCurrentPotential, num(p.mPendingPotential, 1));
      b.boost = num(p.mCurrentProductionBoost, num(p.mPendingProductionBoost, 1));
    }
    if (e.kind === 'extractor') {
      const n = p.mExtractableResource && p.mExtractableResource.value && p.mExtractableResource.value.pathName;
      if (n) { b.node = shortName(n); nodeSet.set(n, true); }
      for (const c of e.o.components || []) {
        if (lastSeg(c.pathName) !== 'OutputInventory') continue;
        const co = objs.get(c.pathName);
        const al = co && co.properties && co.properties.mAllowedItemDescriptors;
        if (al && al.values && al.values[0] && al.values[0].pathName) b.resource = lastSeg(al.values[0].pathName);
      }
    }
    if (e.kind === 'generator') {
      const f = p.mCurrentFuelClass || p.mFuelClass;
      if (f && f.value) b.fuel = typeof f.value === 'string' ? lastSeg(f.value) : lastSeg(f.value.pathName || '');
    }
    idx.set(name, buildings.length);
    buildings.push(b);
  }

  // collapse belt/lift/pipe chains into links between real nodes
  const links = [];
  const seen = new Set();
  for (const [name, e] of ents) {
    if (e.kind === 'edge') continue;
    for (const nb of adj.get(name) || []) {
      let prev = name, cur = nb, len = 0, guard = 0;
      while (ents.get(cur) && ents.get(cur).kind === 'edge' && guard++ < 5000) {
        len += edgeLength(ents.get(cur).o);
        let next = null;
        for (const n2 of adj.get(cur) || []) if (n2 !== prev) { next = n2; break; }
        if (!next) { cur = null; break; }
        prev = cur; cur = next;
      }
      if (!cur || !idx.has(cur) || cur === name) continue;
      const a = idx.get(name), b = idx.get(cur);
      const key = a < b ? `${a}-${b}` : `${b}-${a}`;
      // keep the shortest of parallel links
      const prevLink = seen.has(key);
      if (!prevLink) { seen.add(key); links.push([Math.min(a, b), Math.max(a, b), Math.round(len * 10) / 10]); }
    }
  }

  const h = save.header || {};
  return {
    format: 1,
    game: { build: h.buildVersion, session: h.sessionName, saveName: h.saveName, map: h.mapName },
    buildings, links,
  };
}
