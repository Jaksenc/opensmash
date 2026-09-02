// rom-scan-filter.js — decide which files in a user-picked folder are worth
// hashing when looking for the Smash 64 ROM. Pure so it can be tested in Node;
// the directory walk itself (File System Access API) is in
// src/rom-folder-scan.js.
//
// The goal is to touch as few files as possible: a game folder can hold tens
// of thousands of files, and hashing each 16 MiB candidate costs real time on
// a laptop. Size is the strongest signal — an N64 image is 16 MiB (possibly a
// few KiB more with a copier header), a zipped one is under that.

const MIB = 1024 * 1024;

export const ROM_EXTENSIONS = Object.freeze([".z64", ".n64", ".v64", ".rom", ".bin", ".u64"]);
export const ARCHIVE_EXTENSIONS = Object.freeze([".zip"]);
// Directories that are never worth descending into.
export const SKIPPED_DIRECTORY_NAMES = Object.freeze(new Set([
  "node_modules", ".git", "Library", "Applications", "Windows", "Program Files", "Program Files (x86)",
  "AppData", "System", "$RECYCLE.BIN", "System Volume Information", "Trash", ".Trash",
]));

export const SCAN_LIMITS = Object.freeze({
  maxDepth: 8,
  maxEntries: 40_000,
  maxCandidates: 40,
  timeBudgetMs: 90_000,
});

function extensionOf(name) {
  const dot = name.lastIndexOf(".");
  return dot === -1 ? "" : name.slice(dot).toLowerCase();
}

export function shouldDescend(name, depth, limits = SCAN_LIMITS) {
  if (depth >= limits.maxDepth) return false;
  if (!name || name.startsWith(".")) return false;
  return !SKIPPED_DIRECTORY_NAMES.has(name);
}

/**
 * Is this file plausibly a Smash 64 ROM (or a zip holding one)?
 * `romSizes` are the canonical catalog sizes; a raw dump may carry up to a
 * 4 KiB copier header on top.
 */
export function isRomScanCandidate({ name, size }, romSizes = [16 * MIB]) {
  if (!name || !Number.isFinite(size) || size <= 0) return false;
  const extension = extensionOf(name);
  const minRom = Math.min(...romSizes);
  const maxRom = Math.max(...romSizes);

  if (ARCHIVE_EXTENSIONS.includes(extension)) {
    // Compressed 16 MiB N64 images land around 7–12 MiB; anything under 1 MiB
    // cannot hold one and anything over 64 MiB is not a single-game zip.
    return size >= 1 * MIB && size <= 64 * MIB;
  }
  const sizeLooksLikeRom = size >= minRom && size <= maxRom + 4096;
  if (ROM_EXTENSIONS.includes(extension)) {
    // A known ROM extension buys a wider tolerance (over-dumps to 32/64 MiB).
    return size >= minRom && size <= 64 * MIB;
  }
  // Unknown or missing extension: only an exact-ish size match is worth reading.
  return sizeLooksLikeRom;
}

/**
 * Order candidates so the likely hit is hashed first: names that mention the
 * game, then exact catalog sizes, then known ROM extensions, then the rest.
 */
export function rankRomCandidates(candidates, romSizes = [16 * MIB]) {
  const exact = new Set(romSizes);
  const score = (candidate) => {
    const name = String(candidate.name || "").toLowerCase();
    let value = 0;
    if (/smash|ssb|dairantou|nale/.test(name)) value -= 100;
    if (exact.has(candidate.size)) value -= 10;
    if (ROM_EXTENSIONS.includes(extensionOf(name))) value -= 5;
    if (ARCHIVE_EXTENSIONS.includes(extensionOf(name))) value -= 1;
    return value;
  };
  return [...candidates].sort((left, right) => score(left) - score(right) || left.name.localeCompare(right.name));
}
