import { useEffect, useRef, useState } from "react";
import ModalPage from "./ModalPage.jsx";
import { formatFighterJobError } from "../shared/fighter-job-ui.js";

const ACTIVE = new Set(["queued", "running", "retrying"]);

function formatElapsed(ms) {
  if (!Number.isFinite(ms) || ms < 0) return "";
  const totalSeconds = Math.floor(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return minutes ? `${minutes}m ${String(seconds).padStart(2, "0")}s` : `${seconds}s`;
}

function statusHeadline(job) {
  switch (job?.status) {
    case "queued":
      return "Waiting for a generation worker";
    case "running":
      return "Generating";
    case "retrying":
      return "Retrying";
    case "failed":
      return "Generation failed";
    case "cancelled":
      return "Cancelled";
    case "complete":
      return "Ready to fight";
    default:
      return "";
  }
}

// Generation details for one fighter job: the live stage, how long it has
// been running, the pipeline's last log lines, and retry when it failed.
// Opened by tapping a generating or failed grid tile and automatically when a
// job that was visible while it ran fails.
export default function FighterJobModal({ job, onClose, onDelete, onRetry, open }) {
  const closeRef = useRef(null);
  const [now, setNow] = useState(() => Date.now());
  const [logOpen, setLogOpen] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [retryError, setRetryError] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const active = ACTIVE.has(job?.status);
  useEffect(() => {
    if (!open || !active) return undefined;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [open, active]);
  useEffect(() => {
    if (!open) return;
    setNow(Date.now());
    setLogOpen(job?.status === "failed");
    setRetryError("");
    setConfirmDelete(false);
    setDeleting(false);
  }, [open, job?.id, job?.status]);

  if (!job) return <ModalPage className="fighter-job-overlay" open={false} />;

  const failed = job.status === "failed";
  const progress = Math.max(0, Math.min(100, Number(job.progress) || 0));
  const startedAt = Date.parse(job.startedAt || job.createdAt || "");
  const endedAt = Date.parse(job.completedAt || (active ? "" : job.updatedAt) || "");
  const elapsed = formatElapsed((Number.isFinite(endedAt) ? endedAt : now) - startedAt);
  const retryLabel = job.retry?.label || "Retry generation";
  const logTail = Array.isArray(job.logTail) ? job.logTail : [];

  async function retry(close) {
    if (!onRetry || retrying) return;
    setRetrying(true);
    setRetryError("");
    try {
      await onRetry(job);
      close();
    } catch (error) {
      setRetryError(error.message || "Could not retry this fighter.");
    } finally {
      setRetrying(false);
    }
  }

  async function remove(close) {
    if (!onDelete || deleting) return;
    if (!confirmDelete) {
      setConfirmDelete(true);
      return;
    }
    setDeleting(true);
    setRetryError("");
    try {
      await onDelete(job);
      close();
    } catch (error) {
      setRetryError(error.message || "Could not delete this fighter.");
      setDeleting(false);
      setConfirmDelete(false);
    }
  }

  return (
    <ModalPage
      id="fighter-job-overlay"
      className="fighter-job-overlay"
      bodyClass="is-fighter-job-open"
      dismissOnBackdrop
      initialFocusRef={closeRef}
      onRequestClose={onClose}
      open={open}
      role="presentation"
    >
      {(close) => (
        <section
          className={`modal-page-surface fighter-job-screen ${failed ? "is-failed" : ""}`.trim()}
          role="dialog"
          aria-modal="true"
          aria-labelledby="fighter-job-title"
          aria-describedby="fighter-job-copy"
        >
          <div className="fighter-job-content">
            <h2 id="fighter-job-title" className="launch-flow-title fighter-job-title">
              {job.character?.name || job.name}
            </h2>
            <p className="fighter-job-headline" role="status" aria-live="polite">
              {statusHeadline(job)}
              {active && <span className="fighter-job-headline-dot" aria-hidden="true" />}
            </p>

            <dl className="fighter-job-facts">
              <div>
                <dt>Stage</dt>
                <dd>{job.stageLabel || job.stage || job.status}</dd>
              </div>
              <div>
                <dt>Progress</dt>
                <dd>{progress}%</dd>
              </div>
              {elapsed && (
                <div>
                  <dt>{active ? "Elapsed" : "Ran for"}</dt>
                  <dd>{elapsed}</dd>
                </div>
              )}
              {job.attempt > 1 && (
                <div>
                  <dt>Attempt</dt>
                  <dd>{job.attempt}</dd>
                </div>
              )}
              {job.retry?.nextAttemptAt && (
                <div>
                  <dt>Next try</dt>
                  <dd>{formatElapsed(Date.parse(job.retry.nextAttemptAt) - now) || "now"}</dd>
                </div>
              )}
            </dl>

            <div className="fighter-job-bar" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow={progress}>
              <i style={{ width: `${progress}%` }} />
            </div>

            <div id="fighter-job-copy" className="fighter-job-copy">
              {failed && <p className="launch-flow-copy">{formatFighterJobError(job)}</p>}
              {failed && job.error && (
                <p className="fighter-job-raw-error">
                  <span>Error</span> {job.error}
                </p>
              )}
              {!failed && active && (
                <p className="launch-flow-copy">
                  A fighter usually takes a few minutes. You can close this and keep playing; the tile
                  updates on its own.
                </p>
              )}
            </div>

            {logTail.length > 0 && (
              <div className="fighter-job-log">
                <button
                  className="fighter-job-log-toggle"
                  type="button"
                  aria-expanded={logOpen}
                  aria-controls="fighter-job-log-lines"
                  onClick={() => setLogOpen((value) => !value)}
                >
                  {logOpen ? "Hide pipeline log" : `Show pipeline log (${logTail.length} ${logTail.length === 1 ? "line" : "lines"})`}
                </button>
                <pre id="fighter-job-log-lines" hidden={!logOpen}>{logTail.join("\n")}</pre>
              </div>
            )}

            {retryError && <p className="fighter-job-retry-error" role="alert">{retryError}</p>}

            <div className="fighter-job-actions">
              {failed && onRetry && (
                <button
                  className="launch-flow-action fighter-job-retry"
                  type="button"
                  disabled={retrying}
                  onClick={() => retry(close)}
                >
                  {retrying ? "Retrying…" : retryLabel}
                </button>
              )}
              {!active && onDelete && (
                <button
                  className={`launch-flow-action fighter-job-delete ${confirmDelete ? "is-confirming" : ""}`.trim()}
                  type="button"
                  disabled={deleting}
                  onClick={() => remove(close)}
                >
                  {deleting ? "Deleting…" : confirmDelete ? "Really delete? Tap again" : "Delete fighter"}
                </button>
              )}
              <button
                ref={closeRef}
                className="launch-flow-action launch-flow-cancel fighter-job-cancel"
                type="button"
                onClick={() => close()}
              >
                Close
              </button>
            </div>
          </div>
        </section>
      )}
    </ModalPage>
  );
}
