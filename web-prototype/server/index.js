import { createHmac, randomUUID, timingSafeEqual } from "node:crypto";
import { createReadStream } from "node:fs";
import { access, readdir, readFile, stat } from "node:fs/promises";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createFighterJobs } from "./fighter-jobs.js";
import { createAuthService } from "./auth.js";
import { createJobDatabase } from "./job-database.js";
import { createJobDispatcher } from "./job-dispatcher.js";
import { createObjectStore } from "./object-store.js";
import { assignRosterBases, bundleForBase, FIGHTERS } from "./roster.js";
import { matchesCharacterSearch } from "../shared/character-search.js";
import { ROMS_BY_SHA1 } from "../shared/rom-catalog.js";

const APP_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const REPO_ROOT = path.resolve(APP_ROOT, "..", "..");
const DIST_ROOT = path.join(APP_ROOT, "dist");
const ENGINE_ROOT = path.join(REPO_ROOT, "BattleShip", "web-dist");
const PIPELINE_UI_ROOT = path.join(REPO_ROOT, "pipeline", "play", "ui");
const SITE_ASSETS_ROOT = path.join(APP_ROOT, "visual", "assets");
const CHARACTERS_CONFIG = path.join(APP_ROOT, "config", "characters.json");
const objectStore = createObjectStore({ appRoot: APP_ROOT });
const dispatcher = createJobDispatcher();
const jobDatabase = createJobDatabase({
  jobsRoot: path.resolve(process.env.FIGHTER_JOBS_ROOT || path.join(APP_ROOT, "data", "fighter-jobs")),
});
const fighterJobs = createFighterJobs({
  appRoot: APP_ROOT,
  repoRoot: REPO_ROOT,
  engineRoot: ENGINE_ROOT,
  pipelineUiRoot: PIPELINE_UI_ROOT,
  objectStore,
  jobDatabase,
  dispatcher,
});

const PORT = Number(process.env.PORT || 4174);
const HOST = process.env.HOST || (process.env.NODE_ENV === "production" ? "0.0.0.0" : "127.0.0.1");
const IS_PRODUCTION = process.env.NODE_ENV === "production";
const authService = createAuthService({ isProduction: IS_PRODUCTION });
// Bump the cookie name whenever the validation contract changes. This also
// invalidates cookies created while the prototype was being exercised.
const COOKIE_NAME = "opensmash_rom_v4";
const COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 30;
const COOKIE_SECRET = process.env.COOKIE_SECRET || "opensmash-local-development-only";
const MAX_JSON_BODY = 4096;
const ROM_VALIDATION_WINDOW_MS = 15 * 60 * 1000;
const ROM_VALIDATION_LIMIT = Number(process.env.ROM_VALIDATION_LIMIT || 10);
const romValidationAttempts = new Map();

const ROMS = ROMS_BY_SHA1;

const MIME_TYPES = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".jpeg": "image/jpeg",
  ".jpg": "image/jpeg",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".glb": "model/gltf-binary",
  ".mp3": "audio/mpeg",
  ".mp4": "video/mp4",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".ttf": "font/ttf",
  ".wasm": "application/wasm",
  ".wav": "audio/wav",
  ".webp": "image/webp",
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

