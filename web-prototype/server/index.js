import { createHmac, randomUUID, timingSafeEqual } from "node:crypto";
import { createReadStream } from "node:fs";
import { access, readdir, readFile, stat } from "node:fs/promises";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createFighterJobs } from "./fighter-jobs.js";
import { HandoffError, createHandoffRoomsFromEnv } from "./handoff-rooms.js";
import { createAuthService } from "./auth.js";
import { createJobDatabase } from "./job-database.js";
import { createJobDispatcher } from "./job-dispatcher.js";
import { createObjectStore } from "./object-store.js";
import { cacheControlForEnvironment, edgeCacheHeaders } from "./cache-policy.js";
import { CREATION_DISABLED_MESSAGE, creationEnabled } from "./creation-switch.js";
import { withInitialState } from "./html-state.js";
import { resolveProjectPaths } from "./project-paths.js";
import { assignRosterBases, bundleForBase, FIGHTERS, readOsb6Targets } from "./roster.js";
import { matchesCharacterSearch } from "../shared/character-search.js";
import { bakedRosterEntries } from "../shared/baked-roster.js";
import { ROMS_BY_SHA1, UNSUPPORTED_ROMS_BY_SHA1 } from "../shared/rom-catalog.js";

const APP_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const {
  pipelineProjectRoot: PIPELINE_PROJECT_ROOT,
  engineRoot: ENGINE_ROOT,
  pipelineUiRoot: PIPELINE_UI_ROOT,
} = resolveProjectPaths(APP_ROOT);
const DIST_ROOT = path.join(APP_ROOT, "dist");
const APP_SHELL_PATHS = new Set(["/", "/create", "/create/", "/index.html"]);
const APP_SHELL_CACHE_CONTROL = "public, max-age=15";
const APP_SHELL_EDGE_CACHE_CONTROL =
  "public, max-age=30, stale-while-revalidate=300, stale-if-error=86400";
// Only "/" and "/create" are client-side routes; everything else under the
// outer app is a real file or a 404, so the shell is never served for
// /favicon.ico, /robots.txt, or typos.
const BASE_SECURITY_HEADERS = Object.freeze({
  "X-Content-Type-Options": "nosniff",
  "Referrer-Policy": "strict-origin-when-cross-origin",
  "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
});
// The outer app must never be framed (a framed /create could be clickjacked
// into a public submission). The engine is framed by the outer app itself.
const APP_SECURITY_HEADERS = Object.freeze({
  ...BASE_SECURITY_HEADERS,
  "Content-Security-Policy": "frame-ancestors 'none'",
  "X-Frame-Options": "DENY",
});
const ENGINE_SECURITY_HEADERS = Object.freeze({
  ...BASE_SECURITY_HEADERS,
  "Content-Security-Policy": "frame-ancestors 'self'",
  "X-Frame-Options": "SAMEORIGIN",
});

