const AUTH_COOKIE_NAME = "opensmash_auth_v1";
const AUTH_COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 14;

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

// Sign in with Apple hands Firebase the user's name form-encoded, so spaces
// arrive as "+" ("William+J Flynn+III"). Decode it before anyone sees it.
function decodeDisplayName(name, provider) {
  if (typeof name !== "string" || !name) return null;
  if (provider !== "apple.com") return name;
  try {
    return decodeURIComponent(name.replace(/\+/g, " "));
  } catch {
    return name.replace(/\+/g, " ");
  }
}

function publicUser(claims) {
  if (!claims?.uid && !claims?.sub) return null;
  const provider = claims.firebase?.sign_in_provider || null;
  return {
    uid: claims.uid || claims.sub,
    displayName: decodeDisplayName(claims.name, provider),
    email: claims.email || null,
    photoUrl: claims.picture || null,
    provider,
  };
}

// Firebase's hosted sign-in helper lives at <project>.firebaseapp.com/__/auth/*.
// Serving it from our own origin (authDomain = smash.fun) is Firebase's
// recommended setup for browsers that partition third-party storage and for
// iOS, where a cross-site popup tab strands the user on a blank handler page.
// See "Best practices for using signInWithRedirect" in the Firebase docs.
const AUTH_HANDLER_PREFIX = "/__/auth/";
const AUTH_HANDLER_HOP_HEADERS = new Set([
  "connection", "content-length", "content-encoding", "transfer-encoding",
  "keep-alive", "host", "cookie", "set-cookie", "alt-svc", "server",
]);

export function isAuthHandlerPath(pathname) {
  return pathname.startsWith(AUTH_HANDLER_PREFIX);
}

export async function proxyAuthHandler(req, res, { upstreamOrigin, fetchImpl = fetch } = {}) {
  const url = new URL(req.url, "http://localhost");
  const target = new URL(url.pathname + url.search, upstreamOrigin);
  const headers = {};
  for (const name of ["accept", "accept-language", "content-type", "user-agent", "referer"]) {
    if (req.headers[name]) headers[name] = req.headers[name];
  }
  const hasBody = !["GET", "HEAD"].includes(req.method);
  let upstream;
  try {
    upstream = await fetchImpl(target, {
      method: req.method,
      headers,
      body: hasBody ? req : undefined,
      duplex: hasBody ? "half" : undefined,
      redirect: "manual",
    });
  } catch (error) {
    res.writeHead(502, { "Content-Type": "text/plain; charset=utf-8", "Cache-Control": "no-store" });
    res.end(`Sign-in helper unavailable: ${error.message}`);
    return;
  }
  const responseHeaders = {};
  upstream.headers.forEach((value, name) => {
    if (!AUTH_HANDLER_HOP_HEADERS.has(name.toLowerCase())) responseHeaders[name] = value;
  });
  res.writeHead(upstream.status, responseHeaders);
  if (req.method === "HEAD" || !upstream.body) {
    res.end();
    return;
  }
  const { Readable } = await import("node:stream");
  Readable.fromWeb(upstream.body).pipe(res);
}

function cookie(value, { isProduction, maxAge = AUTH_COOKIE_MAX_AGE_SECONDS } = {}) {
  return [
    `${AUTH_COOKIE_NAME}=${value}`,
    "Path=/",
    "HttpOnly",
    "SameSite=Strict",
    `Max-Age=${maxAge}`,
    isProduction ? "Secure" : null,
  ]
    .filter(Boolean)
    .join("; ");
}

export function createAuthService({ isProduction = process.env.NODE_ENV === "production" } = {}) {
  const enabled = process.env.FIREBASE_AUTH_ENABLED === "1";
  const providers = (process.env.FIREBASE_AUTH_PROVIDERS || "google,apple,email")
    .split(/[,|]/)
    .map((provider) => provider.trim())
    .filter(Boolean);
  let adminAuth = null;

  async function init() {
    if (!enabled) {
      if (isProduction) {
        throw new Error("FIREBASE_AUTH_ENABLED=1 is required in production.");
      }
      return;
    }

    for (const name of ["FIREBASE_API_KEY", "FIREBASE_AUTH_DOMAIN", "FIREBASE_APP_ID"]) {
      if (!process.env[name]) throw new Error(`${name} is required when Firebase Authentication is enabled.`);
    }

    const [{ applicationDefault, getApps, initializeApp }, { getAuth }] = await Promise.all([
      import("firebase-admin/app"),
      import("firebase-admin/auth"),
    ]);
    const app = getApps()[0] || initializeApp({
      credential: applicationDefault(),
      projectId: process.env.FIREBASE_PROJECT_ID || process.env.GOOGLE_CLOUD_PROJECT,
    });
    adminAuth = getAuth(app);
  }

  async function readUser(req, { checkRevoked = false } = {}) {
    if (!enabled || !adminAuth) return null;
    const sessionCookie = parseCookies(req)[AUTH_COOKIE_NAME];
    if (!sessionCookie) return null;
    try {
      return publicUser(await adminAuth.verifySessionCookie(sessionCookie, checkRevoked));
    } catch {
      return null;
    }
  }

  async function createSession(idToken) {
    if (!enabled || !adminAuth) throw new Error("Firebase Authentication is not enabled.");
    if (typeof idToken !== "string" || idToken.length < 100 || idToken.length > 16_384) {
      const error = new Error("A valid Firebase ID token is required.");
      error.status = 400;
      throw error;
    }

    const claims = await adminAuth.verifyIdToken(idToken, true);
    const authAgeSeconds = Math.floor(Date.now() / 1000) - Number(claims.auth_time || 0);
    if (!claims.auth_time || authAgeSeconds > 5 * 60) {
      const error = new Error("Please sign in again before starting a session.");
      error.status = 401;
      throw error;
    }
    const sessionCookie = await adminAuth.createSessionCookie(idToken, {
      expiresIn: AUTH_COOKIE_MAX_AGE_SECONDS * 1000,
    });
    return {
      cookie: cookie(sessionCookie, { isProduction }),
      user: publicUser(claims),
    };
  }

  const authDomain = process.env.FIREBASE_AUTH_DOMAIN || null;
  const projectId = process.env.FIREBASE_PROJECT_ID || process.env.GOOGLE_CLOUD_PROJECT || null;
  // Where the real Firebase handler lives. When FIREBASE_AUTH_DOMAIN is our own
  // origin, the SDK loads /__/auth/* from us and we forward it here.
  const handlerOrigin = process.env.FIREBASE_AUTH_HANDLER_ORIGIN
    || (authDomain && authDomain.endsWith(".firebaseapp.com") ? `https://${authDomain}`
      : projectId ? `https://${projectId}.firebaseapp.com` : null);

  return {
    enabled,
    providers,
    init,
    handlerOrigin,
    proxyHandler: (req, res) => proxyAuthHandler(req, res, { upstreamOrigin: handlerOrigin }),
    readUser,
    createSession,
    clearCookie: () => cookie("", { isProduction, maxAge: 0 }),
    publicConfig: () => ({
      enabled,
      providers,
      firebase: enabled ? {
        apiKey: process.env.FIREBASE_API_KEY,
        authDomain: process.env.FIREBASE_AUTH_DOMAIN,
        projectId: process.env.FIREBASE_PROJECT_ID || process.env.GOOGLE_CLOUD_PROJECT,
        appId: process.env.FIREBASE_APP_ID,
      } : null,
    }),
  };
}

export { AUTH_COOKIE_NAME, decodeDisplayName, publicUser };
