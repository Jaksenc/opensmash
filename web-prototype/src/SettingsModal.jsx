import { useEffect, useRef, useState } from "react";
import ModalPage from "./ModalPage.jsx";
import { choiceForEntry, portOptions } from "../shared/controller-ports.js";
import {
  BOOT_MODES,
  CHARACTER_MESHES,
  DEFAULT_ADVANCED_OPTIONS,
  OPPONENT_LEVELS,
  STAGES,
  controllerPlan,
  normalizeAdvancedOptions,
} from "./launch-options.js";

export default function SettingsModal({
  authorized,
  debugMode,
  gamepads = [],
  open,
  options,
  soundOn,
  onCancel,
  onOptionsChange,
  onRestoreDefaults,
  onResetControllerTutorial,
  onResetRom,
  onSendRom,
  onReceiveRom,
  onSound,
}) {
  const [draft, setDraft] = useState(options);
  const [page, setPage] = useState("main");
  const mainFirstRef = useRef(null);
  const gameplayFirstRef = useRef(null);
  const controllersFirstRef = useRef(null);
  const portPlan = controllerPlan(draft, gamepads);
  const humanPorts = portPlan.filter((entry) => entry && entry.kind !== "none").length;

  useEffect(() => {
    if (open) {
      setDraft(options);
      setPage("main");
    }
  }, [open]);

  useEffect(() => {
    if (!open) return undefined;
    const focusFrame = window.requestAnimationFrame(() => {
      if (page === "gameplay") gameplayFirstRef.current?.focus();
      else if (page === "controllers") controllersFirstRef.current?.focus();
      else mainFirstRef.current?.focus();
    });
    return () => window.cancelAnimationFrame(focusFrame);
  }, [open, page]);

  function update(key, value) {
    const next = { ...draft, [key]: value };
    setDraft(next);
    onOptionsChange(next);
  }

  function updatePort(port, value) {
    const ports = [...(draft.ports ?? DEFAULT_ADVANCED_OPTIONS.ports)];
    ports[port] = value;
    const next = { ...draft, ports };
    setDraft(next);
    onOptionsChange(next);
  }

  function restoreDefaults() {
    const defaults = normalizeAdvancedOptions(DEFAULT_ADVANCED_OPTIONS);
    setDraft(defaults);
    onRestoreDefaults(defaults);
  }

  const title = page === "gameplay"
    ? "Gameplay Options"
    : page === "controllers" ? "Keyboard & Controllers" : "Settings";

  return (
    <ModalPage
      bodyClass="is-advanced-open"
      className="advanced-overlay"
      dismissOnBackdrop
      initialFocusRef={mainFirstRef}
      onRequestClose={onCancel}
      open={open}
      role="presentation"
    >
      {(close) => (
        <section
          className="modal-page-surface advanced-screen"
          role="dialog"
          aria-modal="true"
          aria-labelledby="settings-title"
        >
          <header className="advanced-heading">
            <h2 id="settings-title">{title}</h2>
            {page === "controllers" && (
              <p className="settings-subtitle">Connect a controller for multiplayer</p>
            )}
          </header>

          <div className="settings-menu" hidden={page !== "main"}>
            <button
              ref={mainFirstRef}
              className="launch-flow-action settings-menu-button settings-sound-button"
              type="button"
              aria-label={`Sound ${soundOn ? "on" : "off"}. Turn sound ${soundOn ? "off" : "on"}.`}
              aria-pressed={soundOn}
              data-ui-sound-toggle
              onClick={onSound}
            >
              <span>Sound: {soundOn ? "On" : "Off"}</span>
            </button>
            <button className="launch-flow-action settings-menu-button" type="button" onClick={() => setPage("gameplay")}>
              <span>Gameplay Options</span>
            </button>
            <button className="launch-flow-action settings-menu-button" type="button" onClick={() => setPage("controllers")}>
              <span>Keyboard &amp; Controllers</span>
            </button>
            {authorized ? (
              <button
                className="launch-flow-action settings-menu-button advanced-handoff-action"
                type="button"
                onClick={() => close(onSendRom)}
              >
                <span>Send ROM to another device</span>
              </button>
            ) : (
              <button
                className="launch-flow-action settings-menu-button advanced-handoff-action"
                type="button"
                onClick={() => close(onReceiveRom)}
              >
                <span>Receive ROM from another device</span>
              </button>
            )}
            <button className="launch-flow-action settings-menu-button" type="button" onClick={restoreDefaults}>
              Restore Defaults
            </button>
            <button className="launch-flow-action settings-menu-button" type="button" onClick={() => close()}>
              Cancel
            </button>
          </div>

          <div className="advanced-form settings-subpage" hidden={page !== "gameplay"}>
            <div className="advanced-selects">
              <label className="advanced-field">
                <span className="advanced-field-label">Character Mesh</span>
                <span className="advanced-select-shell advanced-cell-frame flame-bridge-cell">
                  <select
                    ref={gameplayFirstRef}
                    value={draft.characterMesh}
                    onChange={(event) => update("characterMesh", event.target.value)}
                  >
                    {CHARACTER_MESHES.map((mesh) => (
                      <option value={mesh.value} key={mesh.value}>{mesh.label}</option>
                    ))}
                  </select>
                </span>
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
              </label>
              <label className="advanced-field">
                <span className="advanced-field-label">Opponent Difficulty</span>
                <span className="advanced-select-shell advanced-cell-frame flame-bridge-cell">
                  <select value={draft.opponentLevel} onChange={(event) => update("opponentLevel", event.target.value)}>
                    {OPPONENT_LEVELS.map((level) => (
                      <option value={level.value} key={level.value}>{level.label}</option>
                    ))}
                  </select>
                </span>
              </label>
              <label className="advanced-field">
                <span className="advanced-field-label">Boot Destination</span>
                <span className="advanced-select-shell advanced-cell-frame flame-bridge-cell">
                  <select value={draft.bootMode} onChange={(event) => update("bootMode", event.target.value)}>
                    {BOOT_MODES.map((mode) => (
                      <option value={mode.value} key={mode.value}>{mode.label}</option>
                    ))}
                  </select>
                </span>
              </label>
            </div>
            <BackButton onClick={() => setPage("main")} />
          </div>

          <div className="advanced-form settings-subpage" hidden={page !== "controllers"}>
            <section className="advanced-input" aria-label="Player inputs">
              <div className="advanced-selects advanced-inputs">
                {portPlan.map((entry, port) => {
                  const choices = portOptions(portPlan, gamepads, port);
                  const current = choiceForEntry(entry);
                  const disabled = choices.length === 0 && current === "none";
                  return (
                    <label className="advanced-field" key={port}>
                      <span className="advanced-field-label">{`P${port + 1}`}</span>
                      <span className={`advanced-select-shell advanced-cell-frame flame-bridge-cell ${disabled ? "is-disabled" : ""}`}>
                        <select
                          ref={port === 0 ? controllersFirstRef : undefined}
                          value={current}
                          disabled={disabled}
                          onChange={(event) => updatePort(port, event.target.value)}
                        >
                          <option value="none">{disabled ? "No input" : "None"}</option>
                          {choices.map((choice) => (
                            <option value={choice.value} key={choice.value}>{choice.label}</option>
                          ))}
                        </select>
                      </span>
                    </label>
                  );
                })}
              </div>
              {humanPorts >= 2 && (
                <small className="advanced-controllers-note">
                  Two or more players: launches open the VS character select so everyone picks a fighter.
                </small>
              )}
            </section>

            {debugMode && (
              <section className="advanced-debug-tools" aria-labelledby="advanced-debug-title">
                <div>
                  <strong id="advanced-debug-title">Debug</strong>
                  <small>Restore first-run checks for this browser.</small>
                </div>
                <div className="advanced-debug-actions">
                  {authorized && (
                    <button className="launch-flow-action reset-rom-button" type="button" onClick={() => close(onResetRom)}>
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

            <BackButton onClick={() => setPage("main")} />
          </div>
        </section>
      )}
    </ModalPage>
  );
}

function BackButton({ onClick }) {
  return (
    <div className="advanced-actions">
      <button className="launch-flow-action settings-back-button" type="button" onClick={onClick}>
        Back
      </button>
    </div>
  );
}