function securityHeaders(pathname) {
  return pathname.startsWith("/engine/") ? ENGINE_SECURITY_HEADERS : APP_SECURITY_HEADERS;
}
const PIPELINE_PLAY_ROOT = path.join(PIPELINE_PROJECT_ROOT, "play");
const SITE_ASSETS_ROOT = path.join(APP_ROOT, "visual", "assets");
const CHARACTERS_CONFIG = path.join(APP_ROOT, "config", "characters.json");
const objectStore = createObjectStore({ appRoot: APP_ROOT });
const dispatcher = createJobDispatcher();
const jobDatabase = createJobDatabase({
  jobsRoot: path.resolve(process.env.FIGHTER_JOBS_ROOT || path.join(APP_ROOT, "data", "fighter-jobs")),
});
const fighterJobs = createFighterJobs({
  appRoot: APP_ROOT,
  repoRoot: PIPELINE_PROJECT_ROOT,
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
const COOKIE_SECRETS = [
  process.env.COOKIE_SECRET || "opensmash-local-development-only",
  process.env.COOKIE_SECRET_PREVIOUS,
].filter((secret, index, secrets) => secret && secrets.indexOf(secret) === index);
const MAX_JSON_BODY = 4096;
// WebRTC offers/answers run a few KiB; the room store caps each message again.
const MAX_HANDOFF_BODY = 32 * 1024;
// Memory locally, Firestore in production (follows JOB_DATABASE) so every API
// replica sees every room.
const handoffRooms = await createHandoffRoomsFromEnv();
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
  ".ico": "image/x-icon",
  ".txt": "text/plain; charset=utf-8",
  ".mp3": "audio/mpeg",
  ".mp4": "video/mp4",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".ttf": "font/ttf",
  ".wasm": "application/wasm",
  ".wav": "audio/wav",
  ".webmanifest": "application/manifest+json",
  ".webp": "image/webp",
};

function json(res, status, data, headers = {}) {
  const body = Buffer.from(JSON.stringify(data));
  res.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Content-Length": body.length,
    "Cache-Control": "no-store",
    ...BASE_SECURITY_HEADERS,
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

function signatureFor(payload, secret = COOKIE_SECRETS[0]) {
  return createHmac("sha256", secret).update(payload).digest("base64url");
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
  const signatureBuffer = Buffer.from(signature);
  const validSignature = COOKIE_SECRETS.some((secret) => {
    const expectedBuffer = Buffer.from(signatureFor(payload, secret));
    return signatureBuffer.length === expectedBuffer.length &&
      timingSafeEqual(signatureBuffer, expectedBuffer);
  });
  if (!validSignature) {
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

function clientAddress(req) {
  const forwarded = String(req.headers["x-forwarded-for"] || "").split(",")[0].trim();
  return forwarded || req.socket.remoteAddress || "unknown";
}

function romValidationAllowed(req) {
  const address = clientAddress(req);
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

// Every static file carries a validator so "no-cache" policies cost a 304
// instead of a re-download. Size + mtime is enough: deploys rebuild the image
// (new mtimes) and purge the edge, so a validator never outlives its bytes.
function etagFor(info) {
  return `"${info.size.toString(16)}-${Math.floor(info.mtimeMs).toString(16)}"`;
}

function notModified(req, etag) {
  const header = req.headers["if-none-match"];
  if (!header) return false;
  return header.split(",").some((candidate) => {
    const value = candidate.trim();
    return value === "*" || value === etag || value === `W/${etag}`;
  });
}

async function serveFile(req, res, filePath, cacheControl = "no-store", extraHeaders = {}) {
  try {
    const info = await stat(filePath);
    if (!info.isFile()) return false;
    const pathname = new URL(req.url, "http://localhost").pathname;
    const etag = etagFor(info);
    const headers = {
      "Cache-Control": cacheControlForEnvironment(cacheControl, IS_PRODUCTION),
      ETag: etag,
      "Last-Modified": new Date(info.mtimeMs).toUTCString(),
      ...securityHeaders(pathname),
      ...extraHeaders,
    };
    if (notModified(req, etag)) {
      res.writeHead(304, headers);
      res.end();
      return true;
    }
    res.writeHead(200, {
      "Content-Type": MIME_TYPES[path.extname(filePath).toLowerCase()] || "application/octet-stream",
      "Content-Length": info.size,
      ...headers,
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

// Engine caching policy. package_web.sh stamps one content-derived build
// version (?v=) onto every runtime URL it controls, and the rules below make
// a stale/new mismatch impossible rather than merely unlikely:
//  - versioned and matching the deployed build: immutable for a year;
//  - versioned for any other build: 404 (engineBuildVersion). The origin
//    used to ignore ?v and would hand out new bytes under an old immutable
//    URL after a deploy, which is how a cached JS glue could meet a fresh
//    wasm;
//  - unversioned (index.html, manifest.json, and any file a future change
//    forgets to stamp): always revalidate. serveFile answers 304 to a
//    matching ETag, and the Cloudflare worker answers those from the edge;
//  - baked bundles: public (the worker may share them, keyed on this
//    marker) and revalidated, since their URLs carry no version. Anything
//    else under bundles/ may be owner-scoped and stays private.
const ENGINE_REVALIDATE_CACHE_CONTROL = "private, no-cache";
const ENGINE_IMMUTABLE_CACHE_CONTROL = "private, max-age=31536000, immutable";
const BAKED_BUNDLE_CACHE_CONTROL = "public, no-cache";

function engineCacheControl(relative, searchParams) {
  if (searchParams.has("v") && relative !== "index.html" && !relative.startsWith("bundles/")) {
    return ENGINE_IMMUTABLE_CACHE_CONTROL;
  }
  return ENGINE_REVALIDATE_CACHE_CONTROL;
}

// The deployed engine build version, read from the ?v= the package stamped
// into manifest.json. null when the package is unversioned (no manifest).
let engineVersionCache = { mtime: null, version: null };

async function engineBuildVersion() {
  const manifestPath = path.join(ENGINE_ROOT, "manifest.json");
  let mtime;
  try {
    mtime = (await stat(manifestPath)).mtimeMs;
  } catch {
    return null;
  }
  if (engineVersionCache.mtime !== mtime) {
    let version = null;
    try {
      const match = (await readFile(manifestPath, "utf8")).match(/[?&]v=([A-Za-z0-9._-]+)/);
      version = match ? match[1] : null;
    } catch {
      // Unreadable manifest: treat the package as unversioned.
    }
    engineVersionCache = { mtime, version };
  }
  return engineVersionCache.version;
}

async function readJsonBody(req, limit = MAX_JSON_BODY) {
  const chunks = [];
  let size = 0;
  for await (const chunk of req) {
    size += chunk.length;
    if (size > limit) throw new Error("Request body is too large");
    chunks.push(chunk);
  }
  return JSON.parse(Buffer.concat(chunks).toString("utf8"));
}

async function configuredCharacters(query = "", user = null) {
  const result = [...(await bakedRoster()).characters];
  const configuredSlugs = new Set(result.map((character) => character.slug));
  for (const job of fighterJobs.listVisible(user?.uid)) {
    if (job.status !== "complete" || !job.character || configuredSlugs.has(job.slug)) continue;
    result.push({ ...job.character, generated: true });
  }

  return result.filter((character) => matchesCharacterSearch(character, query));
}

async function bakedCharacterConfig() {
  return (await bakedRoster()).entries;
}

// The baked roster is computed once and reused by every request. It walks
// play/ and play/ui/<slug> (readdir, OSB6 header, character.json, access
// checks per character), which at 1000 fighters is thousands of fs ops, so
// it must never run per request. The cache is rebuilt when
// config/characters.json changes (one stat per request to notice that).
let bakedRosterCache = null;
let bakedRosterBuild = null;

async function bakedRoster() {
  let mtime = 0;
  try {
    mtime = (await stat(CHARACTERS_CONFIG)).mtimeMs;
  } catch {
    // A missing manifest means an empty baked roster; keep any prior cache.
  }
  if (bakedRosterCache && bakedRosterCache.mtime === mtime) return bakedRosterCache;
  bakedRosterBuild ||= buildBakedRoster(mtime).finally(() => { bakedRosterBuild = null; });
  return bakedRosterBuild;
}

async function buildBakedRoster(mtime) {
  const started = Date.now();
  const entries = bakedRosterEntries(JSON.parse(await readFile(CHARACTERS_CONFIG, "utf8")));
  const roster = await scanEngineRoster(entries);
  const characters = [];
  for (const character of roster) {
    const { slug } = character;
    const fighterName = character.base || "mario";
    const fkind = FIGHTERS.indexOf(fighterName);
    if (fkind === -1) continue;
    const characterRoot = path.join(PIPELINE_UI_ROOT, slug);
    try {
      await access(path.join(characterRoot, "portrait_raw.png"));
      const bundle = bundleForBase(slug);
      await access(path.join(PIPELINE_PLAY_ROOT, bundle));
      // Small derivatives (pipeline/portrait_tiles.py); the grid draws the
      // 90x86 tile and thumbnails use the 256, so a 1000-fighter home page
      // is a few MB, not a gigabyte. Fall back to the raw portrait for a
      // character published before the derivatives existed.
      const derivative = async (name) => {
        try {
          await access(path.join(characterRoot, name));
          return `/character-assets/${slug}/${name}`;
        } catch {
          return `/character-assets/${slug}/portrait.png`;
        }
      };
      characters.push({
        slug,
        name: character.display,
        short: character.short,
        portrait: await derivative("portrait_tile.png"),
        portraitMedium: await derivative("portrait_medium.png"),
        portraitFull: `/character-assets/${slug}/portrait.png`,
        announcer: character.voice ? `/character-assets/${slug}/announcer.wav` : null,
        base: fighterName,
        fkind,
        bundle,
        variants: character.variants,
        ui: character.ui,
        voice: character.voice,
      });
    } catch (error) {
      console.warn(`Skipping staged character '${slug}': ${error.message}`);
    }
  }
  bakedRosterCache = {
    mtime,
    entries,
    roster,
    characters,
    slugs: new Set(roster.map((character) => character.slug)),
  };
  console.log(`Baked roster: ${characters.length} characters in ${Date.now() - started} ms`);
  return bakedRosterCache;
}

async function engineRoster() {
  return (await bakedRoster()).roster;
}

async function scanEngineRoster(entries) {
  const files = new Set(await readdir(PIPELINE_PLAY_ROOT));
  const characters = [];

  for (const entry of entries) {
    const { slug } = entry;
    if (!files.has(`${slug}.osb6`)) {
      console.warn(`Skipping baked character '${slug}': play/${slug}.osb6 is missing`);
      continue;
    }
    let variants;
    try {
      variants = (await readOsb6Targets(path.join(PIPELINE_PLAY_ROOT, `${slug}.osb6`)))
        .filter((target) => target !== "mario")
        .sort();
    } catch (error) {
      console.warn(`Skipping baked character '${slug}': ${error.message}`);
      continue;
    }
    let metadata = {};
    try {
      metadata = JSON.parse(await readFile(path.join(PIPELINE_UI_ROOT, slug, "character.json"), "utf8"));
    } catch {
      // Bundle-only characters still work with generated labels.
    }
    const display = entry.name || metadata.display || slug;
    let uiFiles = new Set();
    try {
      uiFiles = new Set(await readdir(path.join(PIPELINE_UI_ROOT, slug)));
    } catch {
      // configuredCharacters reports the missing required portrait clearly.
    }
    characters.push({
      slug,
      display,
      // the roster entry as requested (e.g. "Wolfgang Amadeus Mozart" when
      // display is the announcer-length "Mozart"); search matches on it too
      nameFull: metadata.name_full || null,
      short: entry.short || metadata.short || display.toUpperCase().replace(/[^A-Z]/g, "").slice(0, 10),
      base: entry.base ?? metadata.base ?? null,
      preferredBases: entry.preferredBases || metadata.preferred_bases,
      variants,
      ui: uiFiles.has(`${slug}.osbui`),
      voice: uiFiles.has("announcer.wav"),
    });
  }

  return assignRosterBases(characters);
}

async function bakedEngineFile(relative) {
  const match = relative.match(/^bundles\/([a-z0-9]+)\.(osb6|osbui|wav)$/);
  if (!match) return null;
  const [, slug, extension] = match;
  if (!(await bakedRoster()).slugs.has(slug)) return null;

  if (extension === "osb6") {
    return path.join(PIPELINE_PLAY_ROOT, `${slug}.osb6`);
  }
  return path.join(
    PIPELINE_UI_ROOT,
    slug,
    extension === "osbui" ? `${slug}.osbui` : "announcer.wav",
  );
}

async function serveAppShell(req, res) {
  const shellPath = path.join(DIST_ROOT, "index.html");
  let html;
  try {
    html = await readFile(shellPath, "utf8");
  } catch {
    return false;
  }

  // This response is cached and shared by Cloudflare, so it must never contain
  // cookie-derived or private fighter data. Public Firestore fighters are
  // intentionally resolved on each edge cache miss rather than at startup.
  // If roster discovery fails, omit the seed and let the client fall back to
  // the no-store API instead of caching an authoritative empty roster.
  let initialState = {};
  try {
    initialState = { characters: await configuredCharacters("", null) };
  } catch (error) {
    console.warn(`Could not embed the public character roster: ${error.message}`);
  }
  const body = Buffer.from(withInitialState(html, initialState));
  res.writeHead(200, {
    "Content-Type": "text/html; charset=utf-8",
    "Content-Length": body.length,
    "Cache-Control": cacheControlForEnvironment(APP_SHELL_CACHE_CONTROL, IS_PRODUCTION),
    ...edgeCacheHeaders(APP_SHELL_EDGE_CACHE_CONTROL, IS_PRODUCTION),
    ...APP_SECURITY_HEADERS,
  });
  if (req.method === "HEAD") res.end();
  else res.end(body);
  return true;
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
      handoffRooms: handoffRooms.driver,
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
      creationEnabled: creationEnabled(),
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

  // The killswitch is enforced here, not only in the UI: a paused lab must
  // also turn away a form posted from a tab that was open before the flip.
  if (
    req.method === "POST" &&
    (pathname === "/api/fighters" || /^\/api\/fighters\/[a-f0-9-]+\/retry$/.test(pathname)) &&
    !creationEnabled()
  ) {
    return json(res, 503, { error: CREATION_DISABLED_MESSAGE, creationDisabled: true });
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

  const fighterCancelMatch = pathname.match(/^\/api\/fighters\/([a-f0-9-]+)\/cancel$/);
  if (req.method === "POST" && fighterCancelMatch) {
    try {
      return json(res, 200, { job: await fighterJobs.cancel(fighterCancelMatch[1], user.uid) });
    } catch (error) {
      return json(res, error.status || 400, { error: error.message || "Could not cancel fighter." });
    }
  }

  const fighterArtifactMatch = pathname.match(
    /^\/api\/fighters\/([a-f0-9-]+)\/assets\/(portrait|portraitTile|portraitMedium|announcer|bundle|ui|manifest|stock|emblem)\/?$/,
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
    // Stream from the object store: bundles are ~1.6 MB each and the API
    // runs on one small instance, so buffering whole objects per request
    // (x concurrency) was the largest memory risk in the service.
    let object;
    try {
      object = await objectStore.readStream(artifact.key, { public: artifact.public });
    } catch {
      return json(res, 404, { error: "Fighter asset not found." });
    }
    res.writeHead(200, {
      "Content-Type": artifact.contentType || "application/octet-stream",
      "Content-Length": object.size,
      "Cache-Control": cacheControlForEnvironment(
        artifact.public
          ? "public, max-age=31536000, immutable"
          : "private, no-store",
        IS_PRODUCTION,
      ),
      Vary: "Cookie",
    });
    if (req.method === "HEAD") {
      object.stream.destroy();
      return res.end();
    }
    object.stream.on("error", (error) => {
      console.error(`Fighter asset stream failed for ${artifact.key}:`, error);
      res.destroy();
    });
    return object.stream.pipe(res);
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

  // ROM handoff signalling (shared/rom-handoff.js, server/handoff-rooms.js).
  // Only SDP and ICE candidates pass through here; the ROM streams
  // peer-to-peer between the player's own devices.
  const handoffMatch = pathname.match(/^\/api\/handoff\/rooms(?:\/([A-Za-z0-9]{1,12})\/(join|messages|close))?$/);
  if (handoffMatch) {
    const [, code, verb] = handoffMatch;
    try {
      if (!code && req.method === "POST") {
        // Hosting requires a validated ROM session: the host is about to
        // stream the ROM it already proved it holds.
        if (!romSession) return json(res, 401, { error: "Validate your ROM on this device before sending it to another." });
        return json(res, 200, await handoffRooms.create({ address: clientAddress(req) }));
      }
      if (code && verb === "join" && req.method === "POST") {
        return json(res, 200, await handoffRooms.join(code));
      }
      if (code && verb === "messages" && req.method === "POST") {
        const body = await readJsonBody(req, MAX_HANDOFF_BODY);
        return json(res, 200, await handoffRooms.post(code, {
          role: String(body.role || ""),
          key: String(body.key || ""),
          message: body.message,
        }));
      }
      if (code && verb === "messages" && req.method === "GET") {
        return json(res, 200, await handoffRooms.poll(code, {
          role: String(url.searchParams.get("role") || ""),
          key: String(url.searchParams.get("key") || ""),
          after: Number(url.searchParams.get("after") || 0),
        }), { "Cache-Control": "no-store" });
      }
      if (code && verb === "close" && req.method === "POST") {
        const body = await readJsonBody(req);
        return json(res, 200, await handoffRooms.close(code, { role: String(body.role || ""), key: String(body.key || "") }));
      }
      return json(res, 405, { error: "Method not allowed" });
    } catch (error) {
      if (error instanceof HandoffError) return json(res, error.status, { error: error.message });
      return json(res, 400, { error: error.message || "Invalid request" });
    }
  }

  if (req.method === "POST" && pathname === "/api/validate-rom") {
    try {
      if (!romValidationAllowed(req)) {
        return json(res, 429, { error: "Too many ROM validation attempts. Try again later." });
      }
      const body = await readJsonBody(req);
      const hash = String(body.hash || "").toLowerCase();
      if (body.algorithm !== "SHA-1" || !/^[a-f0-9]{40}$/.test(hash) || !ROMS.has(hash)) {
        const known = UNSUPPORTED_ROMS_BY_SHA1.get(hash);
        if (known) {
          return json(res, 422, {
            error: `That is the ${known.region} release, which this port cannot run yet. Only the USA (NALE) ROM is supported.`,
          });
        }
        return json(res, 422, { error: "That file is not a supported Super Smash Bros. 64 ROM. Only the USA (NALE) release works." });
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
    if (!bundleMatch && url.searchParams.has("v")) {
      const current = await engineBuildVersion();
      if (current && url.searchParams.get("v") !== current) {
        return json(res, 404, { error: "That engine file belongs to a different build. Reload the page." });
      }
    }
    const bakedFile = bundleMatch ? await bakedEngineFile(relative) : null;
    const visibleDynamicBundle = bundleMatch && fighterJobs
      .listVisible(user?.uid)
      .some((job) => job.slug === bundleMatch[1]);
    if (bundleMatch && !bakedFile && !visibleDynamicBundle) {
      return json(res, 404, { error: "Engine file not found" });
    }
    if (bakedFile) {
      if (await serveFile(req, res, bakedFile, BAKED_BUNDLE_CACHE_CONTROL)) return;
      return json(res, 404, { error: "Engine file not found" });
    }
    const filePath = safeFile(ENGINE_ROOT, relative);
    if (filePath && (await serveFile(req, res, filePath, engineCacheControl(relative, url.searchParams)))) return;
    return json(res, 404, { error: "Engine file not found" });
  }

  if (pathname === "/bundles.json" || pathname === "/roster.json") {
    if (!validSession(req)) return json(res, 401, { error: "ROM validation required" });
    if (pathname === "/bundles.json") {
      const names = (await engineRoster()).flatMap((character) => [
        `${character.slug}.osb6`,
        ...(character.ui ? [`${character.slug}.osbui`] : []),
        ...(character.voice ? [`${character.slug}.wav`] : []),
      ]).sort();
      return json(res, 200, names);
    }
    return json(res, 200, await engineRoster());
  }

  if (pathname.startsWith("/character-assets/")) {
    const match = pathname.match(
      /^\/character-assets\/([a-z0-9]+)\/(portrait\.png|portrait_tile\.png|portrait_medium\.png|announcer\.wav)$/,
    );
    if (!match) return json(res, 404, { error: "Character asset not found" });
    if (!(await bakedRoster()).slugs.has(match[1])) {
      return json(res, 404, { error: "Character asset not found" });
    }
    const fileName = match[2] === "portrait.png" ? "portrait_raw.png" : match[2];
    const filePath = path.join(PIPELINE_UI_ROOT, match[1], fileName);
    if (await serveFile(req, res, filePath, "public, max-age=3600")) return;
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

  if (APP_SHELL_PATHS.has(pathname)) {
    if (await serveAppShell(req, res)) return;
    return json(res, 404, { error: "Frontend build not found. Run pnpm build first." });
  }

  const relative = pathname.slice(1);
  const filePath = safeFile(DIST_ROOT, relative);
  const cacheControl = pathname.startsWith("/app-assets/")
    ? "public, max-age=31536000, immutable"
    : "public, max-age=300";
  if (filePath && (await serveFile(req, res, filePath, cacheControl))) return;
  return json(res, 404, { error: "Not found" });
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

// Cloud Run runs a single instance; an unhandled rejection anywhere would
// otherwise exit the process and take the whole site down with it.
process.on("unhandledRejection", (reason) => {
  console.error("Unhandled promise rejection:", reason);
});

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
await bakedRoster().catch((error) => console.warn(`Baked roster unavailable at boot: ${error.message}`));
server.listen(PORT, HOST, () => {
  console.log(`OpenSmash web: http://${HOST}:${PORT}`);
});
