import { useEffect, useLayoutEffect, useRef, useState } from "react";
import introVideoUrl from "../visual/assets/intro-crt.mp4?url";
import logoFallbackUrl from "../visual/assets/smash-the-weights-logo.png?url";
import FlameAction from "./FlameAction.jsx";
import MobileControls from "./MobileControls.jsx";
import ModalPage from "./ModalPage.jsx";
import { startHomeRuntime } from "./visual-runtime.js";
import { transitionMediaVolume } from "./audio-envelope.js";

const MOBILE_CONTROLS_MEDIA = "(hover: none) and (pointer: coarse)";
const ROM_FILENAME = "Super Smash Bros. (USA).z64";
const COPY_TOAST_DURATION_MS = 2_000;

function mobileControlsRequested() {
  return new URLSearchParams(window.location.search).has("mobileControls");
}

function ControllerCallouts() {
  return (
    <div id="controller-callouts" className="controller-callouts" aria-label="Keyboard controls">
      <svg id="controller-callout-lines" className="controller-callout-lines" aria-hidden="true">
        {['stick', 'a', 'b', 'z', 'left-bumper', 'right-bumper'].map((control) => (
          <g data-control-line={control} key={control}><line /><circle r="3" /></g>
        ))}
      </svg>
      <div className="controller-callout" data-control-callout="stick" aria-label="W A S D: joystick">
        <span className="controller-key-cluster" aria-hidden="true">
          {['w', 'a', 's', 'd'].map((key) => (
            <kbd className="controller-keycap" data-control-key={key} key={key}>{key.toUpperCase()}</kbd>
          ))}
        </span>
      </div>
      {[
        ['a', 'j', 'J: A button'],
        ['b', 'k', 'K: B button'],
        ['z', 'l', 'L: Z button'],
        ['left-bumper', 'i', 'I: left bumper'],
        ['right-bumper', 'o', 'O: right bumper'],
      ].map(([control, key, label]) => (
        <div className="controller-callout" data-control-callout={control} aria-label={label} key={control}>
          <kbd className="controller-keycap" data-control-key={key} aria-hidden="true">{key.toUpperCase()}</kbd>
        </div>
      ))}
    </div>
  );
}

