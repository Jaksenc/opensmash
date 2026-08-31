import { useEffect, useRef, useState } from "react";
import FighterCreator from "./FighterCreator.jsx";

const RANDOM_FIGHTER_COUNT = 12;
const RANDOM_STAGE_COUNT = 9;

function randomInt(max) {
  return Math.floor(Math.random() * max);
}

function engineUrl(action) {
  const params = new URLSearchParams({ cb: String(Date.now()) });
  if (action.type === "character") {
    params.set("inject", `bundles/${action.character.bundle}`);
    params.set("fkind", String(action.character.fkind));
    params.set("player", "0");
    params.set(
      "SSB64_BOOT_BATTLE",
      [
        action.character.fkind,
        randomInt(RANDOM_FIGHTER_COUNT),
        randomInt(RANDOM_STAGE_COUNT),
        1,
        randomInt(RANDOM_FIGHTER_COUNT),
        randomInt(RANDOM_FIGHTER_COUNT),
      ].join(","),
    );
  } else if (action.type === "select") {
    params.set("SSB64_START_SCENE", "16");
    params.set("roster", "1");
  }
  return `/engine/?${params}`;
}

async function getSession() {
  const response = await fetch("/api/session", { cache: "no-store" });
  if (!response.ok) return false;
  return Boolean((await response.json()).authorized);
}

function RomModal({ action, onCancel, onValidated }) {
  const [file, setFile] = useState(null);
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState("");
  const inputRef = useRef(null);

  useEffect(() => {
    inputRef.current?.focus();
    const closeOnEscape = (event) => {
      if (event.key === "Escape" && status === "idle") onCancel();
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [onCancel, status]);

  async function validate(event) {
    event.preventDefault();
    if (!file) return;
    setError("");
    try {
      setStatus("hashing");
      const buffer = await file.arrayBuffer();
      const digest = await crypto.subtle.digest("SHA-256", buffer);
      const hash = [...new Uint8Array(digest)]
        .map((byte) => byte.toString(16).padStart(2, "0"))
        .join("");

      setStatus("validating");
      const response = await fetch("/api/validate-rom", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ algorithm: "SHA-256", hash, size: file.size }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "ROM validation failed");
      onValidated(result.rom);
    } catch (validationError) {
      setStatus("idle");
      setError(validationError.message || "Could not validate that file");
    }
  }

  const target =
    action?.type === "character"
      ? action.character.name
      : action?.type === "start"
        ? "the full game"
        : "character select";

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onCancel}>
      <section
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="rom-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <button className="modal-close" type="button" onClick={onCancel} aria-label="Close">
          ×
        </button>
        <p className="eyebrow">One-time check</p>
        <h2 id="rom-title">Upload a ROM to continue</h2>
        <p className="modal-copy">Choose your legally obtained Smash 64 ROM to launch {target}.</p>
        <form onSubmit={validate}>
          <label className={`file-picker ${file ? "has-file" : ""}`}>
            <input
              ref={inputRef}
              type="file"
              accept=".zip,.z64,.n64,.v64,application/zip,application/octet-stream"
              onChange={(event) => {
                setFile(event.target.files?.[0] || null);
                setError("");
              }}
              disabled={status !== "idle"}
            />
            <span>{file ? file.name : "Choose ROM file"}</span>
            <small>{file ? `${(file.size / 1024 / 1024).toFixed(1)} MB` : ".zip, .z64, .n64, or .v64"}</small>
          </label>
          {error && <p className="form-error">{error}</p>}
          <button className="validate-button" type="submit" disabled={!file || status !== "idle"}>
            {status === "hashing" && "Hashing locally…"}
            {status === "validating" && "Checking ROM…"}
            {status === "idle" && "Validate & play"}
          </button>
        </form>
      </section>
    </div>
  );
}

