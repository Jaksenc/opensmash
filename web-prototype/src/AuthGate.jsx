import { useEffect, useState } from "react";
import { getApp, getApps, initializeApp } from "firebase/app";
import {
  GoogleAuthProvider,
  OAuthProvider,
  getAuth,
  inMemoryPersistence,
  isSignInWithEmailLink,
  sendSignInLinkToEmail,
  setPersistence,
  signInWithEmailLink,
  signInWithPopup,
  signOut,
} from "firebase/auth";

const EMAIL_KEY = "opensmash-sign-in-email";

async function readResult(response) {
  const result = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(result.error || "Could not sign in.");
  return result;
}

function firebaseAuth(config) {
  const app = getApps().length ? getApp() : initializeApp(config);
  return getAuth(app);
}

export default function AuthGate({ onAuthenticated }) {
  const [config, setConfig] = useState(null);
  const [email, setEmail] = useState(() => localStorage.getItem(EMAIL_KEY) || "");
  const [status, setStatus] = useState("loading");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function exchangeSession(auth, credential) {
    const idToken = await credential.user.getIdToken(true);
    const result = await readResult(await fetch("/api/auth/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ idToken }),
    }));
    await signOut(auth);
    localStorage.removeItem(EMAIL_KEY);
    onAuthenticated(result.user);
  }

  useEffect(() => {
    let cancelled = false;
    fetch("/api/auth/config", { cache: "no-store" })
      .then(readResult)
      .then(async (loaded) => {
        if (cancelled) return;
        setConfig(loaded);
        if (!loaded.enabled) {
          const session = await readResult(await fetch("/api/session", { cache: "no-store" }));
          if (!cancelled && session.user) onAuthenticated(session.user);
          return;
        }
        const auth = firebaseAuth(loaded.firebase);
        await setPersistence(auth, inMemoryPersistence);
        if (isSignInWithEmailLink(auth, window.location.href)) {
          const savedEmail = localStorage.getItem(EMAIL_KEY);
          if (savedEmail) {
            setStatus("signing-in");
            await exchangeSession(auth, await signInWithEmailLink(auth, savedEmail, window.location.href));
            window.history.replaceState({}, "", "/create");
            return;
          }
          setMessage("Enter the same email address to finish signing in.");
        }
        setStatus("idle");
      })
      .catch((loadError) => {
        if (!cancelled) {
          setError(loadError.message);
          setStatus("idle");
        }
      });
    return () => { cancelled = true; };
  }, []);

  async function providerSignIn(providerName) {
    setStatus("signing-in");
    setError("");
    try {
      const auth = firebaseAuth(config.firebase);
      const provider = providerName === "google"
        ? new GoogleAuthProvider()
        : new OAuthProvider("apple.com");
      if (providerName === "apple") {
        provider.addScope("email");
        provider.addScope("name");
      }
      await exchangeSession(auth, await signInWithPopup(auth, provider));
    } catch (signInError) {
      setError(signInError.message || "Could not sign in.");
      setStatus("idle");
    }
  }

  async function emailSignIn(event) {
    event.preventDefault();
    const normalizedEmail = email.trim();
    if (!normalizedEmail) return;
    setStatus("signing-in");
    setError("");
    try {
      const auth = firebaseAuth(config.firebase);
      if (isSignInWithEmailLink(auth, window.location.href)) {
        await exchangeSession(auth, await signInWithEmailLink(auth, normalizedEmail, window.location.href));
        window.history.replaceState({}, "", "/create");
        return;
      }
      localStorage.setItem(EMAIL_KEY, normalizedEmail);
      await sendSignInLinkToEmail(auth, normalizedEmail, {
        url: `${window.location.origin}/create`,
        handleCodeInApp: true,
      });
      setMessage("Check your inbox for a sign-in link.");
      setStatus("sent");
    } catch (signInError) {
      setError(signInError.message || "Could not send the sign-in link.");
      setStatus("idle");
    }
  }

  const providers = new Set(config?.providers || []);

  return (
    <section className="auth-gate" aria-labelledby="auth-title">
      <p className="eyebrow">Uploader account</p>
      <h2 id="auth-title">Sign in to create</h2>
      <p>
        Sign-in keeps fighter uploads accountable and lets you return to private builds.
        Playing and browsing public fighters stay open to everyone.
      </p>
      <div className="auth-options" aria-busy={status === "loading" || status === "signing-in"}>
        {providers.has("google") && (
          <button type="button" disabled={status !== "idle"} onClick={() => providerSignIn("google")}>
            Continue with Google
          </button>
        )}
        {providers.has("apple") && (
          <button type="button" disabled={status !== "idle"} onClick={() => providerSignIn("apple")}>
            Continue with Apple
          </button>
        )}
        {providers.has("email") && (
          <form onSubmit={emailSignIn}>
            <label htmlFor="sign-in-email">Or continue with email</label>
            <div>
              <input
                id="sign-in-email"
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="you@example.com"
                autoComplete="email"
                required
                disabled={status === "loading" || status === "signing-in"}
              />
              <button type="submit" disabled={!email.trim() || status === "loading" || status === "signing-in"}>
                Email a link
              </button>
            </div>
          </form>
        )}
      </div>
      {status === "loading" && <p className="auth-message">Loading sign-in…</p>}
      {status === "signing-in" && <p className="auth-message">Signing you in…</p>}
      {message && <p className="auth-message">{message}</p>}
      {error && <p className="creator-error">{error}</p>}
    </section>
  );
}
