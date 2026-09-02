import assert from "node:assert/strict";
import test from "node:test";
import {
  BAKED_ASSET_KINDS,
  bakedAssetFiles,
  bakedAssetObjectKey,
  validateBakedAssetManifest,
} from "./baked-assets.js";

const digest = "a".repeat(64);

function manifest(slug = "testfighter") {
  return {
    schemaVersion: 1,
    characters: [{
      slug,
      assets: Object.fromEntries(BAKED_ASSET_KINDS.map((kind) => [kind, { sha256: digest, size: 42 }])),
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
});

test("baked asset paths reject unsafe slugs and digests", () => {
  assert.throws(() => bakedAssetFiles("../fighter"), /Invalid baked fighter slug/);
  assert.throws(() => bakedAssetObjectKey("play/fighter.osb6", "bad"), /Invalid baked asset digest/);
});
