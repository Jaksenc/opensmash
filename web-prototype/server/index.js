import { createHmac, timingSafeEqual } from "node:crypto";
import { createReadStream } from "node:fs";
import { access, readdir, readFile, stat } from "node:fs/promises";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";

const APP_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
// The app lives beside pipeline/website inside the opensmash repo, while the
// WASM build is a sibling checkout of that repo.
const REPO_ROOT = path.resolve(APP_ROOT, "..", "..");
const DIST_ROOT = path.join(APP_ROOT, "dist");
const ENGINE_ROOT = path.join(REPO_ROOT, "BattleShip", "web-dist");
const PIPELINE_UI_ROOT = path.join(REPO_ROOT, "pipeline", "play", "ui");
const SITE_ASSETS_ROOT = path.join(REPO_ROOT, "pipeline", "website", "assets");
const CHARACTERS_CONFIG = path.join(APP_ROOT, "config", "characters.json");

const PORT = Number(process.env.PORT || 4174);
const IS_PRODUCTION = process.env.NODE_ENV === "production";
// Bump the cookie name whenever the validation contract changes. This also
// invalidates cookies created while the prototype was being exercised.
const COOKIE_NAME = "opensmash_rom_v2";
const COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 30;
const COOKIE_SECRET = process.env.COOKIE_SECRET || "opensmash-local-development-only";
const MAX_JSON_BODY = 4096;

const ROMS = new Map([
  [
    "15592e79d3c5295cef4371d4992f0bd25bec2102fc29644c93e682f7ea99ef3d",
    { name: "Super Smash Bros. (USA)", size: 16 * 1024 * 1024 },
  ],
]);

const FIGHTERS = [
  "mario",
  "fox",
  "donkey",
  "samus",
  "luigi",
  "link",
  "yoshi",
  "captain",
  "kirby",
  "pikachu",
  "purin",
  "ness",
];

const MIME_TYPES = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".ttf": "font/ttf",
  ".wasm": "application/wasm",
  ".wav": "audio/wav",
};

function json(res, status, data, headers = {}) {
  const body = Buffer.from(JSON.stringify(data));
  res.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Content-Length": body.length,
    "Cache-Control": "no-store",
    ...headers,
  });
  res.end(body);
}

function parseCookies(req) {
  const entries = (req.headers.cookie || "")
    .split(";")
    .map((part) => part.trim())
    .filter(Boolean)
    .map((part) => {
      const separator = part.indexOf("=");
      return separator === -1
        ? [part, ""]
        : [part.slice(0, separator), part.slice(separator + 1)];
    });
  return Object.fromEntries(entries);
}

function signatureFor(payload) {
  return createHmac("sha256", COOKIE_SECRET).update(payload).digest("base64url");
}

function makeSession(hash) {
  const payload = Buffer.from(
    JSON.stringify({ version: 1, hash, expires: Date.now() + COOKIE_MAX_AGE_SECONDS * 1000 }),
  ).toString("base64url");
  return `${payload}.${signatureFor(payload)}`;
}

function validSession(req) {
  const value = parseCookies(req)[COOKIE_NAME];
  if (!value) return false;
  const separator = value.lastIndexOf(".");
  if (separator === -1) return false;

  const payload = value.slice(0, separator);
  const signature = value.slice(separator + 1);
  const expected = signatureFor(payload);
  const signatureBuffer = Buffer.from(signature);
  const expectedBuffer = Buffer.from(expected);
  if (
    signatureBuffer.length !== expectedBuffer.length ||
    !timingSafeEqual(signatureBuffer, expectedBuffer)
  ) {
    return false;
  }

  try {
    const session = JSON.parse(Buffer.from(payload, "base64url").toString("utf8"));
    return session.version === 1 && ROMS.has(session.hash) && session.expires > Date.now();
  } catch {
    return false;
  }
}

function safeFile(root, relativePath) {
  let decoded;
  try {
    decoded = decodeURIComponent(relativePath).replace(/^[/\\]+/, "");
  } catch {
    return null;
  }
  const resolved = path.resolve(root, decoded);
  return resolved === root || resolved.startsWith(`${root}${path.sep}`) ? resolved : null;
}

