import {
  BlobReader,
  Uint8ArrayWriter,
  ZipReader,
} from "@zip.js/zip.js";
import { ROM_CATALOG } from "../shared/rom-catalog.js";

const MIB = 1024 * 1024;
const MAX_INPUT_SIZE = 128 * MIB;
const MAX_ZIP_ENTRIES = 128;
const MAX_HEADER_SIZE = 4096;

const N64_MAGICS = Object.freeze([
  Object.freeze({ format: "z64", bytes: Object.freeze([0x80, 0x37, 0x12, 0x40]) }),
  Object.freeze({ format: "v64", bytes: Object.freeze([0x37, 0x80, 0x40, 0x12]) }),
  Object.freeze({ format: "n64", bytes: Object.freeze([0x40, 0x12, 0x37, 0x80]) }),
]);

function matchesMagic(bytes, offset, magic) {
  return magic.every((value, index) => bytes[offset + index] === value);
}

function findN64Header(bytes) {
  const lastOffset = Math.min(MAX_HEADER_SIZE, bytes.length - 4);
  for (let offset = 0; offset <= lastOffset; offset += 1) {
    const magic = N64_MAGICS.find((candidate) => matchesMagic(bytes, offset, candidate.bytes));
    if (magic) return { format: magic.format, offset };
  }
  return null;
}

export function normalizeN64(input) {
  const source = input instanceof Uint8Array ? input : new Uint8Array(input);
  const header = findN64Header(source);
  if (!header) {
    throw new Error("No N64 ROM header was found in that file.");
  }

  if (header.format === "z64") {
    return source.subarray(header.offset);
  }

  const rom = source.slice(header.offset);
  if (header.format === "v64") {
    const end = rom.length - (rom.length % 2);
    for (let index = 0; index < end; index += 2) {
      const first = rom[index];
      rom[index] = rom[index + 1];
      rom[index + 1] = first;
    }
  } else {
    const end = rom.length - (rom.length % 4);
    for (let index = 0; index < end; index += 4) {
      const first = rom[index];
      const second = rom[index + 1];
      rom[index] = rom[index + 3];
      rom[index + 1] = rom[index + 2];
      rom[index + 2] = second;
      rom[index + 3] = first;
    }
  }
  return rom;
}

export async function digestHex(algorithm, bytes, subtle = globalThis.crypto?.subtle) {
  if (!subtle) throw new Error("This browser cannot validate ROM files.");
  const digest = await subtle.digest(algorithm, bytes);
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

export async function identifyRomBytes(input, options = {}) {
  const catalog = options.catalog || ROM_CATALOG;
  const subtle = options.subtle || globalThis.crypto?.subtle;
  const normalized = normalizeN64(input);
  const bySize = new Map();
  for (const rom of catalog) {
    const entries = bySize.get(rom.size) || [];
    entries.push(rom);
    bySize.set(rom.size, entries);
  }

  // Prefer an exact-size match, then try shorter catalog sizes. The latter
  // safely handles trailing copier padding because the final digest must still
  // match a known canonical image.
  const sizes = [...bySize.keys()]
    .filter((size) => size <= normalized.length)
    .sort((left, right) => {
      if (left === normalized.length) return -1;
      if (right === normalized.length) return 1;
      return right - left;
    });

  for (const size of sizes) {
    const sha1 = await digestHex("SHA-1", normalized.subarray(0, size), subtle);
    const rom = bySize.get(size).find((candidate) => candidate.sha1 === sha1);
    if (rom) return { ...rom, sha1, size };
  }
  return null;
}

async function isZip(blob) {
  if (blob.size < 4) return false;
  const signature = new Uint8Array(await blob.slice(0, 4).arrayBuffer());
  return signature[0] === 0x50 &&
    signature[1] === 0x4b &&
    ((signature[2] === 0x03 && signature[3] === 0x04) ||
      (signature[2] === 0x05 && signature[3] === 0x06) ||
      (signature[2] === 0x07 && signature[3] === 0x08));
}

async function identifyZip(blob, options) {
  const catalog = options.catalog || ROM_CATALOG;
  const sizes = catalog.map((rom) => rom.size);
  const minimumSize = Math.min(...sizes);
  const maximumSize = Math.max(...sizes);
  const reader = new ZipReader(new BlobReader(blob));

  try {
    const entries = await reader.getEntries();
    if (entries.length > MAX_ZIP_ENTRIES) {
      throw new Error("That ZIP contains too many entries.");
    }

    const candidates = entries.filter((entry) =>
      !entry.directory &&
      !entry.encrypted &&
      entry.uncompressedSize >= minimumSize &&
      entry.uncompressedSize <= Math.max(maximumSize, 64 * MIB));

    for (const entry of candidates) {
      let bytes;
      try {
        bytes = await entry.getData(new Uint8ArrayWriter());
      } catch {
        continue;
      }
      options.onStatus?.("hashing");
      const rom = await identifyRomBytes(bytes, options);
      if (rom) return rom;
    }
    return null;
  } finally {
    await reader.close();
  }
}

export async function identifyRomFile(file, options = {}) {
  if (!file || typeof file.arrayBuffer !== "function") {
    throw new Error("Choose a ROM file first.");
  }
  if (file.size > MAX_INPUT_SIZE) {
    throw new Error("That file is too large to be a supported Smash 64 ROM.");
  }

  options.onStatus?.("reading");
  let rom;
  if (await isZip(file)) {
    options.onStatus?.("extracting");
    rom = await identifyZip(file, options);
  } else {
    const bytes = new Uint8Array(await file.arrayBuffer());
    options.onStatus?.("hashing");
    rom = await identifyRomBytes(bytes, options);
  }

  if (!rom) {
    throw new Error("That file does not contain a recognized Super Smash Bros. 64 ROM.");
  }
  return rom;
}
