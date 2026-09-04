import path from "node:path";

// Schema 2 adds `variants` (OSB6 target names) and `metadata` (the fields the
// roster reads from play/ui/<slug>/character.json) to every character, so a
// production API can build the whole baked roster from this manifest alone
// and never needs the fighter files on its own disk.
export const BAKED_ASSET_SCHEMA_VERSION = 2;

export const BAKED_ASSET_KINDS = Object.freeze([
  "bundle",
  "metadata",
  "portrait",
  "portraitTile",
  "portraitMedium",
  "ui",
  "announcer",
]);

// Objects are content addressed, so every URL is immutable by construction.
export const BAKED_ASSET_CACHE_CONTROL = "public, max-age=31536000, immutable";

const SHA256_PATTERN = /^[a-f0-9]{64}$/;
const FIGHTER_PATTERN = /^[a-z]+$/;

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

// GCS never compresses on the fly, so bundles are stored gzip-encoded and
// served as-is to browsers (which decode transparently). PNG and WAV gain
// nothing (a 115 KB announcer clip shrinks 8%), while an OSB6 halves.
export function bakedAssetContentEncoding(filePath) {
  return /\.(osb6|osbui|osb|json)$/i.test(filePath) ? "gzip" : null;
}

export function bakedAssetObjectKey(filePath, sha256) {
  if (!SHA256_PATTERN.test(sha256 || "")) throw new Error(`Invalid baked asset digest '${sha256}'`);
  return `baked/v1/objects/${sha256}/${path.posix.basename(filePath)}`;
}

export function bakedAssetUrl(assetBaseUrl, filePath, sha256) {
  const base = String(assetBaseUrl || "").replace(/\/+$/, "");
  if (!/^https?:\/\//.test(base)) throw new Error(`Invalid baked asset base URL '${assetBaseUrl}'`);
  return `${base}/${bakedAssetObjectKey(filePath, sha256).split("/").map(encodeURIComponent).join("/")}`;
}

// The subset of play/ui/<slug>/character.json the roster consumes.
export function bakedCharacterMetadata(source) {
  const metadata = source && typeof source === "object" ? source : {};
  const text = (value) => (typeof value === "string" && value.trim() ? value.trim() : null);
  const preferred = Array.isArray(metadata.preferred_bases)
    ? metadata.preferred_bases.filter((base) => FIGHTER_PATTERN.test(base || ""))
    : null;
  return {
    display: text(metadata.display),
    nameFull: text(metadata.name_full),
    short: text(metadata.short),
    base: FIGHTER_PATTERN.test(metadata.base || "") ? metadata.base : null,
    preferredBases: preferred && preferred.length ? preferred : null,
  };
}

export function validateBakedAssetManifest(manifest, expectedSlugs = null) {
  if (!manifest || manifest.schemaVersion !== BAKED_ASSET_SCHEMA_VERSION) {
    throw new Error(
      `Unsupported baked asset manifest schema '${manifest?.schemaVersion}' ` +
      `(expected ${BAKED_ASSET_SCHEMA_VERSION}; run pnpm assets:publish)`,
    );
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
    if (!Array.isArray(character.variants) || !character.variants.every((name) => FIGHTER_PATTERN.test(name))) {
      throw new Error(`Invalid variants for '${character.slug}'`);
    }
    if (!character.metadata || typeof character.metadata !== "object") {
      throw new Error(`Missing metadata for '${character.slug}'`);
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
