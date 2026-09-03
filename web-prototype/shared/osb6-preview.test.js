import test from "node:test";
import assert from "node:assert/strict";

import { parseOsb6Preview } from "./osb6-preview.js";

function sampleBundle() {
  const textureBytes = 2;
  const payloadLength = 24 + 4 + 28 * 3 + 8;
  const bytes = new Uint8Array(16 + textureBytes + 8 + payloadLength);
  const view = new DataView(bytes.buffer);
  bytes.set([79, 83, 66, 54], 0); // OSB6
  view.setUint32(4, 1, true);
  view.setUint32(8, 1, true);
  view.setUint32(12, 1, true);
  // Opaque red in RGBA5551.
  bytes[16] = 0xf8;
  bytes[17] = 0x01;
  let offset = 18;
  view.setUint32(offset, 3, true);
  view.setUint32(offset + 4, payloadLength, true);
  offset += 8;
  bytes.set([79, 83, 66, 53], offset); // OSB5
  view.setUint32(offset + 4, 1, true);
  view.setUint32(offset + 8, 3, true);
  view.setUint32(offset + 12, 1, true);
  view.setUint32(offset + 24, 6, true);
  const vertices = offset + 28;
  for (let index = 0; index < 3; index += 1) {
    const at = vertices + index * 28;
    view.setFloat32(at, index === 1 ? 1 : 0, true);
    view.setFloat32(at + 4, index === 2 ? 1 : 0, true);
    view.setInt8(at + 26, 127);
  }
  const triangles = vertices + 28 * 3;
  view.setUint16(triangles, 0, true);
  view.setUint16(triangles + 2, 1, true);
  view.setUint16(triangles + 4, 2, true);
  return bytes;
}

test("OSB6 preview parser extracts the requested in-game mesh and texture", () => {
  const parsed = parseOsb6Preview(sampleBundle(), 3);

  assert.equal(parsed.fkind, 3);
  assert.deepEqual([...parsed.positions], [0, 0, 0, 1, 0, 0, 0, 1, 0]);
  assert.deepEqual([...parsed.indices], [0, 1, 2]);
  assert.deepEqual([...parsed.rgba], [255, 0, 0, 255]);
  assert.deepEqual([...parsed.uvs], [0, 0, 0, 0, 0, 0]);
});

test("OSB6 preview parser rejects truncated data", () => {
  assert.throws(() => parseOsb6Preview(new Uint8Array([79, 83, 66, 54]), 0), /Truncated/);
});