function streamJobEvents(req, res, id, ownerId) {
  res.writeHead(200, {
    "Content-Type": "text/event-stream; charset=utf-8",
    "Cache-Control": "no-cache, no-transform",
    Connection: "keep-alive",
    "X-Accel-Buffering": "no",
  });
  res.flushHeaders?.();

  const unsubscribe = fighterJobs.subscribe(id, ownerId, (event) => {
    res.write(`id: ${event.job.revision}\nevent: job\ndata: ${JSON.stringify(event)}\n\n`);
  });
  if (!unsubscribe) {
    res.end();
    return;
  }
  const keepAlive = setInterval(() => res.write(": keep-alive\n\n"), 15_000);
  req.on("close", () => {
    clearInterval(keepAlive);
    unsubscribe();
  });
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

function makeSession(hash, subject = randomUUID()) {
  const payload = Buffer.from(
    JSON.stringify({ version: 2, subject, hash, expires: Date.now() + COOKIE_MAX_AGE_SECONDS * 1000 }),
  ).toString("base64url");
  return `${payload}.${signatureFor(payload)}`;
}

function readSession(req) {
  const value = parseCookies(req)[COOKIE_NAME];
  if (!value) return null;
  const separator = value.lastIndexOf(".");
  if (separator === -1) return null;

  const payload = value.slice(0, separator);
  const signature = value.slice(separator + 1);
  const expected = signatureFor(payload);
  const signatureBuffer = Buffer.from(signature);
  const expectedBuffer = Buffer.from(expected);
  if (
    signatureBuffer.length !== expectedBuffer.length ||
    !timingSafeEqual(signatureBuffer, expectedBuffer)
  ) {
    return null;
  }

  try {
    const session = JSON.parse(Buffer.from(payload, "base64url").toString("utf8"));
    return session.version === 2 &&
      typeof session.subject === "string" &&
      /^[a-f0-9-]{36}$/.test(session.subject) &&
      ROMS.has(session.hash) &&
      session.expires > Date.now()
      ? session
      : null;
  } catch {
    return null;
  }
}

function validSession(req) {
  return Boolean(readSession(req));
}

function mutationOriginAllowed(req) {
  const origin = req.headers.origin;
  if (!origin) return !IS_PRODUCTION;
  const requestHost = String(req.headers["x-forwarded-host"] || req.headers.host || "")
    .split(",")[0]
    .trim();
  const requestProtocol = String(
    req.headers["x-forwarded-proto"] || (req.socket.encrypted ? "https" : "http"),
  )
    .split(",")[0]
    .trim();
  const ownOrigin = requestHost ? `${requestProtocol}://${requestHost}` : null;
  const configured = (process.env.ALLOWED_ORIGINS || "")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
  return origin === ownOrigin || configured.includes(origin);
}

function romValidationAllowed(req) {
  const forwarded = String(req.headers["x-forwarded-for"] || "").split(",")[0].trim();
  const address = forwarded || req.socket.remoteAddress || "unknown";
  const cutoff = Date.now() - ROM_VALIDATION_WINDOW_MS;
  const attempts = (romValidationAttempts.get(address) || []).filter((time) => time >= cutoff);
  if (attempts.length >= ROM_VALIDATION_LIMIT) return false;
  attempts.push(Date.now());
  romValidationAttempts.set(address, attempts);
  return true;
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

function engineCacheControl(relative, searchParams) {
  if (relative === "index.html" || relative === "manifest.json") {
    return "private, max-age=300";
  }
  if (
    searchParams.has("v") &&
    (relative === "BattleShip.js" || relative === "BattleShip.wasm")
  ) {
    return "private, max-age=31536000, immutable";
  }
  if (relative.startsWith("bundles/")) return "private, max-age=300";
  return "private, max-age=3600";
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

async function configuredCharacters(query = "", user = null) {
  const config = JSON.parse(await readFile(CHARACTERS_CONFIG, "utf8"));
  const featuredOrder = new Map(
    config.map((entry, index) => [typeof entry === "string" ? entry : entry.slug, index]),
  );
  const result = [];

  for (const character of await engineRoster()) {
    const { slug } = character;
    if (!/^[a-z0-9]+$/.test(slug)) continue;
    if (!fighterJobs.isSlugAccessible(slug, user?.uid)) continue;

    const fighterName = character.base || "mario";
    const fkind = FIGHTERS.indexOf(fighterName);
    if (fkind === -1) continue;

    const characterRoot = path.join(PIPELINE_UI_ROOT, slug);
    try {
      await access(path.join(characterRoot, "portrait_raw.png"));
      const bundle = bundleForBase(slug, fighterName);
      await access(path.join(ENGINE_ROOT, "bundles", bundle));
      result.push({
        slug,
        name: character.display,
        short: character.short,
        portrait: `/character-assets/${slug}/portrait.png`,
        announcer: character.voice ? `/character-assets/${slug}/announcer.wav` : null,
        base: fighterName,
        fkind,
        bundle,
        ui: character.ui,
        voice: character.voice,
      });
    } catch (error) {
      console.warn(`Skipping staged character '${slug}': ${error.message}`);
    }
  }

  result.sort((left, right) => {
    const leftRank = featuredOrder.get(left.slug) ?? Number.MAX_SAFE_INTEGER;
    const rightRank = featuredOrder.get(right.slug) ?? Number.MAX_SAFE_INTEGER;
    return leftRank - rightRank || left.name.localeCompare(right.name);
  });

  const configuredSlugs = new Set(result.map((character) => character.slug));
  for (const job of fighterJobs.listVisible(user?.uid)) {
    if (job.status !== "complete" || !job.character || configuredSlugs.has(job.slug)) continue;
    result.push({ ...job.character, generated: true });
  }

  return result.filter((character) => matchesCharacterSearch(character, query));
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
      base: metadata.base ?? null,
      preferredBases: metadata.preferred_bases,
      variants,
      ui: files.has(`${slug}.osbui`),
      voice: files.has(`${slug}.wav`),
    });
  }

  return assignRosterBases(characters);
}

