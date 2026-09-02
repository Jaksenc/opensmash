import assert from "node:assert/strict";
import { createHash, webcrypto } from "node:crypto";
import test from "node:test";
import {
  BlobWriter,
  TextReader,
  Uint8ArrayReader,
  ZipWriter,
} from "@zip.js/zip.js";
import {
  identifyRomBytes,
  identifyRomFile,
  normalizeN64,
} from "../src/rom-validation.js";

function canonicalFixture() {
  const bytes = new Uint8Array(128);
  for (let index = 0; index < bytes.length; index += 1) bytes[index] = (index * 29) & 0xff;
  bytes.set([0x80, 0x37, 0x12, 0x40], 0);
  return bytes;
}

function encodeByteOrder(canonical, format) {
  const bytes = canonical.slice();
  if (format === "v64") {
    for (let index = 0; index < bytes.length; index += 2) {
      [bytes[index], bytes[index + 1]] = [bytes[index + 1], bytes[index]];
    }
  } else if (format === "n64") {
    for (let index = 0; index < bytes.length; index += 4) {
      [bytes[index], bytes[index + 3]] = [bytes[index + 3], bytes[index]];
      [bytes[index + 1], bytes[index + 2]] = [bytes[index + 2], bytes[index + 1]];
    }
  }
  return bytes;
}

function withHeaderAndPadding(bytes) {
  const wrapped = new Uint8Array(512 + bytes.length + 73);
  wrapped.fill(0xa5, 0, 512);
  wrapped.set(bytes, 512);
  wrapped.fill(0xff, 512 + bytes.length);
  return wrapped;
}

function fixtureCatalog(canonical) {
  return [{
    sha1: createHash("sha1").update(canonical).digest("hex"),
    name: "Synthetic Smash fixture",
    region: "Test",
    serial: "TEST",
    size: canonical.length,
  }];
}

test("normalizes z64, v64, and n64 byte orders after a leading header", () => {
  const canonical = canonicalFixture();
  for (const format of ["z64", "v64", "n64"]) {
    const encoded = format === "z64" ? canonical : encodeByteOrder(canonical, format);
    const normalized = normalizeN64(withHeaderAndPadding(encoded));
    assert.deepEqual(normalized.subarray(0, canonical.length), canonical, format);
  }
});

test("identifies a canonical ROM after byte-order conversion and trailing padding", async () => {
  const canonical = canonicalFixture();
  const catalog = fixtureCatalog(canonical);

  for (const format of ["z64", "v64", "n64"]) {
    const encoded = format === "z64" ? canonical : encodeByteOrder(canonical, format);
    const rom = await identifyRomBytes(withHeaderAndPadding(encoded), {
      catalog,
      subtle: webcrypto.subtle,
    });
    assert.equal(rom?.name, "Synthetic Smash fixture", format);
    assert.equal(rom?.sha1, catalog[0].sha1, format);
    assert.equal(rom?.size, canonical.length, format);
  }
});

test("unwraps and identifies a ZIP entirely from its Blob", async () => {
  const canonical = canonicalFixture();
  const catalog = fixtureCatalog(canonical);
  const writer = new ZipWriter(new BlobWriter("application/zip"));
  await writer.add("notes.txt", new TextReader("not a ROM"));
  await writer.add("odd-name.data", new Uint8ArrayReader(withHeaderAndPadding(encodeByteOrder(canonical, "v64"))));
  const zip = await writer.close();
  const statuses = [];

  const rom = await identifyRomFile(zip, {
    catalog,
    subtle: webcrypto.subtle,
    onStatus: (status) => statuses.push(status),
  });

  assert.equal(rom.name, "Synthetic Smash fixture");
  assert.ok(statuses.includes("extracting"));
  assert.ok(statuses.includes("hashing"));
});

test("rejects data with an N64 header but an unknown canonical hash", async () => {
  const canonical = canonicalFixture();
  const altered = canonical.slice();
  altered[64] ^= 0xff;
  const rom = await identifyRomBytes(altered, {
    catalog: fixtureCatalog(canonical),
    subtle: webcrypto.subtle,
  });
  assert.equal(rom, null);
});

test("names the region when a real but unsupported dump is uploaded", async () => {
  const canonical = canonicalFixture();
  const foreign = new Uint8Array(canonical.length);
  foreign.set(canonical);
  foreign[canonical.length - 1] ^= 0x5a;
  const unsupported = [{
    sha1: createHash("sha1").update(foreign).digest("hex"),
    name: "Synthetic Europe fixture",
    region: "Europe",
    size: foreign.length,
  }];
  await assert.rejects(
    identifyRomBytes(withHeaderAndPadding(foreign), {
      catalog: fixtureCatalog(canonical),
      unsupported,
      subtle: webcrypto.subtle,
    }),
    /Europe release/,
  );
  // The supported image is unaffected by the unsupported list.
  const rom = await identifyRomBytes(withHeaderAndPadding(canonical), {
    catalog: fixtureCatalog(canonical),
    unsupported,
    subtle: webcrypto.subtle,
  });
  assert.equal(rom?.region, "Test");
});