async function serveFile(req, res, filePath, cacheControl = "no-store") {
  try {
    const info = await stat(filePath);
    if (!info.isFile()) return false;
    res.writeHead(200, {
      "Content-Type": MIME_TYPES[path.extname(filePath).toLowerCase()] || "application/octet-stream",
      "Content-Length": info.size,
      "Cache-Control": cacheControl,
    });
    if (req.method === "HEAD") {
      res.end();
    } else {
      createReadStream(filePath).pipe(res);
    }
    return true;
  } catch {
    return false;
  }
}

async function readJsonBody(req) {
  const chunks = [];
  let size = 0;
  for await (const chunk of req) {
    size += chunk.length;
    if (size > MAX_JSON_BODY) throw new Error("Request body is too large");
    chunks.push(chunk);
  }
  return JSON.parse(Buffer.concat(chunks).toString("utf8"));
}

async function configuredCharacters() {
  const config = JSON.parse(await readFile(CHARACTERS_CONFIG, "utf8"));
  const result = [];

  for (const entry of config) {
    const item = typeof entry === "string" ? { slug: entry } : entry;
    const slug = item.slug;
    if (!/^[a-z0-9]+$/.test(slug)) continue;

    const fighterName = item.fighter || "mario";
    const fkind = FIGHTERS.indexOf(fighterName);
    if (fkind === -1) continue;

    const characterRoot = path.join(PIPELINE_UI_ROOT, slug);
    try {
      const metadata = JSON.parse(await readFile(path.join(characterRoot, "character.json"), "utf8"));
      await access(path.join(characterRoot, "portrait_raw.png"));
      const bundle = fkind === 0 ? `${slug}.osb` : `${slug}-${fighterName}.osb`;
      await access(path.join(ENGINE_ROOT, "bundles", bundle));
      result.push({
        slug,
        name: metadata.display || slug,
        short: metadata.short || metadata.display || slug,
        portrait: `/character-assets/${slug}/portrait.png`,
        fkind,
        bundle,
      });
    } catch (error) {
      console.warn(`Skipping configured character '${slug}': ${error.message}`);
    }
  }

  return result;
}

async function engineRoster() {
  const bundleRoot = path.join(ENGINE_ROOT, "bundles");
  const files = new Set(await readdir(bundleRoot));
  const characters = [];

  for (const file of [...files].sort()) {
    if (!file.endsWith(".osb") || file.slice(0, -4).includes("-")) continue;
    const slug = file.slice(0, -4);
    const variants = [...files]
      .filter((candidate) => candidate.startsWith(`${slug}-`) && candidate.endsWith(".osb"))
      .map((candidate) => candidate.slice(slug.length + 1, -4))
      .sort();
    let metadata = {};
    try {
      metadata = JSON.parse(await readFile(path.join(PIPELINE_UI_ROOT, slug, "character.json"), "utf8"));
    } catch {
      // Bundle-only characters still work with generated labels.
    }
    const display = metadata.display || slug;
    characters.push({
      slug,
      display,
      short: metadata.short || display.toUpperCase().replace(/[^A-Z]/g, "").slice(0, 7),
      base: metadata.base || null,
      variants,
      ui: files.has(`${slug}.osbui`),
      voice: files.has(`${slug}.wav`),
    });
  }

  return characters;
}

