// Independent save reader for QA: stock parser (no selective.js patches), no extract.js.
// node tests/qa/save_oracle.mjs <save.sav> <out.json>  -> {instanceName: {cls, recipe, potential, pending, boost}}
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
const here = path.dirname(fileURLToPath(import.meta.url));
const { Parser } = await import(path.join(here, '../../static/vendor/satisfactory-file-parser.bundle.js'));
const buf = fs.readFileSync(process.argv[2]);
const save = Parser.ParseSave('s', buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength));
const out = {};
const re = /^Build_(Constructor|Smelter|Foundry|Assembler|Manufacturer|OilRefinery|Blender|Packager|HadronCollider|Converter|QuantumEncoder)(Mk\d+)?_C$/;
for (const lvl of Object.values(save.levels)) for (const o of lvl.objects) {
  if (o.type !== 'SaveEntity') continue;
  const cls = o.typePath.substring(o.typePath.lastIndexOf('.') + 1);
  if (!re.test(cls)) continue;
  const p = o.properties || {};
  const v = (k) => (p[k] && typeof p[k].value === 'number' ? p[k].value : null);
  const rec = p.mCurrentRecipe && p.mCurrentRecipe.value ? p.mCurrentRecipe.value.pathName : null;
  out[o.instanceName.substring(o.instanceName.indexOf('.') + 1).replace(/^PersistentLevel\./, '')] = {
    cls, recipe: rec ? rec.substring(rec.lastIndexOf('.') + 1) : null,
    potential: v('mCurrentPotential'), pending: v('mPendingPotential'), boost: v('mCurrentProductionBoost'), pendingBoost: v('mPendingProductionBoost') };
}
fs.writeFileSync(process.argv[3], JSON.stringify(out));
console.error(Object.keys(out).length, 'machines');
