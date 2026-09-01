import { useCallback, useEffect, useRef, useState } from "react";
import flowMusicUrl from "../visual/assets/skyward-save.mp3?url";
import viewportLogoUrl from "../visual/assets/branding/super-weights-bros-stacked-white.png?url";
import AuthGate from "./AuthGate.jsx";
import CreateVisualShell from "./CreateVisualShell.jsx";
import FighterCreator from "./FighterCreator.jsx";
import FlameAction from "./FlameAction.jsx";
import ModalPage from "./ModalPage.jsx";
import RetroHome from "./RetroHome.jsx";
import RetroChoiceGrid from "./RetroChoiceGrid.jsx";
import { matchesCharacterSearch } from "../shared/character-search.js";
import {
  controlsRoadblockRequired,
  requireControlsRoadblock,
} from "../visual/controls-roadblock.js";
import { identifyRomFile } from "./rom-validation.js";
import { clearControllerTutorialCompletion } from "../visual/control-tutorial.js";
import {
  FLOW_MUSIC_MAX_VOLUME,
  transitionMediaVolume,
} from "./audio-envelope.js";
import {
  BOOT_MODES,
  CHARACTER_MESHES,
  DEFAULT_ADVANCED_OPTIONS,
  OPPONENT_LEVELS,
  STAGES,
  engineUrl,
  hasAdvancedOverrides,
  normalizeAdvancedOptions,
  selectDirectBattleOpponents,
} from "./launch-options.js";

const ADVANCED_OPTIONS_KEY = "opensmash-advanced-options";
const ACTIVE_FIGHTER_JOB_STATUSES = new Set(["queued", "running", "retrying"]);
const FLOW_MUSIC_EVENT = "opensmash:launch-flow";
const FLOW_MUSIC_URL = flowMusicUrl;

function useFlowMusic(flowActive, soundOn) {
  const flowMusicRef = useRef(null);

  useEffect(() => {
    const flowMusic = new Audio(FLOW_MUSIC_URL);
    flowMusic.id = "launch-flow-music";
    flowMusic.hidden = true;
    flowMusic.loop = true;
    flowMusic.preload = "auto";
    flowMusic.volume = 0;
    flowMusic.dataset.mixVolume = "0.0000";
    document.body.append(flowMusic);
    flowMusicRef.current = flowMusic;

    return () => {
      flowMusic.pause();
      flowMusic.removeAttribute("src");
      flowMusic.load();
      flowMusic.remove();
      flowMusicRef.current = null;
    };
  }, []);

  useEffect(() => {
    const flowMusic = flowMusicRef.current;
    if (!flowMusic) return undefined;

    let cancelTransition = () => {};
    let retryPlayback = null;
    let cancelled = false;
    flowMusic.muted = !soundOn;

    if (flowActive) {
      const play = () => {
        if (cancelled) return;
        flowMusic.play()
          .then(() => {
            if (!cancelled) {
              cancelTransition = transitionMediaVolume(flowMusic, FLOW_MUSIC_MAX_VOLUME);
            }
          })
          .catch(() => {
            if (cancelled) return;
            // Browsers can block audible autoplay until the first interaction.
            // Retry from that interaction so the user's saved sound preference
            // still takes effect without requiring a second click.
            retryPlayback = play;
            document.addEventListener("pointerdown", retryPlayback, { once: true, capture: true });
            document.addEventListener("keydown", retryPlayback, { once: true, capture: true });
          });
      };
      play();
    } else if (!flowMusic.paused && flowMusic.volume > 0) {
      cancelTransition = transitionMediaVolume(flowMusic, 0, {
        onComplete() {
          flowMusic.pause();
          flowMusic.currentTime = 0;
        },
      });
    } else {
      flowMusic.pause();
      flowMusic.currentTime = 0;
      flowMusic.volume = 0;
    }

    return () => {
      cancelled = true;
      cancelTransition();
      if (retryPlayback) {
        document.removeEventListener("pointerdown", retryPlayback, { capture: true });
        document.removeEventListener("keydown", retryPlayback, { capture: true });
      }
    };
  }, [flowActive, soundOn]);

  return useCallback(() => {
    const flowMusic = flowMusicRef.current;
    if (!flowMusic) return;
    flowMusic.muted = !soundOn;
    if (flowMusic.paused) {
      flowMusic.currentTime = 0;
      flowMusic.volume = 0;
    }
    flowMusic.play().catch(() => {});
  }, [soundOn]);
}

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
            {status === "reading" && "Reading ROM…"}
            {status === "extracting" && "Opening archive…"}
            {status === "hashing" && "Checking ROM…"}
            {status === "validating" && "Checking ROM…"}
            {status === "idle" && (action?.type === "create" ? "Validate & create" : "Validate & play")}
          </button>
        </form>
      </section>
    </div>
  );
}

