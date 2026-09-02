import assert from "node:assert/strict";
import test from "node:test";
import {
  BAKED_ASSET_KINDS,
  bakedAssetFiles,
  bakedAssetObjectKey,
  bakedAssetUrl,
  bakedCharacterMetadata,
  validateBakedAssetManifest,
} from "./baked-assets.js";

const digest = "a".repeat(64);

function manifest(slug = "testfighter") {
  return {
    schemaVersion: 2,
    characters: [{
      slug,
      assets: Object.fromEntries(BAKED_ASSET_KINDS.map((kind) => [kind, { sha256: digest, size: 42 }])),
      variants: ["mario", "fox"],
      metadata: bakedCharacterMetadata({ display: "Test", preferred_bases: ["fox"] }),
    }],
  };
}

test("baked asset paths are deterministic and remain under play", () => {
  const files = bakedAssetFiles("testfighter");
  assert.equal(files.bundle, "play/testfighter.osb6");
  assert.equal(files.ui, "play/ui/testfighter/testfighter.osbui");
  assert.equal(
    bakedAssetObjectKey(files.bundle, digest),
    `baked/v1/objects/${digest}/testfighter.osb6`,
  );
});

test("baked manifests require every runtime asset and exact roster order", () => {
  assert.equal(validateBakedAssetManifest(manifest(), ["testfighter"]).characters.length, 1);
  const incomplete = manifest();
  delete incomplete.characters[0].assets.announcer;
  assert.throws(() => validateBakedAssetManifest(incomplete), /Invalid announcer asset/);
  assert.throws(() => validateBakedAssetManifest(manifest(), ["otherfighter"]), /does not match/);
  const legacy = manifest();
  legacy.schemaVersion = 1;
  assert.throws(() => validateBakedAssetManifest(legacy), /schema '1'/);
  const noVariants = manifest();
  noVariants.characters[0].variants = ["../x"];
  assert.throws(() => validateBakedAssetManifest(noVariants), /Invalid variants/);
});

test("baked asset URLs are content addressed and metadata keeps only roster fields", () => {
  assert.equal(
    bakedAssetUrl("https://cdn.example/", "play/testfighter.osb6", digest),
    `https://cdn.example/baked/v1/objects/${digest}/testfighter.osb6`,
  );
  assert.throws(() => bakedAssetUrl("", "play/testfighter.osb6", digest), /Invalid baked asset base URL/);
  assert.deepEqual(
    bakedCharacterMetadata({ display: " Cleo ", name_full: "Cleopatra VII", base: "fox", description: "secret", preferred_bases: ["kirby", "../x"] }),
    { display: "Cleo", nameFull: "Cleopatra VII", short: null, base: "fox", preferredBases: ["kirby"] },
  );
  assert.deepEqual(bakedCharacterMetadata(null), { display: null, nameFull: null, short: null, base: null, preferredBases: null });
});

test("baked asset paths reject unsafe slugs and digests", () => {
  assert.throws(() => bakedAssetFiles("../fighter"), /Invalid baked fighter slug/);
  assert.throws(() => bakedAssetObjectKey("play/fighter.osb6", "bad"), /Invalid baked asset digest/);
});
