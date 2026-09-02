import { useEffect, useRef, useState } from "react";
import QRCode from "qrcode";
import ModalPage from "./ModalPage.jsx";
import { loadStoredRom } from "../shared/rom-store.js";
import { holdScreenAwake, isHandoffSupported, startRomHandoffHost } from "./rom-handoff-client.js";

// Host side of the ROM handoff: shows a QR code + short code, then streams
// this browser's stored ROM to the device that scans it. Only reachable from
// Advanced in a browser that already validated a ROM. Presented as a
// full-screen ModalPage in the same house style as Advanced Options.

function formatMiB(bytes) {
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export default function RomHandoffModal({ open, onClose }) {
  const [state, setState] = useState("idle");
  const [detail, setDetail] = useState({});
  const [qr, setQr] = useState("");
  const closeButtonRef = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    if (!isHandoffSupported()) {
      setState("error");
      setDetail({ error: new Error("This browser cannot open a direct connection to another device.") });
      return undefined;
    }
    setState("creating");
    setDetail({});
    setQr("");
    const session = startRomHandoffHost({
      loadRom: loadStoredRom,
      onState(next, info = {}) {
        setState(next);
        setDetail(info);
        if (next === "waiting" && info.url) {
          QRCode.toDataURL(info.url, { margin: 1, width: 320, color: { dark: "#120b08", light: "#fff2d6" } })
            .then(setQr)
            .catch(() => setQr(""));
        }
      },
    });
    session.promise.catch(() => {});
    const releaseWakeLock = holdScreenAwake();
    return () => {
      session.cancel();
      releaseWakeLock();
    };
  }, [open]);

  const busy = state === "connecting" || state === "sending";
  const percent = detail.total ? Math.round(((detail.sent ?? 0) / detail.total) * 100) : 0;
  const subtitle = {
    creating: "Opening a private connection…",
    waiting: "Scan the code on the other device, or enter it under Advanced → Receive from another device.",
    connecting: "Other device found. Connecting…",
    sending: `Sending ${detail.total ? formatMiB(detail.total) : "the ROM"}… ${percent}%`,
    done: "Done. The other device is checking the ROM now.",
    error: "The handoff did not complete.",
    cancelled: "Handoff cancelled.",
  }[state] || "";

  return (
    <ModalPage
      bodyClass="is-advanced-open"
      className="advanced-overlay handoff-overlay"
      dismissOnBackdrop={!busy}
      initialFocusRef={closeButtonRef}
      onRequestClose={onClose}
      open={open}
      role="presentation"
    >
      {(close) => (
        <section
          className="modal-page-surface advanced-screen handoff-screen handoff-modal"
          role="dialog"
          aria-modal="true"
          aria-labelledby="handoff-title"
          aria-describedby="handoff-copy"
        >
          <header className="advanced-heading">
            <h2 id="handoff-title">Send ROM to Another Device</h2>
            <p id="handoff-copy">{subtitle}</p>
          </header>

          {state === "waiting" && (
            <div className="handoff-card">
              {qr
                ? <img className="handoff-qr" src={qr} alt={`QR code for ${detail.url}`} width="240" height="240" />
                : <div className="handoff-qr handoff-qr-placeholder" aria-hidden="true" />}
              <div className="handoff-card-copy">
                <span className="handoff-code-label">Code</span>
                <code className="handoff-code" aria-label={`Handoff code ${detail.code.split("").join(" ")}`}>{detail.code}</code>
                <a className="handoff-url" href={detail.url} target="_blank" rel="noreferrer">{detail.url}</a>
                <small className="handoff-note">
                  Keep this window open and awake until it finishes. The ROM travels directly between your devices;
                  our servers only pass along the connection details. Both devices should be on the same Wi-Fi.
                </small>
              </div>
            </div>
          )}

          {state === "sending" && (
            <div className="handoff-card handoff-card-progress">
              <progress className="handoff-progress" max={detail.total} value={detail.sent} aria-label="Transfer progress" />
            </div>
          )}

          {state === "error" && (
            <div className="handoff-card handoff-card-error" role="alert">
              <p className="handoff-error">{detail.error?.message || "The handoff failed."}</p>
            </div>
          )}

          <div className="advanced-actions">
            <button
              ref={closeButtonRef}
              className="launch-flow-action cancel-options-button"
              type="button"
              onClick={() => close()}
            >
              {state === "done" ? "Close" : busy ? "Stop sending" : "Cancel"}
            </button>
          </div>
        </section>
      )}
    </ModalPage>
  );
}