function AdvancedModal({ authorized, debugMode, open, options, onCancel, onResetControllerTutorial, onResetRom, onSave }) {
  const [draft, setDraft] = useState(options);
  const firstFieldRef = useRef(null);

  useEffect(() => {
    if (open) setDraft(options);
  }, [open, options]);

  function update(key, value) {
    setDraft((current) => ({ ...current, [key]: value }));
  }

  return (
    <ModalPage
      bodyClass="is-advanced-open"
      className="advanced-overlay"
      dismissOnBackdrop
      initialFocusRef={firstFieldRef}
      onRequestClose={onCancel}
      open={open}
      role="presentation"
    >
      {(close) => (
        <section
          className="modal-page-surface advanced-screen"
          role="dialog"
          aria-modal="true"
          aria-labelledby="advanced-title"
          aria-describedby="advanced-copy"
        >
          <header className="advanced-heading">
            <h2 id="advanced-title">Advanced Options</h2>
            <p id="advanced-copy">Settings apply to every launch in this tab.</p>
          </header>

          <form
            className="advanced-form"
            onSubmit={(event) => {
              event.preventDefault();
              close(() => onSave(draft));
            }}
          >
          <div className="advanced-selects">
            <label className="advanced-field">
              <span className="advanced-field-label">Character Mesh</span>
              <span className="advanced-select-shell advanced-cell-frame flame-bridge-cell">
                <select
                  ref={firstFieldRef}
                  value={draft.characterMesh}
                  onChange={(event) => update("characterMesh", event.target.value)}
                >
                  {CHARACTER_MESHES.map((mesh) => (
                    <option value={mesh.value} key={mesh.value}>{mesh.label}</option>
                  ))}
                </select>
              </span>
              <small>Force the skeleton and moveset used by a chosen fighter.</small>
            </label>
            <label className="advanced-field">
              <span className="advanced-field-label">Stage</span>
              <span className="advanced-select-shell advanced-cell-frame flame-bridge-cell">
                <select value={draft.stage} onChange={(event) => update("stage", event.target.value)}>
                  {STAGES.map((stage) => (
                    <option value={stage.value} key={stage.value}>{stage.label}</option>
                  ))}
                </select>
              </span>
              <small>Used for direct matches and preselected VS launches.</small>
            </label>
            <label className="advanced-field">
              <span className="advanced-field-label">Opponent Difficulty</span>
              <span className="advanced-select-shell advanced-cell-frame flame-bridge-cell">
                <select
                  value={draft.opponentLevel}
                  onChange={(event) => update("opponentLevel", event.target.value)}
                >
                  {OPPONENT_LEVELS.map((level) => (
                    <option value={level.value} key={level.value}>{level.label}</option>
                  ))}
                </select>
              </span>
              <small>CPU level for every computer-controlled opponent.</small>
            </label>
          </div>

          <fieldset className="boot-mode-fieldset">
            <legend>Boot Destination</legend>
            <RetroChoiceGrid
              name="boot-mode"
              value={draft.bootMode}
              options={BOOT_MODES}
              onChange={(value) => update("bootMode", value)}
            />
          </fieldset>

          {debugMode && (
            <section className="advanced-debug-tools" aria-labelledby="advanced-debug-title">
              <div>
                <strong id="advanced-debug-title">Debug</strong>
                <small>Restore first-run checks for this browser.</small>
              </div>
              <div className="advanced-debug-actions">
                {authorized && (
                  <button
                    className="launch-flow-action reset-rom-button"
                    type="button"
                    onClick={() => close(onResetRom)}
                  >
                    Reset ROM
                  </button>
                )}
                <button
                  className="launch-flow-action reset-controller-button"
                  type="button"
                  onClick={() => close(onResetControllerTutorial)}
                >
                  Reset Controller Tutorial
                </button>
              </div>
            </section>
          )}

          <div className="advanced-actions">
            <FlameAction cellClassName="advanced-save-cell" className="save-options-button" type="submit">
              Save Settings
            </FlameAction>
            <button
              className="launch-flow-action reset-options-button"
              type="button"
              onClick={() => setDraft({ ...DEFAULT_ADVANCED_OPTIONS })}
            >
              Reset Settings
            </button>
            <button
              className="launch-flow-action cancel-options-button"
              type="button"
              onClick={() => close()}
            >
              Cancel
            </button>
          </div>
          </form>
        </section>
      )}
    </ModalPage>
  );
}

