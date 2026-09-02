// rom-store.js — hand the validated ROM to the engine through IndexedDB.
//
// The engine iframe (same origin) reads this database and builds
// BattleShip.o2r from the ROM bytes in the browser, so no ROM-derived data
// ever leaves the player's machine. Schema is mirrored by
// BattleShip/web/rom-extract.js — keep the two in sync:
//   db 'opensmash-rom' v1
//     roms      key sha1            { sha1, size, name, bytes: ArrayBuffer, storedAt }
//     archives  key `${recipe}:${sha1}` { key, recipe, sha1, bytes: ArrayBuffer, builtAt, ms }
//     meta      key 'current'       { key: 'current', sha1 }

const DB_NAME = "opensmash-rom";
const DB_VERSION = 1;

function openDb(indexedDBImpl = globalThis.indexedDB) {
  if (!indexedDBImpl) return Promise.reject(new Error("IndexedDB unavailable"));
  return new Promise((resolve, reject) => {
    const request = indexedDBImpl.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains("roms")) db.createObjectStore("roms", { keyPath: "sha1" });
      if (!db.objectStoreNames.contains("archives")) db.createObjectStore("archives", { keyPath: "key" });
      if (!db.objectStoreNames.contains("meta")) db.createObjectStore("meta", { keyPath: "key" });
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error || new Error("IndexedDB unavailable"));
    request.onblocked = () => reject(new Error("IndexedDB upgrade blocked"));
  });
}

function transact(db, stores, mode, work) {
  return new Promise((resolve, reject) => {
    const tx = db.transaction(stores, mode);
    let result;
    tx.oncomplete = () => resolve(result);
    tx.onerror = () => reject(tx.error);
    tx.onabort = () => reject(tx.error || new Error("IndexedDB transaction aborted"));
    result = work(tx);
  });
}

/**
 * Ask the browser not to evict our origin's storage under pressure. Safari in
 * particular clears IndexedDB for sites not visited in seven days unless the
 * origin is persisted (or installed); Chromium grants this silently for
 * engaged sites. Best effort: a refusal just leaves eviction policy as it was.
 * Resolves to true when the origin is (now) persisted.
 */
export async function requestPersistentStorage(storageManager = globalThis.navigator?.storage) {
  try {
    if (!storageManager?.persist) return false;
    if (storageManager.persisted && (await storageManager.persisted())) return true;
    return Boolean(await storageManager.persist());
  } catch {
    return false;
  }
}

/**
 * Store the identified ROM so the engine can extract its assets locally.
 * `rom` is the result of identifyRomFile: { sha1, size, name, bytes }.
 */
export async function storeRom(rom, indexedDBImpl) {
  if (!rom?.sha1 || !rom.bytes) throw new Error("ROM bytes are required to store the ROM.");
  // Ask before writing so the bytes land in a persisted bucket from the start.
  requestPersistentStorage().then((persisted) => {
    if (!persisted) console.info("[rom] storage persistence not granted; the browser may evict the ROM when idle.");
  });
  const bytes = rom.bytes instanceof ArrayBuffer
    ? rom.bytes
    : rom.bytes.buffer.slice(rom.bytes.byteOffset, rom.bytes.byteOffset + rom.bytes.byteLength);
  const db = await openDb(indexedDBImpl);
  try {
    await transact(db, ["roms", "meta"], "readwrite", (tx) => {
      tx.objectStore("roms").put({
        sha1: rom.sha1,
        size: rom.size,
        name: rom.name || null,
        bytes,
        storedAt: Date.now(),
      });
      tx.objectStore("meta").put({ key: "current", sha1: rom.sha1 });
    });
  } finally {
    db.close();
  }
}

function idbGet(db, store, key) {
  return new Promise((resolve, reject) => {
    const request = db.transaction(store, "readonly").objectStore(store).get(key);
    request.onsuccess = () => resolve(request.result || null);
    request.onerror = () => reject(request.error);
  });
}

/** Which ROM (by SHA-1) the engine will use, or null when none is stored. */
export async function currentRomSha1(indexedDBImpl) {
  const db = await openDb(indexedDBImpl);
  try {
    const current = await idbGet(db, "meta", "current");
    if (!current?.sha1) return null;
    const rom = await idbGet(db, "roms", current.sha1);
    return rom?.bytes ? current.sha1 : null;
  } finally {
    db.close();
  }
}

/**
 * The stored ROM ({ sha1, size, name, bytes }) or null. Used by the handoff
 * host to stream its copy to another device; the bytes never leave the
 * player's own machines.
 */
export async function loadStoredRom(indexedDBImpl) {
  const db = await openDb(indexedDBImpl);
  try {
    const current = await idbGet(db, "meta", "current");
    if (!current?.sha1) return null;
    const rom = await idbGet(db, "roms", current.sha1);
    return rom?.bytes ? rom : null;
  } finally {
    db.close();
  }
}

/**
 * True when the engine can build its assets in this browser. A valid session
 * cookie is not enough on its own any more: the ROM bytes must be here too
 * (they vanish when site data is cleared or in a fresh private window).
 */
export async function hasStoredRom(indexedDBImpl) {
  try {
    return Boolean(await currentRomSha1(indexedDBImpl));
  } catch {
    return false;
  }
}

/**
 * Build the engine's asset archive now, in a worker, so the engine finds it
 * cached when it launches. Best started right after storeRom(): the launch
 * animation hides the ~4 s of work, and doing it before the engine's own
 * wasm compile avoids CPU contention that otherwise stretches it to 10–30 s.
 * Resolves to the ensureArchive result, or null if the package ships its own.
 */
export async function prewarmEngineArchive({ engineBase = "/engine/", onStatus } = {}) {
  const manifest = await (await fetch(`${engineBase}manifest.json`, { cache: "no-cache" })).json();
  // Development packages can still include a prebuilt archive. In that case
  // the engine stages it directly from the manifest and deliberately does not
  // ship the optional browser extractor. Treating that missing module as an
  // extraction failure invalidates an otherwise playable ROM session and
  // prompts the player to choose the same ROM again.
  if (manifest.files?.some((file) => file.path === "/BattleShip.o2r")) return null;
  const sample = manifest.files?.[0]?.url || "";
  const version = new URL(sample, `${location.origin}${engineBase}`).searchParams.get("v");
  const moduleUrl = `${engineBase}rom-extract.js${version ? `?v=${encodeURIComponent(version)}` : ""}`;
  const { prewarmArchive } = await import(/* @vite-ignore */ moduleUrl);
  return prewarmArchive({ setStatus: onStatus });
}

/** Forget the stored ROM and every archive built from it. */
export async function clearRomStore(indexedDBImpl) {
  const db = await openDb(indexedDBImpl);
  try {
    await transact(db, ["roms", "archives", "meta"], "readwrite", (tx) => {
      tx.objectStore("roms").clear();
      tx.objectStore("archives").clear();
      tx.objectStore("meta").clear();
    });
  } finally {
    db.close();
  }
}
