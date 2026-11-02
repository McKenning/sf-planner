// Module worker: parse a .sav off the main thread and return only the compact building list.
import * as P from '../vendor/satisfactory-file-parser.bundle.js';
import { extract } from './extract.js';
import { installFast } from './selective.js';

const { Parser } = P;
installFast(P);

self.onmessage = async (ev) => {
  const { buffer, name } = ev.data;
  try {
    const t0 = performance.now();
    const save = Parser.ParseSave(name, buffer, {
      onProgressCallback: (p, msg) => self.postMessage({ type: 'progress', phase: 'parse', progress: p, msg }),
    });
    self.postMessage({ type: 'progress', phase: 'extract', progress: 1 });
    const payload = extract(save);
    payload.game.parseSeconds = (performance.now() - t0) / 1000;
    self.postMessage({ type: 'done', payload });
  } catch (e) {
    self.postMessage({ type: 'error', message: String(e && e.message || e) });
  }
};
