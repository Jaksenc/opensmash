import { useEffect, useRef, useState } from "react";
import introVideoUrl from "../visual/assets/intro-crt.mp4?url";
import logoFallbackUrl from "../visual/assets/smash-the-weights-logo.png?url";
import FlameAction from "./FlameAction.jsx";
import MobileControls from "./MobileControls.jsx";
import ModalPage from "./ModalPage.jsx";
import { startHomeRuntime } from "./visual-runtime.js";
import { transitionMediaVolume } from "./audio-envelope.js";

const MOBILE_CONTROLS_MEDIA = "(hover: none) and (pointer: coarse)";

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
  return (
    <div id="launch-flow-overlay" className="launch-flow-overlay" data-step="upload" data-mode="launch" hidden>
      <canvas id="launch-flow-canvas" className="launch-flow-canvas" aria-hidden="true" />
      <section className="launch-flow-step launch-flow-upload" role="dialog" aria-modal="true" aria-labelledby="launch-flow-title" aria-describedby="launch-flow-copy rom-filename-hint">
        <h2 id="launch-flow-title" className="visually-hidden">Play Smash the Weights</h2>
        <p id="launch-flow-copy" className="launch-flow-copy">
          To play Smash the Weights, upload your legally obtained Super Smash Bros. 64 ROM.
        </p>
        <div id="rom-filename-hint" className="launch-flow-rom-hint">
          <span className="launch-flow-rom-hint-label">These ROMs are normally named</span>
          <span className="launch-flow-rom-filenames">
            <code>Super Smash Bros. (USA).z64</code>
            <code>Super Smash Bros. (Europe) (En,Fr,De).z64</code>
            <code>Nintendo All-Star! Dairantou Smash Brothers (Japan).z64</code>
          </span>
        </div>
        <input id="rom-file-input" className="launch-flow-file-input" type="file" hidden accept=".zip,.z64,.n64,.v64,.rom,application/zip,application/octet-stream" />
        <FlameAction id="rom-upload-button" type="button">Upload ROM</FlameAction>
        <button id="launch-cancel-button" className="launch-flow-action launch-flow-cancel" type="button">Cancel</button>
        <p id="rom-form-error" className="launch-flow-error" role="alert" hidden />
      </section>
      <section id="launch-flow-controller-step" className="launch-flow-step launch-flow-controller" role="dialog" aria-modal="true" aria-labelledby="how-to-play-title" aria-describedby="launch-control-prompt" tabIndex="-1">
        <div className="launch-flow-controller-instructions">
          <h2 id="how-to-play-title" className="launch-flow-title launch-flow-how-title">How to play</h2>
          <p id="launch-control-prompt" className="launch-flow-control-prompt" aria-live="polite">Press each key on your keyboard to continue</p>
        </div>
        <ControllerCallouts />
        <FlameAction cellClassName="launch-flow-controls-close" id="controls-close-button" type="button">Close</FlameAction>
      </section>
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
  isFullscreen,
  launchFlowOpen,
  onAboutChange,
  onAdvanced,
  onCloseGame,
  onCreate,
  onFullscreen,
  onResetRom,
  onSignOut,
  onSound,
  pageError,
  ready,
  soundOn,
  user,
}) {
  const aboutCancelRef = useRef(null);
  const introVideoRef = useRef(null);
  const [introVideoPlaying, setIntroVideoPlaying] = useState(false);
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

  function toggleMobileControls(event) {
    if (!mobileLayout) return;
    event.stopPropagation();
    if (!engine) setMobileControlsPreview((visible) => !visible);
  }

  function toggleSurfacePower() {
    const video = introVideoRef.current;
    if (engine) {
      onCloseGame();
      if (video) {
        video.currentTime = 0;
        video.play().catch((error) => window.openSmashReactBridge?.reportError?.(error));
      }
      return;
    }
    if (!video) return;
    if (video.paused) {
      video.play().catch((error) => window.openSmashReactBridge?.reportError?.(error));
    } else {
      video.pause();
    }
  }

  const powerLabel = engine
    ? "Power off game"
    : introVideoPlaying ? "Pause intro video" : "Play intro video";

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
            <button className={`retro-site-link ${advancedActive ? "is-active" : ""}`} type="button" aria-haspopup="dialog" onClick={onAdvanced}>Advanced</button>
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
          </nav>
        </header>
        <section className="intro-video-stage" aria-label="Intro video">
          <div className={`game-surface-shell ${mobileControlsVisible ? "has-mobile-control-deck" : ""}`}>
            <div className={`intro-video-frame ${engine ? "is-game-running" : ""}`} ref={gameFrameRef}>
              <video
                ref={introVideoRef}
                id="intro-video"
                className="intro-video"
                src={introVideoUrl}
                muted={!soundOn}
                autoPlay
                loop
                playsInline
                preload="auto"
                aria-label="Super Weights Bros intro video"
                onPlay={() => setIntroVideoPlaying(true)}
                onPause={() => setIntroVideoPlaying(false)}
              />
              <img className="intro-video-rule-layer" alt="" aria-hidden="true" />
              <iframe ref={engineRef} id="intro-game-frame" className="intro-game-frame" src={engine?.src || "about:blank"} title={engine ? "OpenSmash game engine" : "Super Weights Bros game"} allow="autoplay; gamepad; fullscreen" />
              <div className="retro-game-tools" role="group" aria-label="Game controls">
                <button
                  id="game-close-button"
                  className="game-overlay-control is-power"
                  type="button"
                  aria-label={powerLabel}
                  aria-pressed={engine ? undefined : introVideoPlaying}
                  title={powerLabel}
                  onClick={toggleSurfacePower}
                >
                  <svg viewBox="0 0 24 24" aria-hidden="true">
                    <path d="M12 2.75v8.5" />
                    <path d="M7.15 5.55a8 8 0 1 0 9.7 0" />
                  </svg>
                </button>
                <button
                  className="game-overlay-control is-fullscreen"
                  type="button"
                  aria-label={isFullscreen ? "Exit fullscreen" : "Enter fullscreen"}
                  title={isFullscreen ? "Exit fullscreen" : "Enter fullscreen"}
                  onClick={onFullscreen}
                >
                  <svg viewBox="0 0 24 24" aria-hidden="true">
                    {isFullscreen ? (
                      <>
                        <path d="M9 3v6H3" />
                        <path d="M15 3v6h6" />
                        <path d="M9 21v-6H3" />
                        <path d="M15 21v-6h6" />
                      </>
                    ) : (
                      <>
                        <path d="M8 3H3v5" />
                        <path d="M16 3h5v5" />
                        <path d="M8 21H3v-5" />
                        <path d="M16 21h5v-5" />
                      </>
                    )}
                  </svg>
                </button>
                <button
                  className="game-overlay-control is-sound"
                  type="button"
                  aria-label={soundOn ? "Mute audio" : "Unmute audio"}
                  aria-pressed={soundOn}
                  title={soundOn ? "Mute audio" : "Unmute audio"}
                  onClick={onSound}
                >
                  <svg viewBox="0 0 24 24" aria-hidden="true">
                    <path d="M4 9.25h4l5-4v13.5l-5-4H4z" />
                    {soundOn ? (
                      <>
                        <path d="M16 8.25a5 5 0 0 1 0 7.5" />
                        <path d="M18.75 5.5a8.5 8.5 0 0 1 0 13" />
                      </>
                    ) : (
                      <>
                        <path d="m16.5 9 5 5" />
                        <path d="m21.5 9-5 5" />
                      </>
                    )}
                  </svg>
                </button>
              </div>
            </div>
            <MobileControls
              active={mobileControlsVisible}
              frameRef={engineRef}
              preview={previewMobileControls}
            />
          </div>
        </section>
        <div className="arena-surface"><div id="replica-grid" className="replica-grid" role="grid" aria-label="Search, create, and character roster" />{!ready && <p className="retro-roster-loading">Loading fighters…</p>}<p id="fighter-empty-state" className="fighter-empty-state" role="status" aria-live="polite" hidden /></div>
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
