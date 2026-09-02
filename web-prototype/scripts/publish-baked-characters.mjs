#!/usr/bin/env node
import { createHash } from "node:crypto";
import { createReadStream } from "node:fs";
import { readFile, rename, stat, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { Storage } from "@google-cloud/storage";
import { bakedRosterSlugs } from "../shared/baked-roster.js";
import {
  BAKED_ASSET_KINDS,
  BAKED_ASSET_SCHEMA_VERSION,
  bakedAssetFiles,
  bakedAssetObjectKey,
  validateBakedAssetManifest,
} from "../shared/baked-assets.js";

const APP_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const PIPELINE_ROOT = path.resolve(APP_ROOT, "..");
const DEFAULT_MANIFEST = path.join(APP_ROOT, "config", "baked-assets.json");
const ROSTER_CONFIG = path.join(APP_ROOT, "config", "characters.json");

function option(name, fallback = null) {
  const index = process.argv.indexOf(name);
  return index === -1 ? fallback : process.argv[index + 1];
}

const bucketName = option("--bucket", process.env.PUBLIC_BUCKET);
const manifestPath = path.resolve(option("--manifest", DEFAULT_MANIFEST));
const dryRun = process.argv.includes("--dry-run");
const concurrency = Math.max(1, Number(option("--concurrency", "16")) || 16);

if (!bucketName && !dryRun) {
  console.error("--bucket or PUBLIC_BUCKET is required");
  process.exit(2);
}

async function sha256File(filePath) {
  const hash = createHash("sha256");
  const stream = createReadStream(filePath);
  for await (const chunk of stream) hash.update(chunk);
  return hash.digest("hex");
}

async function mapLimit(values, limit, operation) {
  const results = new Array(values.length);
  let next = 0;
  async function worker() {
    while (next < values.length) {
      const index = next;
      next += 1;
      results[index] = await operation(values[index], index);
    }
  }
  await Promise.all(Array.from({ length: Math.min(limit, values.length) }, worker));
  return results;
}

function contentType(filePath) {
  if (filePath.endsWith(".json")) return "application/json";
  if (filePath.endsWith(".png")) return "image/png";
  if (filePath.endsWith(".wav")) return "audio/wav";
  return "application/octet-stream";
}

const slugs = bakedRosterSlugs(JSON.parse(await readFile(ROSTER_CONFIG, "utf8")));
const pending = slugs.flatMap((slug) => {
  const files = bakedAssetFiles(slug);
  return BAKED_ASSET_KINDS.map((kind) => ({ slug, kind, relativePath: files[kind] }));
});

console.log(`Hashing ${pending.length} runtime assets for ${slugs.length} fighters...`);
const assets = await mapLimit(pending, concurrency, async (asset) => {
  const sourcePath = path.join(PIPELINE_ROOT, asset.relativePath);
  const info = await stat(sourcePath);
  if (!info.isFile()) throw new Error(`Missing runtime asset ${asset.relativePath}`);
  const sha256 = await sha256File(sourcePath);
  return {
    ...asset,
    sourcePath,
    sha256,
    size: info.size,
    key: bakedAssetObjectKey(asset.relativePath, sha256),
  };
});

const bySlug = new Map(slugs.map((slug) => [slug, {}]));
for (const asset of assets) bySlug.get(asset.slug)[asset.kind] = { sha256: asset.sha256, size: asset.size };
const manifest = validateBakedAssetManifest({
  schemaVersion: BAKED_ASSET_SCHEMA_VERSION,
  characters: slugs.map((slug) => ({ slug, assets: bySlug.get(slug) })),
}, slugs);
const totalBytes = assets.reduce((sum, asset) => sum + asset.size, 0);

if (dryRun) {
  console.log(`Dry run: ${assets.length} objects, ${(totalBytes / 1073741824).toFixed(2)} GiB.`);
  process.exit(0);
}

const storage = new Storage();
const bucket = storage.bucket(bucketName);
let uploaded = 0;
let reused = 0;
await mapLimit(assets, concurrency, async (asset) => {
  const remote = bucket.file(asset.key);
  const [exists] = await remote.exists();
  if (exists) {
    reused += 1;
    return;
  }
  await bucket.upload(asset.sourcePath, {
    destination: asset.key,
    resumable: false,
    metadata: {
      contentType: contentType(asset.relativePath),
      cacheControl: "public, max-age=31536000, immutable",
      metadata: { sha256: asset.sha256 },
    },
  });
  uploaded += 1;
  if (uploaded % 100 === 0) console.log(`Uploaded ${uploaded} new objects...`);
});

const body = `${JSON.stringify(manifest, null, 2)}\n`;
const temporaryManifest = `${manifestPath}.tmp-${process.pid}`;
await writeFile(temporaryManifest, body);
await rename(temporaryManifest, manifestPath);
const manifestDigest = createHash("sha256").update(body).digest("hex");
await bucket.file(`baked/v1/manifests/${manifestDigest}.json`).save(body, {
  resumable: false,
  contentType: "application/json",
  metadata: { cacheControl: "public, max-age=31536000, immutable" },
});

console.log(
  `Published ${assets.length} objects (${(totalBytes / 1073741824).toFixed(2)} GiB): ` +
  `${uploaded} uploaded, ${reused} reused.`,
);
console.log(`Wrote ${path.relative(PIPELINE_ROOT, manifestPath)} (${manifestDigest}).`);