export function LaunchFlow() {
  const [copyToastId, setCopyToastId] = useState(0);
  const copyToastTimerRef = useRef(0);

  useEffect(() => () => window.clearTimeout(copyToastTimerRef.current), []);

  async function copyRomFilename() {
    try {
      await navigator.clipboard.writeText(ROM_FILENAME);
    } catch {
      const fallback = document.createElement("textarea");
      fallback.value = ROM_FILENAME;
      fallback.setAttribute("readonly", "");
      fallback.style.position = "fixed";
      fallback.style.opacity = "0";
      document.body.append(fallback);
      fallback.select();
      const copied = document.execCommand("copy");
      fallback.remove();
      if (!copied) return;
    }

    window.clearTimeout(copyToastTimerRef.current);
    setCopyToastId((current) => current + 1);
    copyToastTimerRef.current = window.setTimeout(() => setCopyToastId(0), COPY_TOAST_DURATION_MS);
  }

  return (
    <div id="launch-flow-overlay" className="launch-flow-overlay" data-step="upload" data-mode="launch" hidden>
      <canvas id="launch-flow-canvas" className="launch-flow-canvas" aria-hidden="true" />
      <section className="launch-flow-step launch-flow-upload" role="dialog" aria-modal="true" aria-labelledby="launch-flow-title" aria-describedby="launch-flow-copy rom-filename-hint">
        <h2 id="launch-flow-title" className="visually-hidden">Play Smash the Weights</h2>
        <p id="launch-flow-copy" className="launch-flow-copy">
          To play Smash the Weights, choose your legally obtained USA-release Super Smash Bros. 64 ROM. It never
          leaves your device.
        </p>
        <div id="rom-filename-hint" className="launch-flow-rom-hint">
          <span className="launch-flow-rom-hint-label">The file is usually named</span>{" "}
          <button
            className="launch-flow-rom-copy"
            type="button"
            aria-label={`Copy ${ROM_FILENAME} to clipboard`}
            onClick={copyRomFilename}
          >
            <code>{ROM_FILENAME}</code>
          </button>
        </div>
        <input id="rom-file-input" className="launch-flow-file-input" type="file" hidden accept=".z64,.n64,.v64,.rom,.zip" />
        <FlameAction id="rom-upload-button" type="button">Choose ROM</FlameAction>
        <button id="launch-cancel-button" className="launch-flow-action launch-flow-cancel" type="button">Cancel</button>
        <button id="rom-more-options-button" className="launch-flow-text-link" type="button" aria-expanded="false" aria-controls="rom-more-options">Other options</button>
        <div className="launch-flow-more-anchor">
        <div id="rom-more-options" className="launch-flow-more-options" hidden>
          <form id="rom-handoff-panel" className="launch-flow-option launch-flow-handoff">
            <p className="launch-flow-more-copy">
              Have the ROM on your computer or another device? Open this site there, choose
              {" "}<strong>Advanced → Send ROM to another device</strong>, and enter the code it shows here.
            </p>
            <div className="launch-flow-handoff-row">
              <input
                id="rom-handoff-code"
                className="launch-flow-handoff-input"
                type="text"
                inputMode="text"
                autoComplete="one-time-code"
                autoCapitalize="characters"
                autoCorrect="off"
                spellCheck="false"
                maxLength="8"
                placeholder="CODE"
                aria-label="Handoff code from the other device"
              />
              <button id="rom-handoff-connect" className="launch-flow-action launch-flow-secondary" type="submit">Connect</button>
            </div>
            <p id="rom-handoff-status" className="launch-flow-status" aria-live="polite" hidden />
          </form>
        </div>
        </div>
        <p id="rom-form-error" className="launch-flow-error" role="alert" hidden />
      </section>
      <section id="launch-flow-controller-step" className="launch-flow-step launch-flow-controller" role="dialog" aria-modal="true" aria-labelledby="how-to-play-title" aria-describedby="launch-control-prompt" tabIndex="-1">
        <div className="launch-flow-controller-instructions">
          <h2 id="how-to-play-title" className="launch-flow-title launch-flow-how-title">How to play</h2>
          <p id="launch-control-prompt" className="launch-flow-control-prompt" aria-live="polite">Press each key on your keyboard to continue</p>
        </div>
        <ControllerCallouts />
        <FlameAction cellClassName="launch-flow-controls-skip launch-flow-controls-bottom" className="launch-flow-skip" id="launch-control-skip" type="button" hidden>Skip</FlameAction>
        <FlameAction cellClassName="launch-flow-controls-close launch-flow-controls-bottom" id="controls-close-button" type="button">Close</FlameAction>
      </section>
      {copyToastId > 0 && (
        <p key={copyToastId} className="launch-flow-copy-toast" role="status" aria-live="polite">
          Copied to Clipboard
        </p>
      )}
    </div>
  );
}

function GodRay() {
  return (
    <svg id="hardware-god-ray" aria-hidden="true" preserveAspectRatio="none">
      <defs>
        <linearGradient id="god-ray-outer-gradient" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#fffde8" stopOpacity=".08" /><stop offset=".34" stopColor="#fff8d4" stopOpacity=".22" /><stop offset=".5" stopColor="#ffeab1" stopOpacity=".15" /><stop offset="1" stopColor="#e5bd76" stopOpacity="0" /></linearGradient>
        <linearGradient id="god-ray-middle-gradient" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#fffff3" stopOpacity=".12" /><stop offset=".34" stopColor="#fffde1" stopOpacity=".28" /><stop offset=".56" stopColor="#ffe6aa" stopOpacity=".13" /><stop offset="1" stopColor="#dba65b" stopOpacity="0" /></linearGradient>
        <linearGradient id="god-ray-core-gradient" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#ffffff" stopOpacity=".12" /><stop offset=".3" stopColor="#fffef0" stopOpacity=".32" /><stop offset=".48" stopColor="#fff2c8" stopOpacity=".18" /><stop offset=".84" stopColor="#f2c980" stopOpacity="0" /></linearGradient>
        <radialGradient id="god-ray-halo-gradient"><stop offset="0" stopColor="#ffffff" stopOpacity=".38" /><stop offset=".28" stopColor="#fffbe2" stopOpacity=".22" /><stop offset="1" stopColor="#f3c97e" stopOpacity="0" /></radialGradient>
        <radialGradient id="god-ray-haze-gradient"><stop offset="0" stopColor="#fff5d1" stopOpacity=".17" /><stop offset=".44" stopColor="#f2d098" stopOpacity=".08" /><stop offset="1" stopColor="#c58d46" stopOpacity="0" /></radialGradient>
        <filter id="god-ray-blur-wide" x="-40%" y="-20%" width="180%" height="140%"><feGaussianBlur stdDeviation="28" /></filter>
        <filter id="god-ray-blur-medium" x="-30%" y="-16%" width="160%" height="132%"><feGaussianBlur stdDeviation="12" /></filter>
        <filter id="god-ray-blur-tight" x="-20%" y="-12%" width="140%" height="124%"><feGaussianBlur stdDeviation="4" /></filter>
      </defs>
      <path id="god-ray-outer" className="god-ray-outer" />
      <path id="god-ray-middle" className="god-ray-middle" />
      <path id="god-ray-core" className="god-ray-core" />
      <ellipse id="god-ray-console-haze" className="god-ray-console-haze" />
      <ellipse id="god-ray-cartridge-halo" className="god-ray-cartridge-halo" />
    </svg>
  );
}

