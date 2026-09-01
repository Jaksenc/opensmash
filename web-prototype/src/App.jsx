import { useEffect, useRef, useState } from "react";
import AuthGate from "./AuthGate.jsx";
import FighterCreator from "./FighterCreator.jsx";
import { matchesCharacterSearch } from "../shared/character-search.js";
import { identifyRomFile } from "./rom-validation.js";
import {
  BOOT_MODES,
  CHARACTER_MESHES,
  DEFAULT_ADVANCED_OPTIONS,
  STAGES,
  engineUrl,
  hasAdvancedOverrides,
  normalizeAdvancedOptions,
} from "./launch-options.js";

const ADVANCED_OPTIONS_KEY = "opensmash-advanced-options";

function loadAdvancedOptions() {
  try {
    return normalizeAdvancedOptions(JSON.parse(sessionStorage.getItem(ADVANCED_OPTIONS_KEY)));
  } catch {
    return { ...DEFAULT_ADVANCED_OPTIONS };
  }
}

async function getSession() {
  const response = await fetch("/api/session", { cache: "no-store" });
  if (!response.ok) return { authorized: false, authenticated: false, user: null };
  return response.json();
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
      const rom = await identifyRomFile(file, { onStatus: setStatus });

      setStatus("validating");
      const response = await fetch("/api/validate-rom", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ algorithm: "SHA-1", hash: rom.sha1, size: rom.size }),
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
        : action?.type === "create"
          ? "the fighter lab"
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
              accept=".zip,.z64,.n64,.v64,.rom,application/zip,application/octet-stream"
              onChange={(event) => {
                setFile(event.target.files?.[0] || null);
                setError("");
              }}
              disabled={status !== "idle"}
            />
            <span>{file ? file.name : "Choose ROM file"}</span>
            <small>{file ? `${(file.size / 1024 / 1024).toFixed(1)} MB` : ".zip, .z64, .n64, .v64, or .rom"}</small>
          </label>
          {error && <p className="form-error">{error}</p>}
          <button className="validate-button" type="submit" disabled={!file || status !== "idle"}>
            {status === "reading" && "Reading locally…"}
            {status === "extracting" && "Extracting locally…"}
            {status === "hashing" && "Normalizing & hashing locally…"}
            {status === "validating" && "Checking ROM…"}
            {status === "idle" && "Validate & play"}
          </button>
        </form>
      </section>
    </div>
  );
}

