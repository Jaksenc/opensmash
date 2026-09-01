import assert from "node:assert/strict";
import test from "node:test";
import {
  DEFAULT_ADVANCED_OPTIONS,
  engineUrl,
  hasAdvancedOverrides,
  normalizeAdvancedOptions,
} from "../src/launch-options.js";

const CHARACTER = {
  slug: "testfighter",
  name: "Test Fighter",
  fkind: 0,
  base: "mario",
  bundle: "testfighter.osb",
  variants: {
    link: "bundles/testfighter-link.osb",
  },
};

function queryFor(action, options = DEFAULT_ADVANCED_OPTIONS) {
  return new URL(engineUrl(action, options, 123), "https://example.test").searchParams;
}

test("default launches start a free-for-all", () => {
  const characterQuery = queryFor({ type: "character", character: CHARACTER });
  assert.equal(characterQuery.get("inject"), "bundles/testfighter.osb");
  assert.match(characterQuery.get("SSB64_BOOT_BATTLE"), /^0,\d+,\d+,1,\d+,\d+$/);

  const selectQuery = queryFor({ type: "select" });
  assert.match(selectQuery.get("SSB64_BOOT_BATTLE"), /^0,\d+,\d+,1,\d+,\d+$/);

  const startQuery = queryFor({ type: "start" });
  assert.match(startQuery.get("SSB64_BOOT_BATTLE"), /^0,\d+,\d+,1,\d+,\d+$/);
});

test("mesh and stage overrides select the matching injection variant", () => {
  const query = queryFor(
    { type: "character", character: CHARACTER },
    { characterMesh: "link", stage: "4", bootMode: "free-for-all" },
  );
  assert.equal(query.get("inject"), "bundles/testfighter-link.osb");
  assert.equal(query.get("fkind"), "5");
  assert.equal(query.get("base"), "testfighter:link");
  assert.match(query.get("SSB64_BOOT_BATTLE"), /^5,\d+,4,1,\d+,\d+$/);
});

test("boot overrides address the distinct engine scenes", () => {
  const vsMenu = queryFor(
    { type: "character", character: CHARACTER },
    { characterMesh: "auto", stage: "6", bootMode: "vs-menu" },
  );
  assert.equal(vsMenu.get("SSB64_START_SCENE"), "9");
  assert.equal(vsMenu.get("SSB64_BOOT_BATTLE"), "0,8,6");

  const vsSelect = queryFor(
    { type: "select" },
    { characterMesh: "auto", stage: "3", bootMode: "vs-character-select" },
  );
  assert.equal(vsSelect.get("SSB64_START_SCENE"), "16");
  assert.equal(vsSelect.get("SSB64_BOOT_BATTLE"), "-1,8,3");

  const onePlayerSelect = queryFor(
    { type: "select" },
    { characterMesh: "auto", stage: "3", bootMode: "one-player-character-select" },
  );
  assert.equal(onePlayerSelect.get("SSB64_START_SCENE"), "17");
  assert.equal(onePlayerSelect.get("SSB64_BOOT_BATTLE"), null);
});

test("stored settings are allow-listed and report active overrides", () => {
  assert.deepEqual(normalizeAdvancedOptions({ characterMesh: "bad", stage: "4", bootMode: "bad" }), {
    characterMesh: "auto",
    stage: "4",
    bootMode: "free-for-all",
  });
  assert.equal(hasAdvancedOverrides(DEFAULT_ADVANCED_OPTIONS), false);
  assert.equal(hasAdvancedOverrides({ ...DEFAULT_ADVANCED_OPTIONS, stage: "4" }), true);
});

test("a missing forced mesh variant produces a useful error", () => {
  assert.throws(
    () => queryFor(
      { type: "character", character: { ...CHARACTER, bundleUrl: "https://objects.test/testfighter.osb" } },
      { characterMesh: "fox", stage: "random", bootMode: "free-for-all" },
    ),
    /does not have a Fox mesh variant/,
  );
});
