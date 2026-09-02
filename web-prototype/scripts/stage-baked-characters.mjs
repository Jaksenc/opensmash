#!/usr/bin/env node
import { execFileSync } from "node:child_process";
import { cp, mkdir, readFile, readdir, rm, stat } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { bakedRosterEntries } from "../shared/baked-roster.js";

const APP_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const PIPELINE_ROOT = path.resolve(APP_ROOT, "..");
const PLAY_ROOT = path.join(PIPELINE_ROOT, "play");
const MANIFEST_PATH = path.join(APP_ROOT, "config", "characters.json");
const STAGE_ROOT = path.join(APP_ROOT, ".baked-characters");
const requireClean = process.argv.includes("--require-clean");

async function filesBelow(root) {
  const result = [];
  for (const entry of await readdir(root, { withFileTypes: true })) {
    const target = path.join(root, entry.name);
    if (entry.isDirectory()) result.push(...await filesBelow(target));
    else if (entry.isFile()) result.push(target);
  }
  return result;
}

function gitRelative(file) {
  return path.relative(PIPELINE_ROOT, file);
}

function requireTrackedClean(files) {
  const relative = files.map(gitRelative);
  execFileSync("git", ["-C", PIPELINE_ROOT, "ls-files", "--error-unmatch", "--", ...relative], {
    stdio: "ignore",
  });
  const changes = execFileSync(
    "git",
    ["-C", PIPELINE_ROOT, "status", "--porcelain", "--untracked-files=all", "--", ...relative],
    { encoding: "utf8" },
  ).trim();
  if (changes) throw new Error(`Baked character sources are not clean:\n${changes}`);
}

const manifest = bakedRosterEntries(JSON.parse(await readFile(MANIFEST_PATH, "utf8")));
const playFiles = await readdir(PLAY_ROOT);
const sources = [MANIFEST_PATH];
const selections = [];

for (const { slug } of manifest) {
  // The shipped bundle is the single OSB6 (atlas once + every target).
  const bundles = playFiles.filter((name) => name === `${slug}.osb6`);
  if (!bundles.length) throw new Error(`Missing play/${slug}.osb6`);

  const uiRoot = path.join(PLAY_ROOT, "ui", slug);
  const requiredUi = ["character.json", "portrait_raw.png", `${slug}.osbui`, "announcer.wav"];
  for (const name of requiredUi) {
    const file = path.join(uiRoot, name);
    if (!(await stat(file)).isFile()) throw new Error(`Missing play/ui/${slug}/${name}`);
  }
  const uiFiles = await filesBelow(uiRoot);
  sources.push(...bundles.map((name) => path.join(PLAY_ROOT, name)), ...uiFiles);
  selections.push({ slug, bundles, uiRoot });
}

if (requireClean) requireTrackedClean(sources);

await rm(STAGE_ROOT, { recursive: true, force: true });
await mkdir(path.join(STAGE_ROOT, "play", "ui"), { recursive: true });
for (const { slug, bundles, uiRoot } of selections) {
  for (const name of bundles) {
    await cp(path.join(PLAY_ROOT, name), path.join(STAGE_ROOT, "play", name));
  }
  await cp(uiRoot, path.join(STAGE_ROOT, "play", "ui", slug), { recursive: true });
}

console.log(`Staged ${manifest.length} baked characters from committed pipeline/play sources.`);
