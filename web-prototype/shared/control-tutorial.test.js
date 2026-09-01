import assert from "node:assert/strict";
import test from "node:test";
import {
  clearControllerTutorialCompletion,
  readControllerTutorialCompletion,
  saveControllerTutorialCompletion,
  shouldRequireControllerTutorial,
} from "../visual/control-tutorial.js";

function memoryStorage() {
  const values = new Map();
  return {
    getItem: (key) => values.get(key) ?? null,
    removeItem: (key) => values.delete(key),
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

test("controller tutorial completion can be reset for debug verification", () => {
  const storage = memoryStorage();
  saveControllerTutorialCompletion(storage);
  clearControllerTutorialCompletion(storage);
  assert.equal(readControllerTutorialCompletion(storage), false);
});
