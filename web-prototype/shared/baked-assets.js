import path from "node:path";

export const BAKED_ASSET_SCHEMA_VERSION = 1;

export const BAKED_ASSET_KINDS = Object.freeze([
  "bundle",
  "metadata",
  "portrait",
  "portraitTile",
  "portraitMedium",
  "ui",
  "announcer",
]);

const SHA256_PATTERN = /^[a-f0-9]{64}$/;

export function bakedAssetFiles(slug) {
  if (!/^[a-z0-9]+$/.test(slug || "")) throw new Error(`Invalid baked fighter slug '${slug}'`);
  const uiRoot = `play/ui/${slug}`;
  return Object.freeze({
    bundle: `play/${slug}.osb6`,
    metadata: `${uiRoot}/character.json`,
    portrait: `${uiRoot}/portrait_raw.png`,
    portraitTile: `${uiRoot}/portrait_tile.png`,
    portraitMedium: `${uiRoot}/portrait_medium.png`,
    ui: `${uiRoot}/${slug}.osbui`,
    announcer: `${uiRoot}/announcer.wav`,
  });
}

export function bakedAssetObjectKey(filePath, sha256) {
  if (!SHA256_PATTERN.test(sha256 || "")) throw new Error(`Invalid baked asset digest '${sha256}'`);
  return `baked/v1/objects/${sha256}/${path.posix.basename(filePath)}`;
}

export function validateBakedAssetManifest(manifest, expectedSlugs = null) {
  if (!manifest || manifest.schemaVersion !== BAKED_ASSET_SCHEMA_VERSION) {
    throw new Error(`Unsupported baked asset manifest schema '${manifest?.schemaVersion}'`);
  }
  if (!Array.isArray(manifest.characters)) throw new Error("Baked asset manifest needs characters");

  const seen = new Set();
  for (const character of manifest.characters) {
    const files = bakedAssetFiles(character?.slug);
    if (seen.has(character.slug)) throw new Error(`Duplicate baked asset fighter '${character.slug}'`);
    seen.add(character.slug);
    if (!character.assets || typeof character.assets !== "object") {
      throw new Error(`Missing baked assets for '${character.slug}'`);
    }
    for (const kind of BAKED_ASSET_KINDS) {
      const asset = character.assets[kind];
      if (!asset || !SHA256_PATTERN.test(asset.sha256 || "") || !Number.isSafeInteger(asset.size) || asset.size < 0) {
        throw new Error(`Invalid ${kind} asset for '${character.slug}'`);
      }
      bakedAssetObjectKey(files[kind], asset.sha256);
    }
  }

  if (expectedSlugs) {
    const actual = manifest.characters.map(({ slug }) => slug);
    if (actual.length !== expectedSlugs.length || actual.some((slug, index) => slug !== expectedSlugs[index])) {
      throw new Error("Baked asset manifest does not match config/characters.json");
    }
  }
  return manifest;
}
