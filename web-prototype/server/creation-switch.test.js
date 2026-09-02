import assert from "node:assert/strict";
import test from "node:test";
import { creationEnabled } from "./creation-switch.js";

test("creation stays on when the switch is unset or affirmative", () => {
  assert.equal(creationEnabled({}), true);
  assert.equal(creationEnabled({ CREATION_ENABLED: "" }), true);
  assert.equal(creationEnabled({ CREATION_ENABLED: "1" }), true);
  assert.equal(creationEnabled({ CREATION_ENABLED: "true" }), true);
  // An unrecognised value must not close the lab by accident.
  assert.equal(creationEnabled({ CREATION_ENABLED: "maybe" }), true);
});

test("creation is off for the documented negative values", () => {
  for (const value of ["0", "false", "off", "no", "disabled", " OFF ", "False"]) {
    assert.equal(creationEnabled({ CREATION_ENABLED: value }), false, value);
  }
});
