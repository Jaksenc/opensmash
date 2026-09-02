const COOKIE_NAME = "opensmash_rom_v4";
const CACHE_TTL_SECONDS = 24 * 60 * 60;

function cookieValue(header, name) {
  for (const part of (header || "").split(";")) {
    const separator = part.indexOf("=");
    if (separator === -1) continue;
    if (part.slice(0, separator).trim() === name) {
      return part.slice(separator + 1).trim();
    }
  }
  return null;
}

function base64UrlBytes(value) {
  const padded = value.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(value.length / 4) * 4, "=");
  return Uint8Array.from(atob(padded), (character) => character.charCodeAt(0));
}

function base64UrlText(value) {
  return new TextDecoder().decode(base64UrlBytes(value));
}

export async function validRomSession(cookie, secrets, now = Date.now()) {
  const candidates = (Array.isArray(secrets) ? secrets : [secrets]).filter(Boolean);
  if (!cookie || candidates.length === 0) return false;
  const separator = cookie.lastIndexOf(".");
  if (separator === -1) return false;
  const payload = cookie.slice(0, separator);
  const signature = cookie.slice(separator + 1);
  try {
    const verified = (await Promise.all(candidates.map(async (secret) => {
      const key = await crypto.subtle.importKey(
        "raw",
        new TextEncoder().encode(secret),
        { name: "HMAC", hash: "SHA-256" },
        false,
        ["verify"],
      );
      return crypto.subtle.verify(
        "HMAC",
        key,
        base64UrlBytes(signature),
        new TextEncoder().encode(payload),
      );
    }))).some(Boolean);
    if (!verified) return false;
    const session = JSON.parse(base64UrlText(payload));
    return session.version === 2 &&
      typeof session.subject === "string" &&
      typeof session.hash === "string" &&
      Number(session.expires) > now;
  } catch {
    return false;
  }
}

export function cacheRequestFor(request) {
  const url = new URL(request.url);
  if (url.pathname === "/engine/" || url.pathname === "/engine/index.html") {
    url.search = "";
  } else {
    const version = url.searchParams.get("v");
    url.search = version ? `?v=${encodeURIComponent(version)}` : "";
  }
  return new Request(url, { method: "GET" });
}

export function browserCacheControl(pathname, versioned) {
  if (pathname === "/engine/" || pathname.endsWith("/index.html")) {
    return "private, max-age=300";
  }
  if (versioned && !pathname.includes("/bundles/")) {
    return "private, max-age=31536000, immutable";
  }
  if (pathname.endsWith("/manifest.json")) return "private, max-age=300";
  if (pathname.includes("/bundles/")) return "private, max-age=300";
  return "private, max-age=3600";
}

export function sharedCacheAllowed(pathname) {
  return !pathname.startsWith("/engine/bundles/");
}

// Mirrors ENGINE_SECURITY_HEADERS in server/index.js: the engine may only be
// framed by the outer app on the same origin.
export const ENGINE_SECURITY_HEADERS = Object.freeze({
  "X-Content-Type-Options": "nosniff",
  "Referrer-Policy": "strict-origin-when-cross-origin",
  "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
  "Content-Security-Policy": "frame-ancestors 'self'",
  "X-Frame-Options": "SAMEORIGIN",
});

function clientResponse(response, request, cacheStatus) {
  const url = new URL(request.url);
  const headers = new Headers(response.headers);
  headers.set("Cache-Control", browserCacheControl(url.pathname, url.searchParams.has("v")));
  headers.set("X-OpenSmash-Edge-Cache", cacheStatus);
  for (const [name, value] of Object.entries(ENGINE_SECURITY_HEADERS)) headers.set(name, value);
  return new Response(request.method === "HEAD" ? null : response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

export default {
  async fetch(request, env, context) {
    if (request.method !== "GET" && request.method !== "HEAD") return fetch(request);
    const sessionCookie = cookieValue(request.headers.get("Cookie"), COOKIE_NAME);
    if (!(await validRomSession(sessionCookie, [env.COOKIE_SECRET, env.COOKIE_SECRET_PREVIOUS]))) {
      return new Response("ROM validation required", {
        status: 401,
        headers: { "Cache-Control": "no-store", "Content-Type": "text/plain; charset=utf-8" },
      });
    }

    // Bundle access may be scoped to the validated user's private slug at the
    // origin. Never let a response authorized for one user enter shared cache.
    if (!sharedCacheAllowed(new URL(request.url).pathname)) {
      const origin = await fetch(request);
      return clientResponse(origin, request, "BYPASS");
    }

    const cache = caches.default;
    const cacheRequest = cacheRequestFor(request);
    const cached = await cache.match(cacheRequest);
    if (cached) return clientResponse(cached, request, "HIT");

    const originRequest = request.method === "HEAD"
      ? new Request(request.url, { method: "GET", headers: request.headers })
      : request;
    const origin = await fetch(originRequest);
    if (origin.status !== 200) return origin;

    const cacheHeaders = new Headers(origin.headers);
    cacheHeaders.delete("Set-Cookie");
    cacheHeaders.set("Cache-Control", `public, max-age=${CACHE_TTL_SECONDS}`);
    const cacheable = new Response(origin.body, {
      status: origin.status,
      statusText: origin.statusText,
      headers: cacheHeaders,
    });
    context.waitUntil(cache.put(cacheRequest, cacheable.clone()));
    return clientResponse(cacheable, request, "MISS");
  },
};
