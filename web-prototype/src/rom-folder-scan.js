// rom-folder-scan.js — let a desktop Chromium user point at a folder (their
// emulator's ROM directory, Downloads, an external drive) and find the Smash 64
// image for them instead of hunting for one file.
//
// Uses the File System Access API (window.showDirectoryPicker), which only
// exists on desktop Chromium; callers should hide the affordance elsewhere
// (see isFolderScanSupported). Everything stays local: files are read in this
// tab, and only the winning File is handed back to the normal upload path.

import { hasN64Header, identifyRomFile } from "./rom-validation.js";
import { ROM_CATALOG } from "../shared/rom-catalog.js";
import { SCAN_LIMITS, isRomScanCandidate, rankRomCandidates, shouldDescend } from "../shared/rom-scan-filter.js";

const HEADER_PROBE_BYTES = 4096;

export function isFolderScanSupported() {
  return typeof window !== "undefined" && typeof window.showDirectoryPicker === "function";
}

class ScanCancelled extends Error {
  constructor() {
    super("Folder scan cancelled.");
    this.name = "ScanCancelled";
  }
}

/**
 * Walk `directory` breadth-first collecting plausible ROM files.
 * Stops at the scan limits so a huge tree cannot hang the tab.
 */
export async function collectRomCandidates(directory, { onProgress = () => {}, signal, limits = SCAN_LIMITS, now = Date.now } = {}) {
  const romSizes = ROM_CATALOG.map((rom) => rom.size);
  const started = now();
  const queue = [{ handle: directory, depth: 0, path: directory.name || "" }];
  const candidates = [];
  let entries = 0;
  let directories = 0;
  let truncated = false;

  while (queue.length && !truncated) {
    if (signal?.aborted) throw new ScanCancelled();
    const { handle, depth, path } = queue.shift();
    directories += 1;
    let iterator;
    try {
      iterator = handle.values();
    } catch {
      continue;
    }
    for await (const entry of iterator) {
      if (signal?.aborted) throw new ScanCancelled();
      entries += 1;
      if (entries > limits.maxEntries || now() - started > limits.timeBudgetMs) { truncated = true; break; }
      if (entry.kind === "directory") {
        if (shouldDescend(entry.name, depth + 1, limits)) queue.push({ handle: entry, depth: depth + 1, path: `${path}/${entry.name}` });
        continue;
      }
      if (entry.kind !== "file") continue;
      let file;
      try {
        file = await entry.getFile();
      } catch {
        continue;
      }
      if (isRomScanCandidate({ name: file.name, size: file.size }, romSizes)) {
        candidates.push({ file, name: file.name, size: file.size, path: `${path}/${file.name}` });
        if (candidates.length >= limits.maxCandidates) { truncated = true; break; }
      }
      if (entries % 200 === 0) onProgress({ phase: "walking", entries, directories, candidates: candidates.length, path });
    }
  }
  onProgress({ phase: "walking", entries, directories, candidates: candidates.length, truncated });
  return { candidates: rankRomCandidates(candidates, romSizes), entries, directories, truncated };
}

async function looksLikeRom(file) {
  if (/\.zip$/i.test(file.name)) return true;
  const head = new Uint8Array(await file.slice(0, HEADER_PROBE_BYTES).arrayBuffer());
  return hasN64Header(head);
}

/**
 * Prompt for a folder, then return the first File that identifies as a
 * supported ROM. Resolves null when the user cancels the picker. Throws with a
 * helpful message when the folder holds nothing usable.
 */
export async function scanFolderForRom({ onProgress = () => {}, signal, identify = identifyRomFile, pickDirectory } = {}) {
  const pick = pickDirectory || (() => window.showDirectoryPicker({ mode: "read" }));
  let directory;
  try {
    directory = await pick();
  } catch (error) {
    if (error?.name === "AbortError") return null;
    throw error;
  }
  if (!directory) return null;

  onProgress({ phase: "walking", entries: 0, directories: 0, candidates: 0 });
  const { candidates, entries, truncated } = await collectRomCandidates(directory, { onProgress, signal });
  if (!candidates.length) {
    throw new Error(
      `No ROM-sized files found in “${directory.name}” (${entries.toLocaleString()} files checked${truncated ? ", stopped early" : ""}). ` +
      "Try the folder your emulator keeps its ROMs in.",
    );
  }

  let regionError = null;
  for (let index = 0; index < candidates.length; index += 1) {
    if (signal?.aborted) throw new ScanCancelled();
    const candidate = candidates[index];
    onProgress({ phase: "checking", index: index + 1, total: candidates.length, name: candidate.name });
    try {
      if (!(await looksLikeRom(candidate.file))) continue;
      const rom = await identify(candidate.file, {});
      if (rom) return candidate.file;
    } catch (error) {
      // "That is the Japan release…" is worth surfacing if nothing better turns up.
      if (/release/.test(error?.message || "")) regionError = error;
    }
  }
  if (regionError) throw regionError;
  throw new Error(
    `Checked ${candidates.length} likely file${candidates.length === 1 ? "" : "s"} in “${directory.name}” but none is the USA Super Smash Bros. 64 ROM.`,
  );
}
