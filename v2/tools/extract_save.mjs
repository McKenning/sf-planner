// Dev/test CLI: node tools/extract_save.mjs <save.sav> [out.json]
// Runs the same extract() as the browser worker on a save, for tests and offline inspection.
import fs from 'fs';
import { fileURLToPath } from 'url';
import path from 'path';
const here = path.dirname(fileURLToPath(import.meta.url));
const { Parser } = await import(path.join(here, 'vendor/node_modules/@etothepii/satisfactory-file-parser/build/index.js'));
const { extract } = await import(path.join(here, '../static/js/extract.js'));
const buf = fs.readFileSync(process.argv[2]);
const t0 = Date.now();
const save = Parser.ParseSave('save', buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength));
const t1 = Date.now();
const out = extract(save);
const t2 = Date.now();
const json = JSON.stringify(out);
if (process.argv[3]) fs.writeFileSync(process.argv[3], json);
console.error(`parse ${t1 - t0} ms, extract ${t2 - t1} ms, ${out.buildings.length} buildings, ${out.links.length} links, ${json.length} bytes`);
