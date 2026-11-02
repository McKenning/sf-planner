// Dev-only. Bundles the save parser into one ESM file for the browser and records version + licence.
//   cd v2/tools/vendor && npm ci && npm run build
import { build } from 'esbuild';
import fs from 'fs';
import path from 'path';
const out = path.resolve('../../static/vendor');
fs.mkdirSync(out, { recursive: true });
const pkgDir = 'node_modules/@etothepii/satisfactory-file-parser';
const pkg = JSON.parse(fs.readFileSync(`${pkgDir}/package.json`, 'utf8'));
await build({
  entryPoints: ['entry.mjs'], bundle: true, format: 'esm', platform: 'browser', target: 'es2022',
  minify: true, legalComments: 'none', outfile: `${out}/satisfactory-file-parser.bundle.js`,
});
const lic = fs.readdirSync(pkgDir).find(f => /^licen[sc]e/i.test(f));
fs.copyFileSync(`${pkgDir}/${lic}`, `${out}/satisfactory-file-parser.LICENSE`);
const esb = JSON.parse(fs.readFileSync('node_modules/esbuild/package.json', 'utf8'));
fs.writeFileSync(`${out}/VERSION`,
  `@etothepii/satisfactory-file-parser ${pkg.version} (${pkg.license})\nbundled with esbuild ${esb.version}\nrebuild: cd v2/tools/vendor && npm ci && npm run build\n`);
console.log('bundle', fs.statSync(`${out}/satisfactory-file-parser.bundle.js`).size, 'bytes');
