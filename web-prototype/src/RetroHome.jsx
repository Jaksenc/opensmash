import { useEffect, useState } from "react";

let visualRuntimePromise;

function loadVisualStyles() {
  return new Promise((resolve, reject) => {
    const existing = document.getElementById("site-shell-styles");
    if (existing) {
      if (existing.sheet) resolve();
      else existing.addEventListener("load", resolve, { once: true });
      return;
    }
    const link = document.createElement("link");
    link.id = "site-shell-styles";
    link.rel = "stylesheet";
    link.href = "/visual/site-shell.css";
    link.addEventListener("load", resolve, { once: true });
    link.addEventListener("error", () => reject(new Error("Could not load the site visual system")), { once: true });
    document.head.append(link);
  });
}

function loadModule(src) {
  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.type = "module";
    script.src = src;
    script.addEventListener("load", resolve, { once: true });
    script.addEventListener("error", () => reject(new Error(`Could not load ${src}`)), { once: true });
    document.body.append(script);
  });
}

function startVisualRuntime() {
  visualRuntimePromise ||= loadVisualStyles().then(() => [
    "/visual/grid-replica.js?v=20260901-react1",
    "/visual/logo-stage.js?v=20260901-react1",
    "/visual/crt-viewport.js?v=20260901-react1",
    "/visual/game-launcher.js?v=20260901-react1",
    "/visual/site-hardware.js?v=20260901-react1",
  ].reduce((ready, src) => ready.then(() => loadModule(src)), Promise.resolve()));
  return visualRuntimePromise;
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

function LaunchFlow() {
  return (
    <div id="launch-flow-overlay" className="launch-flow-overlay" data-step="upload" data-mode="launch" hidden>
      <canvas id="launch-flow-canvas" className="launch-flow-canvas" aria-hidden="true" />
      <section className="launch-flow-step launch-flow-upload" role="dialog" aria-modal="true" aria-labelledby="launch-flow-title" aria-describedby="launch-flow-copy">
        <h2 id="launch-flow-title" className="visually-hidden">Play Smash the Weights</h2>
        <p id="launch-flow-copy" className="launch-flow-copy">
          To play Smash the Weights upload your legally obtained Super Smash Bros 64 ROM. It is normalized and hashed locally and never uploaded.
        </p>
        <input id="rom-file-input" className="launch-flow-file-input" type="file" hidden accept=".zip,.z64,.n64,.v64,.rom,application/zip,application/octet-stream" />
        <div className="launch-flow-fire-cell flame-bridge-cell">
          <button id="rom-upload-button" className="launch-flow-action" type="button">Upload ROM</button>
        </div>
        <button id="launch-cancel-button" className="launch-flow-action launch-flow-cancel" type="button">Cancel</button>
        <p id="rom-form-error" className="launch-flow-error" role="alert" hidden />
      </section>
      <section id="launch-flow-controller-step" className="launch-flow-step launch-flow-controller" role="dialog" aria-modal="true" aria-labelledby="how-to-play-title" aria-describedby="launch-control-prompt" tabIndex="-1">
        <div className="launch-flow-controller-instructions">
          <h2 id="how-to-play-title" className="launch-flow-title launch-flow-how-title">How to play</h2>
          <p id="launch-control-prompt" className="launch-flow-control-prompt" aria-live="polite">Press each key on your keyboard to continue</p>
        </div>
        <ControllerCallouts />
        <div className="launch-flow-fire-cell flame-bridge-cell launch-flow-controls-close">
          <button id="controls-close-button" className="launch-flow-action" type="button">Close</button>
        </div>
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
  advancedActive,
  authorized,
  engine,
  engineRef,
  gameFrameRef,
  onAdvanced,
  onClearVerification,
  onFullscreen,
  onSignOut,
  onSound,
  pageError,
  ready,
  soundOn,
  user,
}) {
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    document.documentElement.classList.add("is-direct-site");
    document.body.classList.add("retro-home");
    loadVisualStyles().catch((error) => window.openSmashReactBridge?.reportError?.(error));
    return () => {
      document.documentElement.classList.remove("is-direct-site");
      document.body.classList.remove("retro-home");
    };
  }, []);

  useEffect(() => {
    if (!ready) return;
    startVisualRuntime().catch((error) => window.openSmashReactBridge?.reportError?.(error));
  }, [ready]);

  useEffect(() => {
    if (!menuOpen) return undefined;
    const previousOverflow = document.body.style.overflow;
    const closeOnEscape = (event) => {
      if (event.key === "Escape") setMenuOpen(false);
    };
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [menuOpen]);

  function requestGame(actionType) {
    setMenuOpen(false);
    window.setTimeout(() => window.gameLauncher?.request(actionType), 0);
  }

  return (
    <>
      <button id="rom-reset-button" className="rom-reset-button" type="button" hidden={!authorized} aria-label="Remove verified ROM and reset the game">Reset ROM</button>
      {pageError && <p className="retro-page-error" role="alert">{pageError}</p>}
      <main className="arena-shell" aria-label="OpenSmash character grid">
        <section className="intro-video-stage" aria-label="Intro video">
          <div className={`intro-video-frame ${engine ? "is-game-running" : ""}`} ref={gameFrameRef}>
            <video id="intro-video" className="intro-video" src="/assets/intro-crt.mp4" muted={!soundOn} autoPlay loop playsInline preload="auto" aria-label="Super Weights Bros intro video" />
            <canvas className="intro-video-rule-layer" aria-hidden="true" />
            <div id="hero-logo-stage" className="intro-video-logo" aria-label="Animated Smash the Weights logo">
              <img className="hero-logo-fallback" src="/assets/smash-the-weights-logo.png" alt="" aria-hidden="true" draggable="false" />
              <canvas id="hero-logo-canvas" className="hero-logo-canvas" aria-hidden="true" />
            </div>
            <iframe ref={engineRef} id="intro-game-frame" className="intro-game-frame" src={engine?.src || "about:blank"} title={engine ? "OpenSmash game engine" : "Super Weights Bros game"} allow="autoplay; gamepad; fullscreen" />
            <div className="retro-game-tools">
              <button id="game-fullscreen-button" className="game-close-button" type="button" onClick={onFullscreen}>Fullscreen</button>
              <button id="game-close-button" className="game-close-button" type="button">Close game</button>
            </div>
          </div>
        </section>
        <section id="site-menu-bridge" className="site-menu-bridge" aria-label="Site information and settings">
          <div className="flame-bridge-cell"><button id="about-menu-button" className="flame-bridge-action site-menu-button" type="button" onClick={() => setMenuOpen(true)}>About</button></div>
          <div className="flame-bridge-cell"><button id="controls-menu-button" className="flame-bridge-action site-menu-button" type="button" aria-haspopup="dialog" aria-controls="launch-flow-controller-step">Controls</button></div>
          <div className="flame-bridge-cell"><button className={`flame-bridge-action site-menu-button ${advancedActive ? "is-active" : ""}`} type="button" aria-haspopup="dialog" onClick={onAdvanced}>Advanced</button></div>
          <canvas className="site-menu-rule-layer" aria-hidden="true" />
        </section>
        <div id="flame-bridge" className="flame-bridge" aria-label="Fighter search">
          <div className="flame-bridge-cell"><input id="fighter-search" className="flame-bridge-search" type="search" placeholder="Search Fighters…" aria-label="Search fighters" autoComplete="off" spellCheck="false" /></div>
          <canvas className="flame-bridge-rule-layer" aria-hidden="true" />
        </div>
        <div className="arena-surface"><div id="replica-grid" className="replica-grid" role="grid" aria-label="Create fighter and character roster" />{!ready && <p className="retro-roster-loading">Loading fighters…</p>}<p id="fighter-empty-state" className="fighter-empty-state" role="status" aria-live="polite" hidden /></div>
        <span id="replica-metrics" hidden>Building 200-cell grid…</span>
        <section className="font-bench" hidden aria-labelledby="font-bench-title"><h2 id="font-bench-title">Tile-caption font · A–Z</h2><div id="font-glyph-grid" className="font-glyph-grid" /><footer className="font-bench-footer"><span id="font-bench-detail">Loading…</span><output id="font-bench-score">Grading…</output></footer></section>
      </main>

      {menuOpen && (
        <div className="retro-menu-backdrop" role="presentation" onMouseDown={() => setMenuOpen(false)}>
          <section className="retro-menu-modal" role="dialog" aria-modal="true" aria-labelledby="retro-menu-title" onMouseDown={(event) => event.stopPropagation()}>
            <button className="retro-menu-close" type="button" onClick={() => setMenuOpen(false)} aria-label="Close">×</button>
            <p className="retro-menu-kicker">OpenSmash</p>
            <h2 id="retro-menu-title">Smash the weights</h2>
            <p>Pick any fighter for a quick match, or choose another way into the browser build.</p>
            <div className="retro-menu-actions">
              <button type="button" onClick={() => requestGame('select')}>Character select</button>
              <button type="button" onClick={() => requestGame('start')}>Play from start</button>
              <a href="/create">Create fighter</a>
              <button id="sound-toggle" type="button" aria-pressed={soundOn} onClick={onSound}>Sound <span id="sound-toggle-state">{soundOn ? 'On' : 'Off'}</span></button>
              {engine && <button type="button" onClick={onFullscreen}>Fullscreen game</button>}
              {user && <button type="button" onClick={onSignOut}>{user.displayName || user.email || 'Account'} · Sign out</button>}
              {authorized && <button type="button" onClick={onClearVerification}>Clear ROM verification</button>}
            </div>
            <p className="retro-rom-status">{authorized ? 'ROM verified for this browser' : 'ROM bytes stay on this device'}</p>
          </section>
        </div>
      )}

      <LaunchFlow />
      <GodRay />
      <RuntimeControls />
    </>
  );
}