async function handleRequest(req, res, vite) {
  const url = new URL(req.url, `http://${req.headers.host || "localhost"}`);
  const { pathname } = url;

  if (req.method === "GET" && pathname === "/api/session") {
    return json(res, 200, { authorized: validSession(req) });
  }

  if (req.method === "POST" && pathname === "/api/dev/clear-rom") {
    const cookie = [
      `${COOKIE_NAME}=`,
      "Path=/",
      "HttpOnly",
      "SameSite=Strict",
      "Max-Age=0",
      IS_PRODUCTION ? "Secure" : null,
    ]
      .filter(Boolean)
      .join("; ");
    return json(res, 200, { cleared: true }, { "Set-Cookie": cookie });
  }

  if (req.method === "GET" && pathname === "/api/characters") {
    return json(res, 200, { characters: await configuredCharacters() });
  }

  if (req.method === "POST" && pathname === "/api/validate-rom") {
    try {
      const body = await readJsonBody(req);
      const hash = String(body.hash || "").toLowerCase();
      if (body.algorithm !== "SHA-256" || !/^[a-f0-9]{64}$/.test(hash) || !ROMS.has(hash)) {
        return json(res, 422, { error: "That file is not a supported Super Smash Bros. 64 ROM." });
      }
      const rom = ROMS.get(hash);
      if (Number(body.size) !== rom.size) {
        return json(res, 422, { error: "The ROM has the right hash but an unexpected file size." });
      }

      const cookie = [
        `${COOKIE_NAME}=${makeSession(hash)}`,
        "Path=/",
        "HttpOnly",
        "SameSite=Strict",
        `Max-Age=${COOKIE_MAX_AGE_SECONDS}`,
        IS_PRODUCTION ? "Secure" : null,
      ]
        .filter(Boolean)
        .join("; ");
      return json(res, 200, { valid: true, rom: rom.name }, { "Set-Cookie": cookie });
    } catch (error) {
      return json(res, 400, { error: error.message || "Invalid request" });
    }
  }

  if (pathname === "/engine") {
    res.writeHead(302, { Location: "/engine/" });
    return res.end();
  }

  if (pathname.startsWith("/engine/")) {
    if (!validSession(req)) return json(res, 401, { error: "ROM validation required" });
    const relative = pathname.slice("/engine/".length) || "index.html";
    const filePath = safeFile(ENGINE_ROOT, relative);
    if (filePath && (await serveFile(req, res, filePath))) return;
    return json(res, 404, { error: "Engine file not found" });
  }

  if (pathname === "/bundles.json" || pathname === "/roster.json") {
    if (!validSession(req)) return json(res, 401, { error: "ROM validation required" });
    if (pathname === "/bundles.json") {
      const names = (await readdir(path.join(ENGINE_ROOT, "bundles")))
        .filter((name) => /\.(osb|osbui|wav)$/.test(name))
        .sort();
      return json(res, 200, names);
    }
    return json(res, 200, await engineRoster());
  }

  if (pathname.startsWith("/character-assets/")) {
    const match = pathname.match(/^\/character-assets\/([a-z0-9]+)\/portrait\.png$/);
    if (!match) return json(res, 404, { error: "Character asset not found" });
    const allowed = (await configuredCharacters()).some((character) => character.slug === match[1]);
    if (!allowed) return json(res, 404, { error: "Character asset not found" });
    const filePath = path.join(PIPELINE_UI_ROOT, match[1], "portrait_raw.png");
    if (await serveFile(req, res, filePath, "public, max-age=300")) return;
    return json(res, 404, { error: "Character asset not found" });
  }

  if (pathname.startsWith("/site-assets/")) {
    const filePath = safeFile(SITE_ASSETS_ROOT, pathname.slice("/site-assets/".length));
    if (filePath && (await serveFile(req, res, filePath, "public, max-age=300"))) return;
    return json(res, 404, { error: "Site asset not found" });
  }

  if (vite) {
    return vite.middlewares(req, res, () => json(res, 404, { error: "Not found" }));
  }

  const relative = pathname === "/" ? "index.html" : pathname.slice(1);
  const filePath = safeFile(DIST_ROOT, relative);
  if (filePath && (await serveFile(req, res, filePath, "public, max-age=300"))) return;
  if (await serveFile(req, res, path.join(DIST_ROOT, "index.html"), "no-store")) return;
  return json(res, 404, { error: "Frontend build not found. Run pnpm build first." });
}

let vite = null;
if (!IS_PRODUCTION) {
  const { createServer: createViteServer } = await import("vite");
  vite = await createViteServer({
    root: APP_ROOT,
    appType: "spa",
    server: { middlewareMode: true },
  });
}

if (IS_PRODUCTION && process.env.COOKIE_SECRET === undefined) {
  console.warn("COOKIE_SECRET is not set; using the local-development secret.");
}

const server = http.createServer((req, res) => {
  handleRequest(req, res, vite).catch((error) => {
    console.error(error);
    if (!res.headersSent) json(res, 500, { error: "Internal server error" });
    else res.destroy();
  });
});

server.listen(PORT, "127.0.0.1", () => {
  console.log(`OpenSmash prototype: http://127.0.0.1:${PORT}`);
});