function CreateExperienceOverlay({ onAuthenticated, onClose, onCreated, onPlay, stage, user }) {
  const surfaceRef = useRef(null);
  const open = stage === "auth" || stage === "creator";

  return (
    <ModalPage
      bodyClass="is-create-experience-open"
      className="create-experience-backdrop"
      initialFocusRef={surfaceRef}
      onRequestClose={onClose}
      open={open}
      role="presentation"
    >
      {(close) => (
        <section
          ref={surfaceRef}
          className="modal-page-surface create-experience create-page"
          aria-label="Create a fighter"
          aria-modal="true"
          role="dialog"
          tabIndex="-1"
        >
          {stage === "auth" && (
            <button className="create-experience-close" type="button" onClick={() => close()} aria-label="Back to fighters">
              ×
            </button>
          )}
          {stage === "auth" && <AuthGate onAuthenticated={onAuthenticated} />}
          {stage === "creator" && user && (
            <FighterCreator
              onCancel={() => close()}
              onCreated={(job) => close(() => onCreated(job))}
              onPlay={onPlay}
            />
          )}
        </section>
      )}
    </ModalPage>
  );
}

export default function App() {
  const isCreatePage = window.location.pathname.replace(/\/+$/, "") === "/create";
  const [characters, setCharacters] = useState([]);
  const [fighterJobs, setFighterJobs] = useState([]);
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
  const [createStage, setCreateStage] = useState(null);
  const [flowMusicActive, setFlowMusicActive] = useState(false);
  const gameRef = useRef(null);
  const gameFrameRef = useRef(null);
  const engineRef = useRef(null);
  const devMenuRef = useRef(null);
  const announcerRef = useRef(null);
  const visualBridgeRef = useRef({});
  const startFlowMusic = useFlowMusic(flowMusicActive && !engine, soundOn);
  useEffect(() => {
    const syncFlowMusic = (event) => {
      const open = Boolean(event.detail?.open);
      setFlowMusicActive(open);
      if (open && !engine) startFlowMusic();
    };
    window.addEventListener(FLOW_MUSIC_EVENT, syncFlowMusic);
    return () => window.removeEventListener(FLOW_MUSIC_EVENT, syncFlowMusic);
  }, [engine, startFlowMusic]);
  const reportCreateVisualError = useCallback((error) => {
    setPageError(error.message || "Could not load the ROM upload screen.");
  }, []);

  async function loadCharacters() {
    const response = await fetch("/api/characters", { cache: "no-store" });
    if (!response.ok) throw new Error("Could not load the configured characters");
    const loadedCharacters = (await response.json()).characters;
    setCharacters(loadedCharacters);
    return loadedCharacters;
  }

  const recordFighterJob = useCallback((job) => {
    if (!job?.id) return;
    setFighterJobs((current) => {
      const existing = current.find((candidate) => candidate.id === job.id);
      if (existing && (existing.revision || 0) > (job.revision || 0)) return current;
      return [job, ...current.filter((candidate) => candidate.id !== job.id)];
    });
    if (job.status === "complete" && job.character) {
      setCharacters((current) => {
        const generated = { ...job.character, generated: true };
        const existingIndex = current.findIndex((character) => character.slug === generated.slug);
        if (existingIndex === -1) return [...current, generated];
        return current.map((character, index) => (index === existingIndex ? generated : character));
      });
    }
  }, []);

  useEffect(() => {
    Promise.all([
      loadCharacters(),
      getSession(),
    ])
      .then(([, session]) => {
        setAuthorized(Boolean(session.authorized));
        setUser(session.user || null);
        if (isCreatePage && session.user && !session.authorized) {
          setPendingAction({ type: "create" });
        }
      })
      .catch((error) => setPageError(error.message))
      .finally(() => setLoadingCharacters(false));
  }, []);

  useEffect(() => {
    if (!authorized || !user) {
      setFighterJobs([]);
      return undefined;
    }
    let cancelled = false;

    async function refreshFighterJobs() {
      const response = await fetch("/api/fighters", { cache: "no-store" });
      if (!response.ok) return;
      const result = await response.json();
      if (cancelled) return;
      setFighterJobs((current) => {
        const tracked = new Map(current.map((job) => [job.id, job]));
        return result.jobs
          .map((job) => {
            const existing = tracked.get(job.id);
            return existing && (existing.revision || 0) > (job.revision || 0) ? existing : job;
          })
          .sort((left, right) => right.createdAt.localeCompare(left.createdAt));
      });
    }

    refreshFighterJobs().catch(() => {});
    const timer = window.setInterval(() => refreshFighterJobs().catch(() => {}), 15_000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [authorized, user?.uid]);

  const activeFighterJobKey = fighterJobs
    .filter((job) => ACTIVE_FIGHTER_JOB_STATUSES.has(job.status))
    .map((job) => job.id)
    .sort()
    .join(",");

  useEffect(() => {
    if (!activeFighterJobKey) return undefined;
    const streams = activeFighterJobKey.split(",").map((id) => {
      const stream = new EventSource(`/api/fighters/${id}/events`);
      stream.addEventListener("job", (event) => {
        try {
          recordFighterJob(JSON.parse(event.data).job);
        } catch {
          // The polling fallback will reconcile malformed or interrupted events.
        }
      });
      return stream;
    });
    return () => streams.forEach((stream) => stream.close());
  }, [activeFighterJobKey, recordFighterJob]);

  useEffect(() => {
    let cancelled = false;
    let timer;
    let attempts = 0;
    function syncGridJobs() {
      if (cancelled) return;
      if (window.characterGrid?.syncJobs) {
        Promise.resolve(window.characterGrid.syncJobs(fighterJobs)).catch(() => {});
        return;
      }
      attempts += 1;
      if (attempts < 100) timer = window.setTimeout(syncGridJobs, 50);
    }
    syncGridJobs();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [fighterJobs]);

  useEffect(() => {
    if (isCreatePage || createStage !== "rom") return undefined;
    let cancelled = false;
    let attempts = 0;
    let timer;

    function requestCreateRom() {
      if (cancelled) return;
      if (window.gameLauncher?.requestCreate) {
        window.gameLauncher.requestCreate();
        return;
      }
      attempts += 1;
      if (attempts < 100) timer = window.setTimeout(requestCreateRom, 50);
      else {
        setCreateStage(null);
        setPageError("Could not open the cartridge upload screen.");
      }
    }

    requestCreateRom();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [createStage, isCreatePage]);

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
      const launchAction = prepareLaunchAction(action);
      setEngine({ src: engineUrl(launchAction, advancedOptions), action: launchAction });
      setPendingAction(null);
      requestAnimationFrame(() => gameRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
    } catch (error) {
      setPageError(error.message || "Could not apply those advanced options.");
    }
  }

  function prepareLaunchAction(action) {
    if (action.type !== "character" || action.opponents) return action;
    const ownedCharacters = fighterJobs
      .filter((job) => job.status === "complete" && job.character)
      .map((job) => job.character);
    return {
      ...action,
      opponents: selectDirectBattleOpponents(
        action.character,
        characters,
        ownedCharacters,
      ),
    };
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
    if (isCreatePage && controlsRoadblockRequired()) {
      window.location.assign("/");
      return;
    }
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
    if (isCreatePage && !authorized) setPendingAction({ type: "create" });
    await loadCharacters().catch((error) => setPageError(error.message));
  }

  async function openCreateExperience() {
    setPageError("");
    try {
      const session = await getSession();
      setAuthorized(Boolean(session.authorized));
      setUser(session.user || null);
      if (!session.user) setCreateStage("auth");
      else setCreateStage(session.authorized ? "creator" : "rom");
    } catch (error) {
      setPageError(error.message || "Could not start character creation.");
    }
  }

  async function authenticatedForCreate(nextUser) {
    setUser(nextUser);
    setCreateStage(authorized ? "creator" : "rom");
    await loadCharacters().catch((error) => setPageError(error.message));
  }

  function playCreatedCharacter(character) {
    setCreateStage(null);
    announceCharacter(character);
    window.setTimeout(() => window.gameLauncher?.requestCharacter?.(character.slug), 0);
  }

  function fighterCreated(job) {
    recordFighterJob(job);
    setCreateStage(null);
    setPageError("");
  }

  async function signOutUser() {
    const response = await fetch("/api/auth/logout", { method: "POST" });
    if (!response.ok) {
      setPageError("Could not sign out.");
      return;
    }
    setUser(null);
    setCreateStage(null);
    await loadCharacters().catch((error) => setPageError(error.message));
  }

  function selectCharacter(character) {
    announceCharacter(character);
    requestLaunch({ type: "character", character });
  }

  function announceCharacter(character) {
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

  }

  async function validateVisualRom(file, onStatus) {
    const rom = await identifyRomFile(file, { onStatus });
    onStatus?.("validating");
    const response = await fetch("/api/validate-rom", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ algorithm: "SHA-1", hash: rom.sha1, size: rom.size }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "ROM validation failed");
    setAuthorized(true);
    const session = await getSession();
    setUser(session.user || null);
    return result;
  }

  async function validateCreateVisualRom(file, onStatus) {
    const result = await validateVisualRom(file, onStatus);
    requireControlsRoadblock();
    return result;
  }

  function launchVisualAction({ type, slug }) {
    const action = type === "character"
      ? { type, character: characters.find((character) => character.slug === slug) }
      : { type };
    if (type === "character" && !action.character) {
      setPageError("That fighter is no longer available.");
      return "about:blank";
    }
    try {
      const launchAction = prepareLaunchAction(action);
      const src = engineUrl(launchAction, advancedOptions);
      setEngine({ src, action: launchAction });
      setPendingAction(null);
      setPageError("");
      return src;
    } catch (error) {
      setPageError(error.message || "Could not apply those advanced options.");
      return "about:blank";
    }
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
    setAdvancedOpen(false);
    window.characterGrid?.select(null);
    if (devMenuRef.current) devMenuRef.current.open = false;
  }

  async function resetRomFromAdvanced() {
    setAdvancedOpen(false);
    await clearVerification();
  }

  function resetControllerTutorialFromAdvanced() {
    try { clearControllerTutorialCompletion(localStorage); }
    catch { /* The runtime reset below still applies to this tab. */ }
    window.gameLauncher?.resetControls?.();
    setAdvancedOpen(false);
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

  if (isCreatePage) {
    Object.assign(visualBridgeRef.current, {
      completeCreateRom() { setPendingAction(null); },
      isAuthorized() { return authorized; },
      cancelCreateRom() { window.location.assign("/"); },
      reportError: reportCreateVisualError,
      validateCreateRom: validateCreateVisualRom,
      validateRom: validateCreateVisualRom,
    });
    window.openSmashReactBridge = visualBridgeRef.current;
  }

  if (!isCreatePage) {
    Object.assign(visualBridgeRef.current, {
      characters,
      fighterJobs,
      announceCharacter(slug) {
        const character = characters.find((candidate) => candidate.slug === slug);
        if (character) announceCharacter(character);
      },
      clearVerification,
      closeGame() { setEngine(null); },
      completeCreateRom() { setCreateStage("creator"); },
      isAuthorized() { return authorized; },
      launch: launchVisualAction,
      cancelCreateRom() { setCreateStage(null); },
      navigate(pathname) {
        if (pathname === "/create") openCreateExperience();
        else window.location.assign(pathname);
      },
      reportError(error) { setPageError(error.message || "Could not load the visual experience."); },
      validateCreateRom: validateCreateVisualRom,
      validateRom: validateVisualRom,
    });
    window.openSmashReactBridge = visualBridgeRef.current;

    return (
      <>
        <RetroHome
          advancedActive={hasAdvancedOverrides(advancedOptions)}
          authorized={authorized}
          developmentMode={import.meta.env.DEV}
          engine={engine}
          engineRef={engineRef}
          gameFrameRef={gameFrameRef}
          isFullscreen={isFullscreen}
          launchFlowOpen={flowMusicActive}
          onAdvanced={() => setAdvancedOpen(true)}
          onCloseGame={() => setEngine(null)}
          onCreate={openCreateExperience}
          onFullscreen={toggleFullscreen}
          onResetRom={clearVerification}
          onSignOut={signOutUser}
          onSound={toggleSound}
          pageError={pageError}
          ready={!loadingCharacters}
          soundOn={soundOn}
          user={user}
        />
        <CreateExperienceOverlay
          onAuthenticated={authenticatedForCreate}
          onClose={() => setCreateStage(null)}
          onCreated={fighterCreated}
          onPlay={playCreatedCharacter}
          stage={createStage}
          user={user}
        />
        <AdvancedModal
          authorized={authorized}
          debugMode={new URLSearchParams(window.location.search).get("debug") === "1"}
          open={advancedOpen}
          options={advancedOptions}
          onCancel={() => setAdvancedOpen(false)}
          onResetControllerTutorial={resetControllerTutorialFromAdvanced}
          onResetRom={resetRomFromAdvanced}
          onSave={saveAdvancedOptions}
        />
      </>
    );
  }

  return (
    <main className={isCreatePage ? "create-page" : undefined}>
      {isCreatePage && (
        <CreateVisualShell
          onError={reportCreateVisualError}
          romUploadRequired={!loadingCharacters && Boolean(user) && !authorized}
        />
      )}
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
                src={viewportLogoUrl}
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

      {isCreatePage && !loadingCharacters && !user && <AuthGate onAuthenticated={authenticated} />}

      {isCreatePage && (
        <CreateExperienceOverlay
          onAuthenticated={authenticated}
          onClose={() => window.location.assign("/")}
          onCreated={() => window.location.assign("/")}
          onPlay={selectCharacter}
          stage={!loadingCharacters && authorized && user ? "creator" : null}
          user={user}
        />
      )}

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
        <span>OpenSmash web</span>
        <span>React · Node · WASM on demand</span>
      </footer>

      <AdvancedModal
        authorized={authorized}
        debugMode={new URLSearchParams(window.location.search).get("debug") === "1"}
        open={advancedOpen}
        options={advancedOptions}
        onCancel={() => setAdvancedOpen(false)}
        onResetControllerTutorial={resetControllerTutorialFromAdvanced}
        onResetRom={resetRomFromAdvanced}
        onSave={saveAdvancedOptions}
      />

      {pendingAction && pendingAction.type !== "create" && (
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
