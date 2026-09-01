export const CONTROLS_ROADBLOCK_KEY = "opensmash.controls-roadblock.v1";

function availableStorage(storage) {
  if (storage) return storage;
  return typeof localStorage === "undefined" ? null : localStorage;
}

export function controlsRoadblockRequired(storage) {
  try {
    return availableStorage(storage)?.getItem(CONTROLS_ROADBLOCK_KEY) === "required";
  } catch {
    return false;
  }
}

export function requireControlsRoadblock(storage) {
  try {
    availableStorage(storage)?.setItem(CONTROLS_ROADBLOCK_KEY, "required");
  } catch {
    // The regular ROM-to-controller flow still protects launches when storage is unavailable.
  }
}

export function completeControlsRoadblock(storage) {
  try {
    availableStorage(storage)?.removeItem(CONTROLS_ROADBLOCK_KEY);
  } catch {
    // Completion still applies to the current in-memory launch.
  }
}

export function launchGate({ romVerified, controlsRequired }) {
  if (!romVerified) return "rom";
  if (controlsRequired) return "controls";
  return "game";
}

export function postRomUploadGate({ create }) {
  return create ? "create" : "controls";
}
