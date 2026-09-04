// Cloudflare Turnstile verification for fighter creation. Per-account quotas
// bound spend per Firebase account, but the email provider hands out accounts
// freely; a human check on every create makes an account-farming loop cost a
// person (or a solver) per fighter instead of a script.
const SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify";
export const TURNSTILE_FIELD = "cf-turnstile-response";

export class TurnstileError extends Error {
  constructor(message, codes = []) {
    super(message);
    this.status = 403;
    this.code = "TURNSTILE_FAILED";
    this.codes = codes;
  }
}

export function createTurnstileVerifier({
  secretKey = process.env.TURNSTILE_SECRET_KEY || "",
  siteKey = process.env.TURNSTILE_SITE_KEY || "",
  isProduction = process.env.NODE_ENV === "production",
  fetchImpl = globalThis.fetch,
  timeoutMs = 10_000,
} = {}) {
  const enabled = Boolean(secretKey);
  if (enabled && !siteKey) {
    throw new Error("TURNSTILE_SITE_KEY is required when TURNSTILE_SECRET_KEY is set.");
  }
  if (!enabled && isProduction) {
    throw new Error("TURNSTILE_SECRET_KEY is required in production.");
  }

  async function verify(token, remoteIp = null) {
    if (!enabled) return { success: true, skipped: true };
    if (!token || typeof token !== "string" || token.length > 2048) {
      throw new TurnstileError("Complete the human check before creating a fighter.", ["missing-input-response"]);
    }
    const body = new URLSearchParams({ secret: secretKey, response: token });
    if (remoteIp && remoteIp !== "unknown") body.set("remoteip", remoteIp);
    let result;
    try {
      const response = await fetchImpl(SITEVERIFY_URL, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body,
        signal: AbortSignal.timeout(timeoutMs),
      });
      result = await response.json();
    } catch (error) {
      // Cloudflare unreachable: fail closed but say why, so the player retries
      // instead of assuming their account is blocked.
      throw new TurnstileError("The human check is unavailable right now. Try again in a moment.", ["siteverify-unreachable"]);
    }
    if (!result?.success) {
      const codes = Array.isArray(result?.["error-codes"]) ? result["error-codes"] : [];
      const stale = codes.includes("timeout-or-duplicate");
      throw new TurnstileError(
        stale
          ? "The human check expired. Try creating the fighter again."
          : "The human check failed. Refresh the page and try again.",
        codes,
      );
    }
    return { success: true, hostname: result.hostname || null };
  }

  return { enabled, siteKey: enabled ? siteKey : null, verify };
}
