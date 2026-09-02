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
import FlameAction from "./FlameAction.jsx";

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

export default function AuthGate({
  accountOnly = false,
  cancelButtonRef,
  cancelLabel = "Cancel",
  onAuthenticated,
  onCancel,
}) {
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
          if (accountOnly) {
            setStatus("unavailable");
            return;
          }
          const session = await readResult(await fetch("/api/session", { cache: "no-store" }));
          if (!cancelled) {
            onAuthenticated(session.user || {
              uid: "local-development",
              displayName: "Local developer",
              email: null,
              provider: "local",
            });
          }
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
  }, [accountOnly]);

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

  const providers = new Set(config?.enabled ? config.providers : []);
  const hasSocialProvider = providers.has("google") || providers.has("apple");
  const busy = status === "loading" || status === "signing-in";

  return (
    <section className="auth-gate" aria-labelledby="auth-title">
      <header className="creator-intro auth-heading">
        {!accountOnly && <p className="eyebrow">Uploader account</p>}
        <h2 id="auth-title">{accountOnly ? "Log In" : "Sign in to Create"}</h2>
        <p>{accountOnly
          ? "Log in to save the fighters you've created"
          : "Sign-in keeps fighter uploads accountable and lets you return to private builds. Playing and browsing public fighters stay open to everyone."}
        </p>
      </header>

      <div className="auth-options" aria-busy={busy}>
        {providers.has("google") && (
          <button
            className="launch-flow-action auth-provider-button"
            type="button"
            disabled={status !== "idle"}
            onClick={() => providerSignIn("google")}
          >
            Continue with Google
          </button>
        )}
        {providers.has("apple") && (
          <button
            className="launch-flow-action auth-provider-button"
            type="button"
            disabled={status !== "idle"}
            onClick={() => providerSignIn("apple")}
          >
            Continue with Apple
          </button>
        )}
        {providers.has("email") && (
          <form onSubmit={emailSignIn}>
            {hasSocialProvider && <p className="auth-divider">Or continue with email</p>}
            <div className="fighter-fields auth-email-field">
              <label htmlFor="sign-in-email">
                <span>Email address</span>
                <input
                  id="sign-in-email"
                  type="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder="you@example.com"
                  autoComplete="email"
                  required
                  disabled={busy}
                />
              </label>
            </div>
            <FlameAction
              cellClassName="auth-email-action"
              className="auth-email-button"
              type="submit"
              disabled={!email.trim() || busy}
            >
              Email a link
            </FlameAction>
          </form>
        )}
        {status === "loading" && <p className="auth-message" role="status">Loading sign-in…</p>}
        {status === "signing-in" && <p className="auth-message" role="status">Signing you in…</p>}
        {status === "unavailable" && (
          <p className="auth-message auth-unavailable" role="status">
            Account login is disabled for this local server. Restart it with{" "}
            <code>FIREBASE_AUTH_ENABLED=1</code> and the Firebase web app settings from{" "}
            <code>.env.example</code> to test a real sign-in.
          </p>
        )}
        {message && <p className="auth-message" role="status">{message}</p>}
        {error && <p className="creator-error" role="alert">{error}</p>}
        {onCancel && (
          <button
            ref={cancelButtonRef}
            className="launch-flow-action auth-cancel-button"
            type="button"
            onClick={onCancel}
          >
            {cancelLabel}
          </button>
        )}
      </div>
    </section>
  );
}
