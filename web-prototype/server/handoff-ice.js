// handoff-ice.js — ICE server list for the ROM handoff.
//
// STUN alone only works when the two devices can reach each other directly.
// Networks with client isolation, many carrier NATs, and some home routers
// block that, so production adds a TURN relay. A relay forwards DTLS-encrypted
// packets it cannot read, so the ROM is still never readable by any server.
//
// Sources, in order of preference:
//   1. Cloudflare TURN: CLOUDFLARE_TURN_KEY_ID + CLOUDFLARE_TURN_KEY_API_TOKEN
//      mint short-lived credentials via the Realtime API. Cached briefly so a
//      burst of clients does not hammer the API.
//   2. Static TURN: TURN_URLS (comma separated) + TURN_USERNAME + TURN_CREDENTIAL
//      for a self-hosted coturn or another provider's long-lived credential.
//   3. STUN only (local development and unconfigured deploys).

export const DEFAULT_STUN = Object.freeze([
  Object.freeze({ urls: ["stun:stun.l.google.com:19302", "stun:stun1.l.google.com:19302"] }),
]);

const CLOUDFLARE_TTL_SECONDS = 15 * 60;
const CLOUDFLARE_CACHE_MS = 5 * 60 * 1000;

export function createIceServerProvider({ env = process.env, fetchImpl = globalThis.fetch, now = Date.now } = {}) {
  const cloudflare = env.CLOUDFLARE_TURN_KEY_ID && env.CLOUDFLARE_TURN_KEY_API_TOKEN
    ? { keyId: env.CLOUDFLARE_TURN_KEY_ID, token: env.CLOUDFLARE_TURN_KEY_API_TOKEN }
    : null;
  const staticTurn = env.TURN_URLS && env.TURN_USERNAME && env.TURN_CREDENTIAL
    ? {
        urls: env.TURN_URLS.split(",").map((url) => url.trim()).filter(Boolean),
        username: env.TURN_USERNAME,
        credential: env.TURN_CREDENTIAL,
      }
    : null;

  let cached = null; // { servers, expiresAt }

  async function cloudflareServers() {
    if (cached && cached.expiresAt > now()) return cached.servers;
    const response = await fetchImpl(
      `https://rtc.live.cloudflare.com/v1/turn/keys/${encodeURIComponent(cloudflare.keyId)}/credentials/generate-ice-servers`,
      {
        method: "POST",
        headers: { Authorization: `Bearer ${cloudflare.token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ ttl: CLOUDFLARE_TTL_SECONDS }),
      },
    );
    if (!response.ok) throw new Error(`Cloudflare TURN credentials failed (${response.status})`);
    const payload = await response.json();
    const servers = Array.isArray(payload.iceServers) ? payload.iceServers : [payload.iceServers];
    cached = { servers, expiresAt: now() + CLOUDFLARE_CACHE_MS };
    return servers;
  }

  return {
    /** "cloudflare" | "static" | "stun" — for health output and logs. */
    get driver() {
      return cloudflare ? "cloudflare" : staticTurn ? "static" : "stun";
    },
    /** ICE servers for a client about to open a peer connection. Never throws: falls back to STUN. */
    async iceServers() {
      const servers = [...DEFAULT_STUN];
      try {
        if (cloudflare) servers.push(...(await cloudflareServers()));
        else if (staticTurn) servers.push(staticTurn);
      } catch (error) {
        console.warn("[handoff] TURN credentials unavailable, falling back to STUN:", error.message);
      }
      return { iceServers: servers, relay: servers.length > DEFAULT_STUN.length };
    },
  };
}
