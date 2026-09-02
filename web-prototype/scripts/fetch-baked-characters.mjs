#!/usr/bin/env node
import { createHash } from "node:crypto";
import { createReadStream, createWriteStream } from "node:fs";
import { mkdir, readFile, rename, rm, stat } from "node:fs/promises";
import path from "node:path";
import { Readable } from "node:stream";
import { pipeline } from "node:stream/promises";
import { fileURLToPath } from "node:url";
import { bakedRosterSlugs } from "../shared/baked-roster.js";
import {
  BAKED_ASSET_KINDS,
  bakedAssetFiles,
  bakedAssetObjectKey,
  validateBakedAssetManifest,
} from "../shared/baked-assets.js";

const APP_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const DEFAULT_MANIFEST = path.join(APP_ROOT, "config", "baked-assets.json");
const DEFAULT_OUTPUT = path.join(APP_ROOT, ".baked-characters");
const ROSTER_CONFIG = path.join(APP_ROOT, "config", "characters.json");

function option(name, fallback = null) {
  const index = process.argv.indexOf(name);
  return index === -1 ? fallback : process.argv[index + 1];
}

const bucketName = option("--bucket", process.env.PUBLIC_BUCKET);
const assetBaseUrl = option(
  "--asset-base-url",
  process.env.ASSET_BASE_URL || (bucketName ? `https://storage.googleapis.com/${bucketName}` : null),
)?.replace(/\/+$/, "");
const manifestPath = path.resolve(option("--manifest", DEFAULT_MANIFEST));
const outputRoot = path.resolve(option("--output", DEFAULT_OUTPUT));
const concurrency = Math.max(1, Number(option("--concurrency", "16")) || 16);
if (!bucketName) {
  console.error("--bucket or PUBLIC_BUCKET is required");
  process.exit(2);
}
if (outputRoot === path.parse(outputRoot).root || outputRoot === path.resolve(APP_ROOT, "..")) {
  throw new Error(`Refusing unsafe baked asset output '${outputRoot}'`);
}

async function sha256File(filePath) {
  const hash = createHash("sha256");
  const stream = createReadStream(filePath);
  for await (const chunk of stream) hash.update(chunk);
  return hash.digest("hex");
}

async function mapLimit(values, limit, operation) {
  let next = 0;
  async function worker() {
    while (next < values.length) {
      const index = next;
      next += 1;
      await operation(values[index], index);
    }
  }
  await Promise.all(Array.from({ length: Math.min(limit, values.length) }, worker));
}

function objectUrl(key) {
  return `${assetBaseUrl}/${key.split("/").map(encodeURIComponent).join("/")}`;
}

async function downloadObject(key, destination) {
  let lastError;
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    try {
      const response = await fetch(objectUrl(key));
      if (!response.ok || !response.body) throw new Error(`HTTP ${response.status} for ${key}`);
      await pipeline(Readable.fromWeb(response.body), createWriteStream(destination));
      return;
    } catch (error) {
      lastError = error;
      await rm(destination, { force: true });
      if (attempt < 3) await new Promise((resolve) => setTimeout(resolve, attempt * 250));
    }
  }
  throw lastError;
}

const slugs = bakedRosterSlugs(JSON.parse(await readFile(ROSTER_CONFIG, "utf8")));
const manifest = validateBakedAssetManifest(JSON.parse(await readFile(manifestPath, "utf8")), slugs);
const downloads = manifest.characters.flatMap(({ slug, assets }) => {
  const files = bakedAssetFiles(slug);
  return BAKED_ASSET_KINDS.map((kind) => ({
    relativePath: files[kind],
    ...assets[kind],
    key: bakedAssetObjectKey(files[kind], assets[kind].sha256),
  }));
});

const temporaryRoot = `${outputRoot}.download-${process.pid}`;
await rm(temporaryRoot, { recursive: true, force: true });
await mkdir(temporaryRoot, { recursive: true });
let completed = 0;

try {
  await mapLimit(downloads, concurrency, async (asset) => {
    const destination = path.join(temporaryRoot, asset.relativePath);
    await mkdir(path.dirname(destination), { recursive: true });
    await downloadObject(asset.key, destination);
    const info = await stat(destination);
    if (info.size !== asset.size || await sha256File(destination) !== asset.sha256) {
      throw new Error(`Checksum mismatch for ${asset.relativePath}`);
    }
    completed += 1;
    if (completed % 250 === 0) console.log(`Downloaded ${completed}/${downloads.length} objects...`);
  });
  await rm(outputRoot, { recursive: true, force: true });
  await rename(temporaryRoot, outputRoot);
} catch (error) {
  await rm(temporaryRoot, { recursive: true, force: true });
  throw error;
}

console.log(`Materialized ${downloads.length} verified baked assets in ${outputRoot}.`);