function RuntimeControls() {
  return (
    <>
      <aside id="hardware-inset" data-cartridge-state="free" aria-label="Television, interactive cartridge, and console">
        <div id="tv-control" aria-hidden="true" />
        <button id="cartridge-control" type="button" aria-label="Drag the cartridge into the console"><span className="visually-hidden">Drag the cartridge into the console</span></button>
        <div id="console-control" aria-hidden="true" />
      </aside>
      <details id="shader-tuner" hidden>
        <summary>Shader tuning</summary>
        <div className="shader-tuner-body"><button id="shader-reset" type="button">Reset defaults</button></div>
      </details>
      <details id="crt-tuner" hidden><summary>CRT viewport tuning</summary><div className="crt-tuner-body"><button type="button" data-crt-reset>Reset defaults</button></div></details>
      <canvas id="glove-canvas" />
      <canvas id="crt-viewport-canvas" aria-hidden="true" />
    </>
  );
}

export default function RetroHome({
  aboutOpen,
  advancedActive,
  authorized,
  developmentMode,
  engine,
  engineRef,
  gameFrameRef,
  gamepadCount = 0,
  immersive = false,
  isFullscreen,
  launchFlowOpen,
  onAboutChange,
  onAdvanced,
  onCreate,
  onFullscreen,
  onTrailerControl,
  onResetRom,
  onSignOut,
  pageError,
  ready,
  soundOn,
  trailerCinematic = false,
  trailerEngineReady = false,
  trailerEngineStarted = false,
  trailerMode = false,
  user,
}) {
  const aboutCancelRef = useRef(null);
  const introVideoRef = useRef(null);
  const moreMenuRef = useRef(null);
  const gameSurfaceRef = useRef(null);
  const cinematicFirstRectRef = useRef(null);
  const cinematicAnimationRef = useRef(null);
  const [mobileLayout, setMobileLayout] = useState(() => (
    mobileControlsRequested() || window.matchMedia(MOBILE_CONTROLS_MEDIA).matches
  ));
  const [mobileControlsPreview, setMobileControlsPreview] = useState(false);
  const previewMobileControls = !engine && mobileLayout && mobileControlsPreview;
  const mobileControlsVisible = mobileLayout && (Boolean(engine) || previewMobileControls);

  useEffect(() => {
    const showNativeCursor = new URLSearchParams(window.location.search).has("showCursor");
    const mobileControlsMedia = window.matchMedia(MOBILE_CONTROLS_MEDIA);
    const syncMobileControls = () => {
      const enabled = mobileControlsRequested() || mobileControlsMedia.matches;
      setMobileLayout(enabled);
      document.body.classList.toggle("uses-mobile-controls", enabled);
    };
    document.documentElement.classList.add("is-direct-site");
    document.body.classList.add("retro-home");
    document.body.classList.toggle("show-native-cursor", showNativeCursor);
    syncMobileControls();
    if (mobileControlsMedia.addEventListener) {
      mobileControlsMedia.addEventListener("change", syncMobileControls);
    } else {
      mobileControlsMedia.addListener?.(syncMobileControls);
    }
    return () => {
      document.documentElement.classList.remove("is-direct-site");
      document.body.classList.remove("retro-home", "show-native-cursor", "uses-mobile-controls");
      if (mobileControlsMedia.removeEventListener) {
        mobileControlsMedia.removeEventListener("change", syncMobileControls);
      } else {
        mobileControlsMedia.removeListener?.(syncMobileControls);
      }
    };
  }, []);

  useLayoutEffect(() => {
    document.body.classList.toggle("is-trailer-mode", trailerMode);
    document.body.classList.toggle("is-trailer-cinematic", trailerMode && trailerCinematic);
    return () => {
      document.body.classList.remove("is-trailer-mode", "is-trailer-cinematic");
    };
  }, [trailerCinematic, trailerMode]);

  useLayoutEffect(() => {
    const first = cinematicFirstRectRef.current;
    const surface = gameSurfaceRef.current;
    cinematicFirstRectRef.current = null;
    if (!first || !surface) return undefined;

    const last = surface.getBoundingClientRect();
    const scaleX = last.width ? first.width / last.width : 1;
    const scaleY = last.height ? first.height / last.height : 1;
    cinematicAnimationRef.current?.cancel();
    const animation = surface.animate([
      {
        transformOrigin: "top left",
        transform: `translate(${first.left - last.left}px, ${first.top - last.top}px) scale(${scaleX}, ${scaleY})`,
      },
      { transformOrigin: "top left", transform: "none" },
    ], {
      duration: 1050,
      easing: "cubic-bezier(.2,.82,.2,1)",
      fill: "both",
    });
    cinematicAnimationRef.current = animation;
    animation.finished.catch(() => {}).finally(() => {
      if (cinematicAnimationRef.current === animation) cinematicAnimationRef.current = null;
    });
    return () => animation.cancel();
  }, [trailerCinematic]);

  function runTrailerControl() {
    const surface = gameSurfaceRef.current;
    if (surface) cinematicFirstRectRef.current = surface.getBoundingClientRect();
    if (trailerCinematic) window.scrollTo({ top: 0, left: 0, behavior: "instant" });
    onTrailerControl?.();
  }

  useEffect(() => {
    if (!ready) return;
    startHomeRuntime().catch((error) => window.openSmashReactBridge?.reportError?.(error));
  }, [ready]);

  useEffect(() => {
    document.body.classList.toggle("is-game-running", Boolean(engine));
    return () => document.body.classList.remove("is-game-running");
  }, [engine]);

  useEffect(() => {
    const video = introVideoRef.current;
    if (!video) return undefined;
    return transitionMediaVolume(video, launchFlowOpen || engine ? 0 : 1);
  }, [engine, launchFlowOpen]);

  // Browsers only guarantee muted autoplay. The element always starts muted;
  // when sound is on we try to unmute right away (allowed on return visits in
  // Chrome) and otherwise unmute on the first gesture anywhere on the page.
  useEffect(() => {
    const video = introVideoRef.current;
    if (!video) return undefined;
    if (!soundOn) {
      video.muted = true;
      return undefined;
    }
    let cancelled = false;
    const gestureEvents = ["pointerdown", "keydown", "touchstart"];
    const removeGestureListeners = () => {
      for (const type of gestureEvents) document.removeEventListener(type, unmuteOnGesture, true);
    };
    function unmuteOnGesture() {
      removeGestureListeners();
      if (cancelled) return;
      video.muted = false;
      if (video.paused && !engine) {
        video.play().catch(() => { video.muted = true; });
      }
    }
    const tryUnmute = async () => {
      video.muted = false;
      try {
        await video.play();
        if (cancelled) return;
        if (video.muted) throw new Error("still muted");
      } catch {
        if (cancelled) return;
        video.muted = true;
        // Keep the muted loop running while we wait for a gesture.
        video.play().catch(() => {});
        for (const type of gestureEvents) document.addEventListener(type, unmuteOnGesture, true);
      }
    };
    tryUnmute();
    return () => {
      cancelled = true;
      removeGestureListeners();
    };
  }, [soundOn]);

  function toggleMobileControls(event) {
    if (!mobileLayout) return;
    event.stopPropagation();
    if (!engine) setMobileControlsPreview((visible) => !visible);
  }

  function closeMoreMenu() {
    moreMenuRef.current?.removeAttribute("open");
  }

  function openControlsFromMore() {
    closeMoreMenu();
    document.getElementById("controls-menu-button")?.click();
  }

  function openAdvancedFromMore() {
    closeMoreMenu();
    onAdvanced();
  }

  function resetRomFromMore() {
    closeMoreMenu();
    onResetRom();
  }

  return (
    <>
      {pageError && <p className="retro-page-error" role="alert">{pageError}</p>}
      <main className="arena-shell" aria-label="OpenSmash character grid">
        <header className="retro-site-header">
          <div id="hero-logo-stage" className="retro-site-logo" aria-label="Smash the Weights">
            <img className="hero-logo-fallback" src={logoFallbackUrl} alt="Smash the Weights" draggable="false" />
            <canvas id="hero-logo-canvas" className="hero-logo-canvas" aria-hidden="true" />
          </div>
          <nav className="retro-site-nav" aria-label="Site information and settings">
            {gamepadCount > 0 && (
              <button
                className="retro-site-link retro-site-pads"
                type="button"
                aria-haspopup="dialog"
                aria-label={`${gamepadCount} controller${gamepadCount === 1 ? "" : "s"} connected. Open controller settings.`}
                title={`${gamepadCount} controller${gamepadCount === 1 ? "" : "s"} connected`}
                onClick={onAdvanced}
              >
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M7.5 6.5h9a4.5 4.5 0 0 1 4.5 4.5v2.2a4.3 4.3 0 0 1-7.6 2.8L12 14.6l-1.4 1.4A4.3 4.3 0 0 1 3 13.2V11a4.5 4.5 0 0 1 4.5-4.5z" />
                  <path d="M7.5 9.5v4M5.5 11.5h4" />
                  <path d="M16.2 10.6h.01M18.6 12.6h.01" />
                </svg>
                <span>{gamepadCount}</span>
              </button>
            )}
            <button
              className="retro-site-link"
              type="button"
              aria-haspopup="dialog"
              aria-controls="about-overlay"
              aria-expanded={aboutOpen}
              onClick={() => onAboutChange(true)}
            >
              About
            </button>
            <button
              id="controls-menu-button"
              className={`retro-site-link ${mobileLayout && mobileControlsVisible ? "is-active" : ""}`}
              type="button"
              aria-haspopup={mobileLayout ? undefined : "dialog"}
              aria-controls={mobileLayout ? "touch-control-deck" : "launch-flow-controller-step"}
              aria-expanded={mobileLayout ? mobileControlsVisible : undefined}
              aria-pressed={mobileLayout ? mobileControlsVisible : undefined}
              onClickCapture={toggleMobileControls}
            >
              Controls
            </button>
            <button className={`retro-site-link retro-site-advanced-button ${advancedActive ? "is-active" : ""}`} type="button" aria-haspopup="dialog" onClick={onAdvanced}>Settings</button>
            <details className="retro-site-more" ref={moreMenuRef}>
              <summary className="retro-site-link">More</summary>
              <div className="retro-site-more-menu" role="menu">
                <button className="retro-site-link" type="button" role="menuitem" onClick={openControlsFromMore}>Controls</button>
                <button className={`retro-site-link ${advancedActive ? "is-active" : ""}`} type="button" role="menuitem" onClick={openAdvancedFromMore}>Settings</button>
                {developmentMode && authorized && (
                  <button className="retro-site-link retro-site-dev-link" type="button" role="menuitem" onClick={resetRomFromMore}>Reset ROM</button>
                )}
              </div>
            </details>
            {developmentMode && authorized && (
              <button
                className="retro-site-link retro-site-dev-link"
                type="button"
                onClick={onResetRom}
                aria-label="Remove verified ROM and reset the game"
              >
                Reset ROM
              </button>
            )}
            <a
              className="retro-site-link retro-discord-link"
              href="https://discord.gg/qYBbGmwBhr"
              target="_blank"
              rel="noreferrer"
              aria-label="Join the OpenSmash community on Discord"
            >
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M19.6 5.3A18 18 0 0 0 15.3 4l-.5 1a14.7 14.7 0 0 0-5.6 0l-.5-1a18 18 0 0 0-4.3 1.3C1.7 9.4 1 13.4 1.4 17.4a17.3 17.3 0 0 0 5.3 2.7l1.3-1.8a10.8 10.8 0 0 1-2-1l.5-.4a12.6 12.6 0 0 0 11 0l.5.4a11 11 0 0 1-2 1l1.3 1.8a17.3 17.3 0 0 0 5.3-2.7c.5-4.6-.8-8.5-3-12.1ZM8.5 15.2c-1.3 0-2.3-1.2-2.3-2.7s1-2.7 2.3-2.7 2.3 1.2 2.3 2.7-1 2.7-2.3 2.7Zm7 0c-1.3 0-2.3-1.2-2.3-2.7s1-2.7 2.3-2.7 2.3 1.2 2.3 2.7-1 2.7-2.3 2.7Z" />
              </svg>
              <span>Join Discord</span>
            </a>
          </nav>
        </header>
        <section className="intro-video-stage" aria-label="Intro video">
          <div
            ref={gameSurfaceRef}
            className={`game-surface-shell ${mobileControlsVisible ? "has-mobile-control-deck" : ""} ${immersive ? "is-immersive" : ""} ${trailerCinematic ? "is-cinematic" : ""}`}
          >
            <div className={`intro-video-frame ${engine ? "is-game-running" : ""}`} ref={gameFrameRef}>
              <video
                ref={introVideoRef}
                id="intro-video"
                className="intro-video"
                src={introVideoUrl}
                muted
                autoPlay
                loop
                playsInline
                preload="auto"
                aria-label="Super Weights Bros intro video"
              />
              <img className="intro-video-rule-layer" alt="" aria-hidden="true" />
              <iframe ref={engineRef} id="intro-game-frame" className="intro-game-frame" src={engine?.src || "about:blank"} title={engine ? "OpenSmash game engine" : "Super Weights Bros game"} allow="autoplay; gamepad; fullscreen" />
              <button
                className="game-fullscreen-control"
                type="button"
                aria-label={isFullscreen ? "Exit fullscreen" : "Enter fullscreen"}
                title={isFullscreen ? "Exit fullscreen" : "Enter fullscreen"}
                onClick={onFullscreen}
              >
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  {isFullscreen ? (
                    <>
                      <path d="m4 4 6 6m0-5v5H5" />
                      <path d="m20 20-6-6m0 5v-5h5" />
                    </>
                  ) : (
                    <>
                      <path d="M10 10 4 4m0 6V4h6" />
                      <path d="m14 14 6 6m0-6v6h-6" />
                    </>
                  )}
                </svg>
              </button>
            </div>
            {trailerMode && trailerCinematic && (
              <button
                className={`trailer-cinematic-control ${trailerEngineStarted ? "is-reveal" : ""}`}
                type="button"
                disabled={!trailerEngineReady}
                onClick={runTrailerControl}
              >
                {!trailerEngineReady
                  ? "Loading intro…"
                  : trailerEngineStarted
                    ? "Reveal website"
                    : "Start capture"}
              </button>
            )}
            <MobileControls
              active={mobileControlsVisible}
              frameRef={engineRef}
              preview={previewMobileControls}
            />
          </div>
        </section>
        <div className="arena-surface"><div id="replica-grid" className="replica-grid" role="grid" aria-label="Search, create, and character roster" />{!ready && <p className="retro-roster-loading">Loading fighters…</p>}<p id="fighter-empty-state" className="fighter-empty-state" role="status" aria-live="polite" hidden /><p id="fighter-pick-prompt" className="fighter-pick-prompt" role="status" aria-live="polite" hidden /></div>
        <span id="replica-metrics" hidden>Building 200-cell grid…</span>
      </main>

      <ModalPage
        id="about-overlay"
        className="about-overlay"
        bodyClass="is-about-open"
        initialFocusRef={aboutCancelRef}
        onRequestClose={() => onAboutChange(false)}
        open={aboutOpen}
        role="presentation"
      >
        {(close) => (
          <section
            className="modal-page-surface about-screen"
            role="dialog"
            aria-modal="true"
            aria-labelledby="about-title"
            aria-describedby="about-copy"
          >
            <div className="about-content">
              <h2 id="about-title" className="launch-flow-title about-title">About</h2>
              <div id="about-copy" className="about-copy">
                <p className="launch-flow-copy">
                  OpenSmash is a fan-made browser port of Super Smash Bros. for the Nintendo 64 which allows you to
                  create custom fighters and play them inside the original game.
                </p>
                <p className="launch-flow-copy">You must supply a legally obtained copy of the game ROM to play.</p>
                <p className="launch-flow-copy">Your ROM and its assets stay on your device. Nothing is uploaded.</p>
                <p className="launch-flow-copy about-legal">
                  OpenSmash is not affiliated with, endorsed by, or sponsored by Nintendo. Super Smash Bros., Nintendo
                  64, and all related characters, names, and marks are trademarks of Nintendo and their respective
                  owners.
                </p>
              </div>
              <button
                ref={aboutCancelRef}
                className="launch-flow-action launch-flow-cancel about-cancel"
                type="button"
                onClick={() => close()}
              >
                Cancel
              </button>
            </div>
          </section>
        )}
      </ModalPage>

      <LaunchFlow />
      <GodRay />
      <RuntimeControls />
    </>
  );
}
