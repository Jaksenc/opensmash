import assert from "node:assert/strict";
import test from "node:test";
import {
  DEFAULT_ADVANCED_OPTIONS,
  engineUrl,
  hasAdvancedOverrides,
  normalizeAdvancedOptions,
  selectDirectBattleOpponents,
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
  assert.equal(characterQuery.get("inject_ui"), null);
  assert.equal(characterQuery.get("inject_voice"), null);
  assert.match(characterQuery.get("SSB64_BOOT_BATTLE"), /^0,\d+,\d+,1,\d+,\d+$/);
  assert.equal(characterQuery.get("SSB64_CPU_LEVEL"), "3");

  const selectQuery = queryFor({ type: "select" });
  assert.match(selectQuery.get("SSB64_BOOT_BATTLE"), /^0,\d+,\d+,1,\d+,\d+$/);

  const startQuery = queryFor({ type: "start" });
  assert.match(startQuery.get("SSB64_BOOT_BATTLE"), /^0,\d+,\d+,1,\d+,\d+$/);
});

test("launches request only character extras that actually exist", () => {
  const query = queryFor({
    type: "character",
    character: { ...CHARACTER, ui: true, voiceUrl: "/character-assets/testfighter/announcer.wav" },
  });
  assert.equal(query.get("inject_ui"), "bundles/testfighter.osbui");
  assert.equal(query.get("inject_voice"), "/character-assets/testfighter/announcer.wav");
});

test("character launches mix one vanilla, one grid, and one unused owned opponent", () => {
  const grid = [
    CHARACTER,
    { ...CHARACTER, slug: "gridfighter", name: "Grid Fighter", short: "GRID", fkind: 5, bundle: "gridfighter-link.osb" },
    { ...CHARACTER, slug: "fallback", name: "Fallback", short: "FALL", fkind: 8, bundle: "fallback-kirby.osb" },
  ];
  const owned = [
    CHARACTER,
    { ...CHARACTER, slug: "myfighter", name: "My Fighter", short: "MINE", fkind: 3, bundleUrl: "/api/fighters/mine/assets/bundle" },
  ];
  const opponents = selectDirectBattleOpponents(CHARACTER, [owned[1], ...grid], owned, () => 0);
  assert.deepEqual(opponents.map((opponent) => opponent.type), ["vanilla", "character", "character"]);
  assert.equal(opponents[0].fkind, 0);
  assert.equal(opponents[1].character.slug, "gridfighter");
  assert.equal(opponents[2].character.slug, "myfighter");

  const query = queryFor(
    { type: "character", character: CHARACTER, opponents },
    { ...DEFAULT_ADVANCED_OPTIONS, stage: "0" },
  );
  assert.equal(query.get("SSB64_BOOT_BATTLE"), "0,0,0,1,5,3");
  assert.deepEqual(
    query.getAll("inject_player").map((entry) => JSON.parse(entry)),
    [
      {
        player: 2,
        slug: "gridfighter",
        fkind: 5,
        short: "GRID",
        bundleUrl: "bundles/gridfighter-link.osb",
        uiUrl: null,
        voiceUrl: null,
      },
      {
        player: 3,
        slug: "myfighter",
        fkind: 3,
        short: "MINE",
        bundleUrl: "/api/fighters/mine/assets/bundle",
        uiUrl: null,
        voiceUrl: null,
      },
    ],
  );
});

test("owned-opponent slot falls back to another unused grid fighter", () => {
  const grid = [
    CHARACTER,
    { ...CHARACTER, slug: "second", fkind: 1, bundle: "second-fox.osb" },
    { ...CHARACTER, slug: "third", fkind: 2, bundle: "third-donkey.osb" },
  ];
  const opponents = selectDirectBattleOpponents(CHARACTER, grid, [CHARACTER], () => 0);
  assert.deepEqual(
    opponents.slice(1).map((opponent) => opponent.character.slug),
    ["second", "third"],
  );
});

test("duplicate roster records never cause duplicate fighters when unique choices exist", () => {
  const second = { ...CHARACTER, slug: "second", fkind: 1, bundle: "second-fox.osb" };
  const third = { ...CHARACTER, slug: "third", fkind: 2, bundle: "third-donkey.osb" };
  const opponents = selectDirectBattleOpponents(
    CHARACTER,
    [CHARACTER, second, { ...second }, third],
    [CHARACTER, second, { ...second }],
    () => 0,
  );
  const customSlugs = opponents
    .filter((opponent) => opponent.type === "character")
    .map((opponent) => opponent.character.slug);
  assert.deepEqual(customSlugs, ["third", "second"]);
  assert.equal(new Set([CHARACTER.slug, ...customSlugs]).size, 3);
});

test("mesh and stage overrides select the matching injection variant", () => {
  const query = queryFor(
    { type: "character", character: CHARACTER },
    { characterMesh: "link", stage: "4", opponentLevel: "9", bootMode: "free-for-all" },
  );
  assert.equal(query.get("inject"), "bundles/testfighter-link.osb");
  assert.equal(query.get("fkind"), "5");
  assert.equal(query.get("base"), "testfighter:link");
  assert.match(query.get("SSB64_BOOT_BATTLE"), /^5,\d+,4,1,\d+,\d+$/);
  assert.equal(query.get("SSB64_CPU_LEVEL"), "9");
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
  assert.deepEqual(normalizeAdvancedOptions({ characterMesh: "bad", stage: "4", opponentLevel: "99", bootMode: "bad" }), {
    characterMesh: "auto",
    stage: "4",
    opponentLevel: "3",
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
