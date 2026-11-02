// Entry for the browser bundle. The parser itself is unmodified; we additionally expose the few
// internals that static/js/selective.js wraps (speed-ups that do not change what is parsed).
export { Parser, SaveEntity, SaveComponent } from '@etothepii/satisfactory-file-parser';
export { SaveBodyChunks } from '@etothepii/satisfactory-file-parser/build/parser/satisfactory/save/save-body-chunks.js';
export { ByteReader } from '@etothepii/satisfactory-file-parser/build/parser/byte/byte-reader.class.js';
export { Alignment } from '@etothepii/satisfactory-file-parser/build/parser/byte/alignment.enum.js';
export { default as pako } from 'pako';
