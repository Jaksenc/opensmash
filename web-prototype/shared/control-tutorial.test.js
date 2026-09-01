import assert from "node:assert/strict";
import test from "node:test";
import {
  readControllerTutorialCompletion,
  saveControllerTutorialCompletion,
  shouldRequireControllerTutorial,
} from "../visual/control-tutorial.js";

function memoryStorage() {
  const values = new Map();
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
  };
}

test("desktop controller tutorial is mandatory only until it is completed", () => {
  assert.equal(shouldRequireControllerTutorial({ completed: false, mobileControls: false }), true);
  assert.equal(shouldRequireControllerTutorial({ completed: true, mobileControls: false }), false);
});

test("mobile controls bypass the controller tutorial without completing it", () => {
  const storage = memoryStorage();
  assert.equal(shouldRequireControllerTutorial({
    completed: readControllerTutorialCompletion(storage),
    mobileControls: true,
  }), false);
  assert.equal(readControllerTutorialCompletion(storage), false);
});

test("controller tutorial completion persists in storage", () => {
  const storage = memoryStorage();
  saveControllerTutorialCompletion(storage);
  assert.equal(readControllerTutorialCompletion(storage), true);
});
