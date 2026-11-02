// Speed-ups for the (unmodified) save parser. None of them changes what is parsed:
//  1. skip objects the planner never reads (contents are length-prefixed, so skipping is exact);
//  2. decompress chunks by offset (the library re-slices the whole remaining file after every chunk: O(n^2));
//  3. read strings without a per-character array.
// On a 34 MB save this takes the parse from ~80 s to a few seconds.
import { wantEntity, wantComponent } from './extract.js';

export function installFast({ SaveEntity, SaveComponent, SaveBodyChunks, ByteReader, Alignment, pako }) {
  const origEntity = SaveEntity.ParseData;
  const origComponent = SaveComponent.ParseData;
  SaveEntity.ParseData = function (entity, length, reader, typePath) {
    if (!wantEntity(typePath)) { reader.skipBytes(length); return; }
    return origEntity.call(this, entity, length, reader, typePath);
  };
  SaveComponent.ParseData = function (component, length, reader, typePath) {
    if (!wantComponent(component.instanceName, typePath)) { reader.skipBytes(length); return; }
    return origComponent.call(this, component, length, reader, typePath);
  };

  SaveBodyChunks.DecompressChunks = (fileBuffer, alignment = Alignment.LITTLE_ENDIAN) => {
    const le = alignment === Alignment.LITTLE_ENDIAN;
    const view = new DataView(fileBuffer);
    const bytes = new Uint8Array(fileBuffer);
    let pos = 0, first = true, tag = 0, version = SaveBodyChunks.HEADER_V2, headerSize = 0, maxChunk = 0;
    let algo = 3;
    const chunks = [];
    let total = 0;
    while (pos < fileBuffer.byteLength) {
      if (first) {
        tag = view.getUint32(pos, le);
        version = view.getUint32(pos + 4, le);
        headerSize = version === SaveBodyChunks.HEADER_V1 ? 48 : 49;
        maxChunk = view.getInt32(pos + 8, le);
        if (version === SaveBodyChunks.HEADER_V2) algo = view.getUint8(pos + 16);
        first = false;
      }
      const compressedLen = view.getInt32(pos + (version === SaveBodyChunks.HEADER_V1 ? 32 : 33), le);
      pos += headerSize;
      const out = pako.inflate(bytes.subarray(pos, pos + compressedLen));
      chunks.push(out);
      total += out.length;
      pos += compressedLen;
    }
    const whole = new Uint8Array(total);
    let off = 0;
    for (const c of chunks) { whole.set(c, off); off += c.length; }
    return { uncompressedData: whole, compressionInfo: {
      chunkHeaderVersion: version, packageFileTag: tag, maxUncompressedChunkContentSize: maxChunk, compressionAlgorithm: algo } };
  };

  const slow = ByteReader.prototype.readString;
  ByteReader.prototype.readString = function () {
    const len = this.readInt32();
    if (len === 0) return '';
    const bv = this.bufferView;
    if (len > bv.buffer.byteLength - this.currentByte) {
      throw new Error(`Cannot read string of length ${len} at position ${this.currentByte} as it exceeds the end at ${bv.buffer.byteLength}`);
    }
    if (len < 0) {                       // UTF-16
      const n = -len - 1, le = this.alignment === Alignment.LITTLE_ENDIAN;
      let s = '';
      for (let i = 0; i < n; i += 4096) {
        const m = Math.min(4096, n - i), arr = new Array(m);
        for (let j = 0; j < m; j++) arr[j] = bv.getUint16(this.currentByte + 2 * (i + j), le);
        s += String.fromCharCode.apply(null, arr);
      }
      this.currentByte += 2 * n + 2;
      return s;
    }
    const n = len - 1;                   // one byte per char, as the library does
    const u8 = new Uint8Array(bv.buffer, bv.byteOffset + this.currentByte, n);
    let s = '';
    for (let i = 0; i < n; i += 8192) s += String.fromCharCode.apply(null, u8.subarray(i, Math.min(i + 8192, n)));
    this.currentByte += n + 1;
    return s;
  };
  return { restoreReadString: () => { ByteReader.prototype.readString = slow; } };
}
