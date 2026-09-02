import assert from "node:assert/strict";
import test from "node:test";
import { BAKED_ASSET_KINDS, bakedAssetUrl } from "../shared/baked-assets.js";
import { bakedRosterEntries } from "../shared/baked-roster.js";
import { buildRemoteBakedRoster, characterAssetKind, engineBundleAssetKind } from "./baked-remote.js";

const digest = (seed) => seed.repeat(64).slice(0, 64);

function character(slug, extra = {}) {
  const assets = {};
  for (const [index, kind] of BAKED_ASSET_KINDS.entries()) {
    assets[kind] = { sha256: digest(String(index)), size: 10 + index };
  }
  return {
    slug,
    assets,
    variants: ["mario", "fox", "samus"],
    metadata: { display: null, nameFull: null, short: null, base: null, preferredBases: null },
    ...extra,
  };
}

const BASE = "https://storage.googleapis.com/bucket/";

test("roster and characters come from the manifest with immutable object URLs", () => {
  const manifest = {
    schemaVersion: 2,
    characters: [
      character("cleopatra", {
        metadata: { display: "Cleo", nameFull: "Cleopatra VII", short: "CLEO", base: "fox", preferredBases: null },
      }),
      character("lincoln"),
    ],
  };
  const entries = bakedRosterEntries(["cleopatra", { slug: "lincoln", name: "Abe Lincoln" }]);
  const baked = buildRemoteBakedRoster({ manifest, entries, assetBaseUrl: BASE });

  assert.deepEqual([...baked.slugs], ["cleopatra", "lincoln"]);
  const [cleo, abe] = baked.roster;
  assert.equal(cleo.display, "Cleo");
  assert.equal(cleo.nameFull, "Cleopatra VII");
  assert.equal(cleo.base, "fox");
  assert.deepEqual(cleo.variants, ["fox", "samus"]);
  assert.equal(abe.display, "Abe Lincoln");
  assert.equal(abe.short, "ABELINCOLN");
  assert.equal(typeof abe.base, "string", "balanced onto a base like the local scan does");

  const [cleoCard] = baked.characters;
  assert.equal(cleoCard.bundle, "cleopatra.osb6");
  assert.equal(cleoCard.fkind, 1);
  assert.equal(
    cleoCard.portrait,
    `https://storage.googleapis.com/bucket/baked/v1/objects/${digest("3")}/portrait_tile.png`,
  );
  assert.equal(cleoCard.announcer, baked.assetUrl("cleopatra", "announcer"));
  assert.match(cleoCard.portraitFull, /\/portrait_raw\.png$/);
  assert.equal(baked.assetUrl("cleopatra", "bundle"), bakedAssetUrl(BASE, "play/cleopatra.osb6", digest("0")));
  assert.equal(baked.assetUrl("nobody", "bundle"), null);
});

test("manifest must match config/characters.json and carry schema 2 fields", () => {
  const entries = bakedRosterEntries(["cleopatra"]);
  assert.throws(
    () => buildRemoteBakedRoster({ manifest: { schemaVersion: 1, characters: [] }, entries, assetBaseUrl: BASE }),
    /schema '1'/,
  );
  assert.throws(
    () => buildRemoteBakedRoster({
      manifest: { schemaVersion: 2, characters: [character("lincoln")] }, entries, assetBaseUrl: BASE,
    }),
    /does not match/,
  );
  const missingVariants = character("cleopatra");
  delete missingVariants.variants;
  assert.throws(
    () => buildRemoteBakedRoster({ manifest: { schemaVersion: 2, characters: [missingVariants] }, entries, assetBaseUrl: BASE }),
    /variants/,
  );
});

test("route file names map to manifest asset kinds", () => {
  assert.deepEqual(engineBundleAssetKind("cleopatra.osb6"), { slug: "cleopatra", kind: "bundle" });
  assert.deepEqual(engineBundleAssetKind("cleopatra.osbui"), { slug: "cleopatra", kind: "ui" });
  assert.deepEqual(engineBundleAssetKind("cleopatra.wav"), { slug: "cleopatra", kind: "announcer" });
  assert.equal(engineBundleAssetKind("cleopatra-abc.osb6"), null);
  assert.equal(engineBundleAssetKind("../x.osb6"), null);
  assert.equal(characterAssetKind("portrait.png"), "portrait");
  assert.equal(characterAssetKind("portrait_tile.png"), "portraitTile");
  assert.equal(characterAssetKind("stock.png"), null);
});