export default function App() {
  const isCreatePage = window.location.pathname.replace(/\/+$/, "") === "/create";
  const [characters, setCharacters] = useState([]);
  const [loadingCharacters, setLoadingCharacters] = useState(true);
  const [authorized, setAuthorized] = useState(false);
  const [pendingAction, setPendingAction] = useState(null);
  const [engine, setEngine] = useState(null);
  const [pageError, setPageError] = useState("");
  const [fighterSearch, setFighterSearch] = useState("");
  const [soundOn, setSoundOn] = useState(() => localStorage.getItem("opensmash-sound") !== "off");
  const gameRef = useRef(null);
  const engineRef = useRef(null);
  const devMenuRef = useRef(null);
  const announcerRef = useRef(null);

  useEffect(() => {
    Promise.all([
      fetch("/api/characters").then(async (response) => {
        if (!response.ok) throw new Error("Could not load the configured characters");
        return (await response.json()).characters;
      }),
      getSession(),
    ])
      .then(([loadedCharacters, hasSession]) => {
        setCharacters(loadedCharacters);
        setAuthorized(hasSession);
      })
      .catch((error) => setPageError(error.message))
      .finally(() => setLoadingCharacters(false));
  }, []);

  useEffect(() => {
    if (!engine) return undefined;
    let cancelled = false;
    let attempts = 0;
    let retry;

    function applySoundPreference() {
      if (cancelled) return;
      const audioContext = engineRef.current?.contentWindow?.Module?.SDL2?.audioContext;
      if (audioContext) {
        const update = soundOn ? audioContext.resume() : audioContext.suspend();
        update?.catch(() => {});
        return;
      }
      attempts += 1;
      if (attempts < 40) retry = window.setTimeout(applySoundPreference, 250);
    }

    applySoundPreference();
    return () => {
      cancelled = true;
      window.clearTimeout(retry);
    };
  }, [engine, soundOn]);

  function launch(action) {
    setEngine({ src: engineUrl(action), action });
    setPendingAction(null);
    requestAnimationFrame(() => gameRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
  }

  async function requestLaunch(action) {
    setPageError("");
    if (authorized || (await getSession())) {
      setAuthorized(true);
      launch(action);
    } else {
      setPendingAction(action);
    }
  }

  function validated() {
    setAuthorized(true);
    if (pendingAction) launch(pendingAction);
  }

  function selectCharacter(character) {
    const previous = announcerRef.current;
    if (previous) {
      previous.pause();
      previous.currentTime = 0;
    }

    if (soundOn && character.announcer) {
      const announcer = new Audio(character.announcer);
      announcerRef.current = announcer;
      announcer.play().catch(() => {
        if (announcerRef.current === announcer) announcerRef.current = null;
      });
      announcer.addEventListener("ended", () => {
        if (announcerRef.current === announcer) announcerRef.current = null;
      }, { once: true });
    } else {
      announcerRef.current = null;
    }

    requestLaunch({ type: "character", character });
  }

  async function clearVerification() {
    setPageError("");
    const response = await fetch("/api/dev/clear-rom", { method: "POST" });
    if (!response.ok) {
      setPageError("Could not clear ROM verification");
      return;
    }
    setAuthorized(false);
    setPendingAction(null);
    setEngine(null);
    if (devMenuRef.current) devMenuRef.current.open = false;
  }

  function toggleSound() {
    setSoundOn((current) => {
      const next = !current;
      localStorage.setItem("opensmash-sound", next ? "on" : "off");
      if (!next && announcerRef.current) {
        announcerRef.current.pause();
        announcerRef.current.currentTime = 0;
        announcerRef.current = null;
      }
      return next;
    });
  }

  const normalizedSearch = fighterSearch.trim().toLocaleLowerCase();
  const visibleCharacters = characters
    .map((character, index) => ({ character, index }))
    .filter(({ character }) => {
      if (!normalizedSearch) return true;
      return [character.name, character.short, character.slug]
        .filter(Boolean)
        .some((value) => value.toLocaleLowerCase().includes(normalizedSearch));
    });

  return (
    <main className={isCreatePage ? "create-page" : undefined}>
      <header className="site-header">
        <a className="wordmark" href="/" aria-label="OpenSmash home">
          OPEN<span>SMASH</span>
        </a>
        <div className="header-tools">
          <a className="create-link" href={isCreatePage ? "/" : "/create"}>
            {isCreatePage ? "Browse fighters" : "Create fighter"}
          </a>
          <button
            className={`sound-button ${soundOn ? "is-on" : ""}`}
            type="button"
            aria-pressed={soundOn}
            onClick={toggleSound}
          >
            <i /> Sound {soundOn ? "on" : "off"}
          </button>
          <span className={`rom-status ${authorized ? "is-ready" : ""}`}>
            <i /> {authorized ? "ROM verified" : "Browser build"}
          </span>
          <details className="dev-menu" ref={devMenuRef}>
            <summary>Dev</summary>
            <div className="dev-menu-panel">
              <button type="button" onClick={clearVerification}>
                Clear ROM verification
              </button>
            </div>
          </details>
        </div>
      </header>

      {(!isCreatePage || engine) && <section className="hero" id="top" ref={gameRef}>
        <div className={`game-frame ${engine ? "is-running" : ""}`}>
          {engine ? (
            <iframe
              ref={engineRef}
              src={engine.src}
              title="OpenSmash game engine"
              allow="autoplay; gamepad; fullscreen"
            />
          ) : (
            <div className="engine-placeholder">
              <img
                src="/site-assets/branding/super-weights-bros-stacked-white.png"
                alt="Super Weights Bros"
              />
              <div>
                <p className="eyebrow">WASM game viewport</p>
                <h1>Pick a fighter.<br />Start a match.</h1>
                <p>The engine stays unloaded until you choose how to play.</p>
              </div>
            </div>
          )}
          {engine && (
            <button className="stop-game" type="button" onClick={() => setEngine(null)}>
              Close game
            </button>
          )}
        </div>
      </section>}

      {isCreatePage && <FighterCreator
        onPlay={selectCharacter}
      />}

      {!isCreatePage && <section className="select-section" aria-labelledby="select-title">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Choose your fighter</p>
            <h2 id="select-title">Character select</h2>
          </div>
          <div className="select-controls">
            <label className="fighter-search">
              <span>Search roster</span>
              <input
                type="search"
                value={fighterSearch}
                onChange={(event) => setFighterSearch(event.target.value)}
                placeholder="Find a fighter…"
                autoComplete="off"
              />
            </label>
            <div className="play-actions">
              <button
                className="start-button"
                type="button"
                onClick={() => requestLaunch({ type: "start" })}
              >
                <span>Play from start</span>
                <small>Watch the intro</small>
              </button>
              <button className="play-button" type="button" onClick={() => requestLaunch({ type: "select" })}>
                <span>Play now</span>
                <small>Open character select →</small>
              </button>
            </div>
          </div>
        </div>

        {pageError && <p className="page-error">{pageError}</p>}
        <div className="character-grid" aria-busy={loadingCharacters}>
          {loadingCharacters && <p className="loading-message">Loading fighters…</p>}
          {!loadingCharacters && characters.length === 0 && (
            <p className="loading-message">No valid characters are enabled in config/characters.json.</p>
          )}
          {!loadingCharacters && characters.length > 0 && visibleCharacters.length === 0 && (
            <p className="loading-message">No portraits match “{fighterSearch.trim()}”.</p>
          )}
          {visibleCharacters.map(({ character, index }) => (
            <button
              className="character-card"
              type="button"
              key={character.slug}
              style={{ "--index": index }}
              onClick={() => selectCharacter(character)}
            >
              <span className="portrait-wrap">
                <img src={character.portrait} alt="" />
              </span>
              <span className="character-number">{String(index + 1).padStart(2, "0")}</span>
              {character.generated && <span className="generated-label">Fighter Lab</span>}
              <span className="character-name">{character.name}</span>
              <span className="quick-match">Quick match ↗</span>
            </button>
          ))}
        </div>
      </section>}

      <footer>
        <span>OpenSmash prototype</span>
        <span>React · Node · WASM on demand</span>
      </footer>

      {pendingAction && (
        <RomModal
          action={pendingAction}
          onCancel={() => setPendingAction(null)}
          onValidated={validated}
        />
      )}
    </main>
  );
}
