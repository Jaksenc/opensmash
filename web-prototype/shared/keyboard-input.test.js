import assert from "node:assert/strict";
import test from "node:test";
import { hasShortcutModifier } from "./keyboard-input.js";

test("command, control, and alt keyboard shortcuts are not controller input", () => {
  assert.equal(hasShortcutModifier({ metaKey: true }), true);
  assert.equal(hasShortcutModifier({ ctrlKey: true }), true);
  assert.equal(hasShortcutModifier({ altKey: true }), true);
});

test("plain and shift-only key presses remain eligible for controller input", () => {
  assert.equal(hasShortcutModifier({}), false);
  assert.equal(hasShortcutModifier({ shiftKey: true }), false);
});
