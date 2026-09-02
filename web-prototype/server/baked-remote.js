// Production baked roster: built from config/baked-assets.json alone.
//
// The manifest pins every runtime file of every baked fighter by SHA-256, and
// the objects live in the public bucket under keys that contain that digest.
// So the API never needs the ~3 GB of fighter files on its own disk: it
// answers the roster from the manifest and points browsers at the immutable
// object URLs (directly in /api/characters, and via a redirect for the
// engine's relative bundles/<slug>.* fetches).
import { readFile } from "node:fs/promises";
import { bakedAssetFiles, bakedAssetUrl, validateBakedAssetManifest } from "../shared/baked-assets.js";
import { assignRosterBases, bundleForBase, FIGHTERS } from "./roster.js";

// Engine bundle name suffix -> manifest asset kind.
const ENGINE_BUNDLE_KINDS = Object.freeze({ osb6: "bundle", osbui: "ui", wav: "announcer" });
// /character-assets/<slug>/<name> -> manifest asset kind.
const CHARACTER_ASSET_KINDS = Object.freeze({
  "portrait.png": "portrait",
  "portrait_tile.png": "portraitTile",
  "portrait_medium.png": "portraitMedium",
  "announcer.wav": "announcer",
});

export function engineBundleAssetKind(fileName) {
  const match = String(fileName).match(/^([a-z0-9]+)\.(osb6|osbui|wav)$/);
  return match ? { slug: match[1], kind: ENGINE_BUNDLE_KINDS[match[2]] } : null;
}

export function characterAssetKind(fileName) {
  return CHARACTER_ASSET_KINDS[fileName] || null;
}

// entries: bakedRosterEntries(config/characters.json). Returns the same
// shapes buildBakedRoster produces from a local play/ scan, plus assetUrl().
export function buildRemoteBakedRoster({ manifest, entries, assetBaseUrl }) {
  validateBakedAssetManifest(manifest, entries.map((entry) => entry.slug));
  const bySlug = new Map(manifest.characters.map((character) => [character.slug, character]));

  const roster = assignRosterBases(entries.map((entry) => {
    const { slug } = entry;
    const { variants, metadata } = bySlug.get(slug);
    const display = entry.name || metadata.display || slug;
    return {
      slug,
      display,
      nameFull: metadata.nameFull || null,
      short: entry.short || metadata.short || display.toUpperCase().replace(/[^A-Z]/g, "").slice(0, 10),
      base: entry.base ?? metadata.base ?? null,
      preferredBases: entry.preferredBases || metadata.preferredBases || undefined,
      variants: variants.filter((target) => target !== "mario").sort(),
      ui: true,
      voice: true,
    };
  }));

  function assetUrl(slug, kind) {
    const character = bySlug.get(slug);
    if (!character) return null;
    const asset = character.assets[kind];
    if (!asset) return null;
    return bakedAssetUrl(assetBaseUrl, bakedAssetFiles(slug)[kind], asset.sha256);
  }

  const characters = [];
  for (const character of roster) {
    const { slug } = character;
    const fighterName = character.base || "mario";
    const fkind = FIGHTERS.indexOf(fighterName);
    if (fkind === -1) continue;
    characters.push({
      slug,
      name: character.display,
      short: character.short,
      portrait: assetUrl(slug, "portraitTile"),
      portraitMedium: assetUrl(slug, "portraitMedium"),
      portraitFull: assetUrl(slug, "portrait"),
      announcer: assetUrl(slug, "announcer"),
      base: fighterName,
      fkind,
      bundle: bundleForBase(slug),
      variants: character.variants,
      ui: character.ui,
      voice: character.voice,
    });
  }

  return {
    entries,
    roster,
    characters,
    slugs: new Set(roster.map((character) => character.slug)),
    assetUrl,
  };
}

export async function loadRemoteBakedRoster({ manifestPath, entries, assetBaseUrl }) {
  const manifest = JSON.parse(await readFile(manifestPath, "utf8"));
  return buildRemoteBakedRoster({ manifest, entries, assetBaseUrl });
}
