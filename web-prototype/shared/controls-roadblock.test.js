import assert from "node:assert/strict";
import test from "node:test";
import {
  completeControlsRoadblock,
  controlsRoadblockRequired,
  launchGate,
  postRomUploadGate,
  requireControlsRoadblock,
} from "../visual/controls-roadblock.js";

function memoryStorage() {
  const values = new Map();
  return {
    getItem(key) { return values.get(key) ?? null; },
    removeItem(key) { values.delete(key); },
    setItem(key, value) { values.set(key, value); },
  };
}

test("a create-flow ROM requires controls until the roadblock is completed", () => {
  const storage = memoryStorage();

  assert.equal(controlsRoadblockRequired(storage), false);
  requireControlsRoadblock(storage);
  assert.equal(controlsRoadblockRequired(storage), true);
  completeControlsRoadblock(storage);
  assert.equal(controlsRoadblockRequired(storage), false);
});

test("launch gating orders ROM, required controls, then the game", () => {
  assert.equal(launchGate({ romVerified: false, controlsRequired: true }), "rom");
  assert.equal(launchGate({ romVerified: true, controlsRequired: true }), "controls");
  assert.equal(launchGate({ romVerified: true, controlsRequired: false }), "game");
});

test("a play upload always proceeds through controls", () => {
  assert.equal(postRomUploadGate({ create: false }), "controls");
});

test("a create-first upload opens the creator before controls", () => {
  const storage = memoryStorage();

  assert.equal(postRomUploadGate({ create: true }), "create");
  requireControlsRoadblock(storage);
  assert.equal(launchGate({
    romVerified: true,
    controlsRequired: controlsRoadblockRequired(storage),
  }), "controls");
});
