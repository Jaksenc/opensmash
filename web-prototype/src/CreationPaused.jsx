import { useRef } from "react";
import ModalPage from "./ModalPage.jsx";

// Shown instead of the fighter creator while the CREATION_ENABLED killswitch
// is off. This is the About screen's furniture — same overlay, title, copy and
// cancel control — so a closed lab reads as part of the site rather than an
// error page.
export default function CreationPaused({ open, onClose }) {
  const closeRef = useRef(null);

  return (
    <ModalPage
      id="creation-paused-overlay"
      className="creation-paused-overlay"
      bodyClass="is-creation-paused-open"
      initialFocusRef={closeRef}
      onRequestClose={onClose}
      open={open}
      role="presentation"
    >
      {(close) => (
        <section
          className="modal-page-surface creation-paused-screen"
          role="dialog"
          aria-modal="true"
          aria-labelledby="creation-paused-title"
          aria-describedby="creation-paused-copy"
        >
          <div className="creation-paused-content">
            <h2 id="creation-paused-title" className="launch-flow-title creation-paused-title">
              Fighter creation is paused
            </h2>
            <div id="creation-paused-copy" className="creation-paused-copy">
              <p className="launch-flow-copy">
                Generating a fighter costs real money in compute, and we cannot cover the bill
                right now.
              </p>
              <p className="launch-flow-copy">
                Creation is switched off until that changes. Every fighter already on the roster
                is still free to play.
              </p>
            </div>
            <div className="launch-flow-fire-cell creation-paused-support-cell">
              <a
                className="launch-flow-action creation-paused-support"
                href="https://buymeacoffee.com/turtlesoupy"
                target="_blank"
                rel="noreferrer"
              >
                Buy me a coffee
              </a>
            </div>
            <button
              ref={closeRef}
              className="launch-flow-action launch-flow-cancel creation-paused-cancel"
              type="button"
              onClick={() => close()}
            >
              Back to fighters
            </button>
          </div>
        </section>
      )}
    </ModalPage>
  );
}
