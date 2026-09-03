// The CRT overlay (visual/crt-viewport.js) owns its own settings blob in
// localStorage and reads it at boot. Settings only needs the on/off bit, so
// route through the live runtime when it exists (it persists the change) and
// fall back to the same storage key when it does not (no WebGL, or the
// runtime has not been imported yet on this page).
const STORAGE_KEY = "opensmash.crt-tuning.v1";

function readStored() {
  try {
    const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) || "null");
    return stored && typeof stored === "object" ? stored : {};
  } catch {
    return {};
  }
}

export function readCrtEnabled() {
  const live = window.__crtViewport;
  if (live) return Boolean(live.enabled);
  const stored = readStored();
  return typeof stored.enabled === "boolean" ? stored.enabled : true;
}

export function writeCrtEnabled(enabled) {
  const live = window.__crtViewport;
  if (live) {
    live.enabled = enabled;
    return;
  }
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ ...readStored(), enabled: Boolean(enabled) }));
  } catch {
    // Storage unavailable: nothing to persist, the overlay stays as-is.
  }
}