async function handleRequest(req, res, vite) {
  const url = new URL(req.url, `http://${req.headers.host || "localhost"}`);
  const { pathname } = url;
  const romSession = readSession(req);
  let user = await authService.readUser(req, {
    checkRevoked: req.method === "POST" && pathname.startsWith("/api/fighters"),
  });
  if (!authService.enabled && romSession) {
    user = {
      uid: `local-${romSession.subject}`,
      displayName: "Local developer",
      email: null,
      provider: "local",
    };
  }

  if (
    req.method === "GET" &&
    (pathname === "/livez" || pathname === "/healthz" || pathname === "/readyz")
  ) {
    return json(res, 200, {
      ok: true,
      database: jobDatabase.driver,
      objectStore: objectStore.driver,
      dispatcher: dispatcher.driver,
    });
  }

  if (req.method === "POST" && pathname.startsWith("/api/") && !mutationOriginAllowed(req)) {
    return json(res, 403, { error: "Request origin is not allowed" });
  }

  if (req.method === "GET" && pathname === "/api/auth/config") {
    return json(res, 200, authService.publicConfig());
  }

  if (req.method === "POST" && pathname === "/api/auth/session") {
    try {
      const body = await readJsonBody(req);
      const result = await authService.createSession(body.idToken);
      return json(res, 200, { user: result.user }, { "Set-Cookie": result.cookie });
    } catch (error) {
      return json(res, error.status || 401, { error: error.message || "Could not sign in." });
    }
  }

  if (req.method === "POST" && pathname === "/api/auth/logout") {
    return json(res, 200, { signedOut: true }, { "Set-Cookie": authService.clearCookie() });
  }

  if (req.method === "GET" && pathname === "/api/session") {
    return json(res, 200, {
      authorized: Boolean(romSession),
      authenticated: Boolean(user),
      user,
    });
  }

  const fighterAssetMatch = pathname.match(
    /^\/api\/fighters\/([a-f0-9-]+)\/(?:portrait|announcer|assets(?:\/|$))/,
  );
  const accessibleFighterAsset =
    (req.method === "GET" || req.method === "HEAD") &&
    fighterAssetMatch &&
    fighterJobs.isAccessible(fighterAssetMatch[1], user?.uid);
  if (pathname.startsWith("/api/fighters") && !accessibleFighterAsset) {
    if (!romSession) return json(res, 401, { error: "ROM validation required" });
    if (!user) return json(res, 401, { error: "Sign in to use the fighter lab." });
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
    return json(res, 200, {
      characters: await configuredCharacters(url.searchParams.get("q") || "", user),
    });
  }

  if (req.method === "GET" && pathname === "/api/fighters") {
    return json(res, 200, { jobs: fighterJobs.list(user.uid) });
  }

  if (req.method === "POST" && pathname === "/api/fighters") {
    try {
      return json(res, 202, { job: await fighterJobs.create(req, user) });
    } catch (error) {
      return json(res, error.status || 400, { error: error.message || "Could not create fighter." });
    }
  }

  const fighterEventsMatch = pathname.match(/^\/api\/fighters\/([a-f0-9-]+)\/events$/);
  if (req.method === "GET" && fighterEventsMatch) {
    if (!fighterJobs.get(fighterEventsMatch[1], user.uid)) {
      return json(res, 404, { error: "Fighter job not found." });
    }
    return streamJobEvents(req, res, fighterEventsMatch[1], user.uid);
  }

  const fighterMatch = pathname.match(/^\/api\/fighters\/([a-f0-9-]+)$/);
  if (req.method === "GET" && fighterMatch) {
    const job = fighterJobs.get(fighterMatch[1], user.uid);
    return job
      ? json(res, 200, { job })
      : json(res, 404, { error: "Fighter job not found." });
  }

  const fighterRetryMatch = pathname.match(/^\/api\/fighters\/([a-f0-9-]+)\/retry$/);
  if (req.method === "POST" && fighterRetryMatch) {
    try {
      return json(res, 202, { job: await fighterJobs.retry(fighterRetryMatch[1], user.uid) });
    } catch (error) {
      return json(res, error.status || 400, { error: error.message || "Could not retry fighter." });
    }
  }

  const fighterArtifactMatch = pathname.match(
    /^\/api\/fighters\/([a-f0-9-]+)\/assets\/(portrait|announcer|bundle|ui|manifest|stock|emblem)\/?$/,
  );
  const fighterVariantMatch = pathname.match(
    /^\/api\/fighters\/([a-f0-9-]+)\/assets\/variants\/([a-z0-9]+)\/?$/,
  );
  if ((req.method === "GET" || req.method === "HEAD") && (fighterArtifactMatch || fighterVariantMatch)) {
    const id = (fighterArtifactMatch || fighterVariantMatch)[1];
    const artifact = fighterArtifactMatch
      ? fighterJobs.artifact(id, user?.uid, fighterArtifactMatch[2])
      : fighterJobs.artifact(id, user?.uid, "variants", fighterVariantMatch[2]);
    if (!artifact) return json(res, 404, { error: "Fighter asset not found." });
    try {
      const contents = await objectStore.read(artifact.key, { public: artifact.public });
      res.writeHead(200, {
        "Content-Type": artifact.contentType || "application/octet-stream",
        "Content-Length": contents.length,
        "Cache-Control": artifact.public
          ? "public, max-age=31536000, immutable"
          : "private, no-store",
        Vary: "Cookie",
      });
      return req.method === "HEAD" ? res.end() : res.end(contents);
    } catch {
      return json(res, 404, { error: "Fighter asset not found." });
    }
  }

  const fighterPortraitMatch = pathname.match(/^\/api\/fighters\/([a-f0-9-]+)\/portrait$/);
  if ((req.method === "GET" || req.method === "HEAD") && fighterPortraitMatch) {
    const filePath = fighterJobs.portraitPath(fighterPortraitMatch[1], user?.uid);
    if (filePath && (await serveFile(req, res, filePath, "public, max-age=60"))) return;
    return json(res, 404, { error: "Fighter portrait is not ready." });
  }

  const fighterAnnouncerMatch = pathname.match(/^\/api\/fighters\/([a-f0-9-]+)\/announcer$/);
  if ((req.method === "GET" || req.method === "HEAD") && fighterAnnouncerMatch) {
    const filePath = fighterJobs.announcerPath(fighterAnnouncerMatch[1], user?.uid);
    if (filePath && (await serveFile(req, res, filePath, "public, max-age=60"))) return;
    return json(res, 404, { error: "Fighter announcer clip is not ready." });
  }

  if (req.method === "POST" && pathname === "/api/validate-rom") {
    try {
      if (!romValidationAllowed(req)) {
        return json(res, 429, { error: "Too many ROM validation attempts. Try again later." });
      }
      const body = await readJsonBody(req);
      const hash = String(body.hash || "").toLowerCase();
      if (body.algorithm !== "SHA-1" || !/^[a-f0-9]{40}$/.test(hash) || !ROMS.has(hash)) {
        return json(res, 422, { error: "That file is not a supported Super Smash Bros. 64 ROM." });
      }
      const rom = ROMS.get(hash);
      if (Number(body.size) !== rom.size) {
        return json(res, 422, { error: "The ROM has the right hash but an unexpected file size." });
      }

      const cookie = [
        `${COOKIE_NAME}=${makeSession(hash, romSession?.subject)}`,
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
    const bundleMatch = relative.match(/^bundles\/([a-z0-9]+)(?:-|\.)/);
    if (bundleMatch && !fighterJobs.isSlugAccessible(bundleMatch[1], user?.uid)) {
      return json(res, 404, { error: "Engine file not found" });
    }
    const filePath = safeFile(ENGINE_ROOT, relative);
    if (filePath && (await serveFile(req, res, filePath, engineCacheControl(relative, url.searchParams)))) return;
    return json(res, 404, { error: "Engine file not found" });
  }

  if (pathname === "/bundles.json" || pathname === "/roster.json") {
    if (!validSession(req)) return json(res, 401, { error: "ROM validation required" });
    if (pathname === "/bundles.json") {
      const names = (await readdir(path.join(ENGINE_ROOT, "bundles")))
        .filter((name) => /\.(osb|osbui|wav)$/.test(name))
        .filter((name) => fighterJobs.isSlugAccessible(name.match(/^([a-z0-9]+)/)?.[1], user?.uid))
        .sort();
      return json(res, 200, names);
    }
    return json(res, 200, (await engineRoster()).filter(
      (character) => fighterJobs.isSlugAccessible(character.slug, user?.uid),
    ));
  }

  if (pathname.startsWith("/character-assets/")) {
    const match = pathname.match(
      /^\/character-assets\/([a-z0-9]+)\/(portrait\.png|announcer\.wav)$/,
    );
    if (!match) return json(res, 404, { error: "Character asset not found" });
    if (!fighterJobs.isSlugAccessible(match[1], user?.uid)) {
      return json(res, 404, { error: "Character asset not found" });
    }
    const allowed = (await engineRoster()).some((character) => character.slug === match[1]);
    if (!allowed) return json(res, 404, { error: "Character asset not found" });
    const fileName = match[2] === "portrait.png" ? "portrait_raw.png" : "announcer.wav";
    const filePath = path.join(PIPELINE_UI_ROOT, match[1], fileName);
    if (await serveFile(req, res, filePath, "public, max-age=300")) return;
    return json(res, 404, { error: "Character asset not found" });
  }

  if (pathname.startsWith("/site-assets/")) {
    const filePath = safeFile(SITE_ASSETS_ROOT, pathname.slice("/site-assets/".length));
    if (filePath && (await serveFile(req, res, filePath, "public, max-age=300"))) return;
    return json(res, 404, { error: "Site asset not found" });
  }

  // Runtime media remains under a stable path; executable visual modules are
  // part of Vite's hashed production build.
  if (pathname.startsWith("/assets/")) {
    const filePath = safeFile(SITE_ASSETS_ROOT, pathname.slice("/assets/".length));
    if (filePath && (await serveFile(req, res, filePath, "public, max-age=300"))) return;
    return json(res, 404, { error: "Site asset not found" });
  }

  if (pathname.startsWith("/objects/") && objectStore.driver === "local") {
    const objectKey = pathname.slice("/objects/".length);
    const objectMatch = objectKey.match(/^characters\/([a-z0-9]+)\/(?:versions\/[a-f0-9-]+-\d+\/|latest\.json$)/);
    const isVersioned = /^characters\/[a-z0-9]+\/versions\/[a-f0-9-]+-\d+\//.test(objectKey);
    const isLatest = /^characters\/[a-z0-9]+\/latest\.json$/.test(objectKey);
    if (!isVersioned && !isLatest) {
      return json(res, 404, { error: "Object not found" });
    }
    if (!objectMatch || !fighterJobs.isSlugPublic(objectMatch[1])) {
      return json(res, 404, { error: "Object not found" });
    }
    const filePath = objectStore.localPath(objectKey);
    const cacheControl = isLatest
      ? "public, max-age=60"
      : "public, max-age=31536000, immutable";
    if (await serveFile(req, res, filePath, cacheControl)) return;
    return json(res, 404, { error: "Object not found" });
  }

  if (vite) {
    return vite.middlewares(req, res, () => json(res, 404, { error: "Not found" }));
  }

  if (pathname === "/") {
    if (await serveFile(req, res, path.join(DIST_ROOT, "index.html"), "no-store")) return;
    return json(res, 404, { error: "Frontend build not found. Run pnpm build first." });
  }

  const relative = pathname.slice(1);
  const filePath = safeFile(DIST_ROOT, relative);
  const cacheControl = pathname.startsWith("/app-assets/")
    ? "public, max-age=31536000, immutable"
    : "public, max-age=300";
  if (filePath && (await serveFile(req, res, filePath, cacheControl))) return;
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
  throw new Error("COOKIE_SECRET must be set in production.");
}

const server = http.createServer((req, res) => {
  handleRequest(req, res, vite).catch((error) => {
    console.error(error);
    if (!res.headersSent) json(res, 500, { error: "Internal server error" });
    else res.destroy();
  });
});
server.keepAliveTimeout = 65_000;
server.headersTimeout = 66_000;

await objectStore.init();
await jobDatabase.init();
await dispatcher.init();
await authService.init();
await fighterJobs.init();
server.listen(PORT, HOST, () => {
  console.log(`OpenSmash web: http://${HOST}:${PORT}`);
});