function AdvancedModal({ options, onCancel, onSave }) {
  const [draft, setDraft] = useState(options);
  const firstFieldRef = useRef(null);

  useEffect(() => {
    firstFieldRef.current?.focus();
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const closeOnEscape = (event) => {
      if (event.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [onCancel]);

  function update(key, value) {
    setDraft((current) => ({ ...current, [key]: value }));
  }

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onCancel}>
      <section
        className="modal advanced-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="advanced-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <button className="modal-close" type="button" onClick={onCancel} aria-label="Close">
          ×
        </button>
        <p className="eyebrow">Launch overrides</p>
        <h2 id="advanced-title">Advanced options</h2>
        <p className="modal-copy">
          These choices apply to every launch in this tab and reset when the session ends.
        </p>

        <form
          className="advanced-form"
          onSubmit={(event) => {
            event.preventDefault();
            onSave(draft);
          }}
        >
          <div className="advanced-selects">
            <label>
              <span>Character mesh</span>
              <select
                ref={firstFieldRef}
                value={draft.characterMesh}
                onChange={(event) => update("characterMesh", event.target.value)}
              >
                {CHARACTER_MESHES.map((mesh) => (
                  <option value={mesh.value} key={mesh.value}>{mesh.label}</option>
                ))}
              </select>
              <small>Force the skeleton and moveset used by a chosen fighter.</small>
            </label>
            <label>
              <span>Stage</span>
              <select value={draft.stage} onChange={(event) => update("stage", event.target.value)}>
                {STAGES.map((stage) => (
                  <option value={stage.value} key={stage.value}>{stage.label}</option>
                ))}
              </select>
              <small>Used for direct matches and preselected VS launches.</small>
            </label>
          </div>

          <fieldset className="boot-mode-fieldset">
            <legend>Boot destination</legend>
            <div className="boot-mode-grid">
              {BOOT_MODES.map((mode) => (
                <label className={draft.bootMode === mode.value ? "is-selected" : ""} key={mode.value}>
                  <input
                    type="radio"
                    name="boot-mode"
                    value={mode.value}
                    checked={draft.bootMode === mode.value}
                    onChange={(event) => update("bootMode", event.target.value)}
                  />
                  <span>{mode.label}</span>
                  <small>{mode.description}</small>
                </label>
              ))}
            </div>
          </fieldset>

          <div className="advanced-actions">
            <button
              className="reset-options-button"
              type="button"
              onClick={() => setDraft({ ...DEFAULT_ADVANCED_OPTIONS })}
            >
              Reset defaults
            </button>
            <button className="save-options-button" type="submit">Save for session</button>
          </div>
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
  const [user, setUser] = useState(null);
  const [pendingAction, setPendingAction] = useState(null);
  const [engine, setEngine] = useState(null);
  const [pageError, setPageError] = useState("");
  const [fighterSearch, setFighterSearch] = useState("");
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [soundOn, setSoundOn] = useState(() => localStorage.getItem("opensmash-sound") !== "off");
  const [advancedOptions, setAdvancedOptions] = useState(loadAdvancedOptions);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const gameRef = useRef(null);
  const gameFrameRef = useRef(null);
  const engineRef = useRef(null);
  const devMenuRef = useRef(null);
  const announcerRef = useRef(null);

  async function loadCharacters() {
    const response = await fetch("/api/characters", { cache: "no-store" });
    if (!response.ok) throw new Error("Could not load the configured characters");
    const loadedCharacters = (await response.json()).characters;
    setCharacters(loadedCharacters);
    return loadedCharacters;
  }

  useEffect(() => {
    Promise.all([
      loadCharacters(),
      getSession(),
    ])
      .then(([, session]) => {
        setAuthorized(Boolean(session.authorized));
        setUser(session.user || null);
        if (isCreatePage && !session.authorized) setPendingAction({ type: "create" });
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

  useEffect(() => {
    function syncFullscreenState() {
      const fullscreenElement = document.fullscreenElement || document.webkitFullscreenElement;
      setIsFullscreen(fullscreenElement === gameFrameRef.current);
    }

    document.addEventListener("fullscreenchange", syncFullscreenState);
    document.addEventListener("webkitfullscreenchange", syncFullscreenState);
    return () => {
      document.removeEventListener("fullscreenchange", syncFullscreenState);
      document.removeEventListener("webkitfullscreenchange", syncFullscreenState);
    };
  }, []);

  function launch(action) {
    try {
      setEngine({ src: engineUrl(action, advancedOptions), action });
      setPendingAction(null);
      requestAnimationFrame(() => gameRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
    } catch (error) {
      setPageError(error.message || "Could not apply those advanced options.");
    }
  }

  function saveAdvancedOptions(nextOptions) {
    const normalized = normalizeAdvancedOptions(nextOptions);
    setAdvancedOptions(normalized);
    try {
      sessionStorage.setItem(ADVANCED_OPTIONS_KEY, JSON.stringify(normalized));
    } catch {
      // The in-memory choice still applies when session storage is unavailable.
    }
    setAdvancedOpen(false);
  }

  async function requestLaunch(action) {
    setPageError("");
    const session = authorized ? null : await getSession();
    if (authorized || session?.authorized) {
      setAuthorized(true);
      if (session?.user) setUser(session.user);
      launch(action);
    } else {
      setPendingAction(action);
    }
  }

  async function validated() {
    setAuthorized(true);
    const session = await getSession();
    setUser(session.user || null);
    if (pendingAction && pendingAction.type !== "create") launch(pendingAction);
    else setPendingAction(null);
  }

  async function authenticated(nextUser) {
    setUser(nextUser);
    await loadCharacters().catch((error) => setPageError(error.message));
  }

  async function signOutUser() {
    const response = await fetch("/api/auth/logout", { method: "POST" });
    if (!response.ok) {
      setPageError("Could not sign out.");
      return;
    }
    setUser(null);
    await loadCharacters().catch((error) => setPageError(error.message));
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

  async function toggleFullscreen() {
    const frame = gameFrameRef.current;
    if (!frame) return;

    try {
      const fullscreenElement = document.fullscreenElement || document.webkitFullscreenElement;
      if (fullscreenElement) {
        const exitFullscreen = document.exitFullscreen || document.webkitExitFullscreen;
        await exitFullscreen.call(document);
      } else {
        const requestFullscreen = frame.requestFullscreen || frame.webkitRequestFullscreen;
        if (!requestFullscreen) throw new Error("Fullscreen API unavailable");
        await requestFullscreen.call(frame);
      }
    } catch {
      setPageError("Fullscreen is not available in this browser.");
    }
  }

  const visibleCharacters = characters
    .map((character, index) => ({ character, index }))
    .filter(({ character }) => matchesCharacterSearch(character, fighterSearch));

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
          {user && (
            <button className="account-button" type="button" onClick={signOutUser}>
              {user.displayName || user.email || "Account"} · Sign out
            </button>
          )}
          <button
            className={`sound-button ${soundOn ? "is-on" : ""}`}
            type="button"
            aria-pressed={soundOn}
            onClick={toggleSound}
          >
            <i /> Sound {soundOn ? "on" : "off"}
          </button>
          <button
            className={`advanced-button ${hasAdvancedOverrides(advancedOptions) ? "is-active" : ""}`}
            type="button"
            aria-haspopup="dialog"
            onClick={() => setAdvancedOpen(true)}
          >
            <i /> Advanced
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
        <div className={`game-frame ${engine ? "is-running" : ""}`} ref={gameFrameRef}>
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
          <div className="game-frame-tools">
            {engine && (
              <button className="frame-button" type="button" onClick={() => setEngine(null)}>
                Close game
              </button>
            )}
            <button
              className="frame-button fullscreen-button"
              type="button"
              aria-label={isFullscreen ? "Exit fullscreen" : "Enter fullscreen"}
              onClick={toggleFullscreen}
            >
              <span aria-hidden="true">⛶</span>
              {isFullscreen ? "Exit fullscreen" : "Fullscreen"}
            </button>
          </div>
        </div>
      </section>}

      {isCreatePage && authorized && !user && <AuthGate onAuthenticated={authenticated} />}

      {isCreatePage && authorized && user && <FighterCreator
        onPlay={selectCharacter}
        user={user}
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

      {advancedOpen && (
        <AdvancedModal
          options={advancedOptions}
          onCancel={() => setAdvancedOpen(false)}
          onSave={saveAdvancedOptions}
        />
      )}

      {pendingAction && (
        <RomModal
          action={pendingAction}
          onCancel={() => {
            if (pendingAction.type === "create") window.location.assign("/");
            else setPendingAction(null);
          }}
          onValidated={validated}
        />
      )}
    </main>
  );
}
