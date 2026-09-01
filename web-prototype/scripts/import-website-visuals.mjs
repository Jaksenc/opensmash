import { cp, mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = path.resolve(appRoot, "..");
const websiteRoot = path.join(repoRoot, "website");
const visualRoot = path.join(appRoot, "visual");

await mkdir(visualRoot, { recursive: true });
await cp(path.join(websiteRoot, "assets"), path.join(visualRoot, "assets"), {
  recursive: true,
  force: true,
});

for (const file of ["grid-replica.js", "logo-stage.js", "crt-viewport.js", "game-launcher.js"]) {
  await cp(path.join(websiteRoot, file), path.join(visualRoot, file), { force: true });
}

await mkdir(path.join(visualRoot, "stone-tile-pipeline"), { recursive: true });
await cp(
  path.join(websiteRoot, "stone-tile-pipeline", "playground.js"),
  path.join(visualRoot, "stone-tile-pipeline", "playground.js"),
  { force: true },
);

const source = await readFile(path.join(websiteRoot, "index.html"), "utf8");
const style = source.match(/<style>\s*([\s\S]*?)<\/style>/)?.[1];
const hardware = source.match(/<script type="module">\s*([\s\S]*?)<\/script>\s*<\/body>/)?.[1];

if (!style || !hardware) throw new Error("Could not extract the website visual runtime");

await writeFile(
  path.join(visualRoot, "site-shell.css"),
  `/* Imported from website/index.html by scripts/import-website-visuals.mjs. */\n${style}`,
);
await writeFile(
  path.join(visualRoot, "site-hardware.js"),
  `// Imported from website/index.html by scripts/import-website-visuals.mjs.\n${hardware}`,
);

console.log(`Imported website visuals into ${visualRoot}`);
