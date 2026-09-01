import { useEffect, useMemo, useState } from "react";

const ACTIVE_STATUSES = new Set(["queued", "running", "retrying"]);
const ACTIVE_JOB_KEY = "opensmash-active-fighter-job";

function formatTime(value) {
  if (!value) return "";
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

async function readResult(response) {
  const result = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(result.error || "Something went wrong.");
  return result;
}

export default function FighterCreator({ onPlay, user }) {
  const [jobs, setJobs] = useState([]);
  const [selectedId, setSelectedId] = useState(() => localStorage.getItem(ACTIVE_JOB_KEY));
  const [name, setName] = useState("");
  const [emblem, setEmblem] = useState("");
  const [photo, setPhoto] = useState(null);
  const [photoPreview, setPhotoPreview] = useState("");
  const [visibility, setVisibility] = useState("public");
  const [rightsAttested, setRightsAttested] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const selectedJob = useMemo(
    () => jobs.find((job) => job.id === selectedId) || jobs[0] || null,
    [jobs, selectedId],
  );
  const hasActiveJob = jobs.some((job) => ACTIVE_STATUSES.has(job.status));

  async function loadJobs() {
    const result = await readResult(await fetch("/api/fighters", { cache: "no-store" }));
    setJobs(result.jobs);
    setSelectedId((current) => {
      if (current && result.jobs.some((job) => job.id === current)) return current;
      const next = result.jobs.find((job) => ACTIVE_STATUSES.has(job.status)) || result.jobs[0];
      return next?.id || null;
    });
  }

  useEffect(() => {
    loadJobs().catch((loadError) => setError(loadError.message));
  }, []);

  useEffect(() => {
    if (!selectedId) {
      localStorage.removeItem(ACTIVE_JOB_KEY);
      return;
    }
    localStorage.setItem(ACTIVE_JOB_KEY, selectedId);
  }, [selectedId]);

  useEffect(() => {
    if (!hasActiveJob) return undefined;
    const timer = window.setInterval(() => {
      loadJobs().catch((loadError) => setError(loadError.message));
    }, 15_000);
    return () => window.clearInterval(timer);
  }, [hasActiveJob]);

  useEffect(() => {
    if (!selectedJob || !ACTIVE_STATUSES.has(selectedJob.status)) return undefined;
    const stream = new EventSource(`/api/fighters/${selectedJob.id}/events`);
    stream.addEventListener("job", (event) => {
      const snapshot = JSON.parse(event.data);
      setJobs((current) => current.map((job) => (
        job.id === snapshot.job.id && snapshot.job.revision >= (job.revision || 0)
          ? snapshot.job
          : job
      )));
      if (!ACTIVE_STATUSES.has(snapshot.job.status)) {
        stream.close();
        loadJobs().catch((loadError) => setError(loadError.message));
      }
    });
    return () => stream.close();
  }, [selectedJob?.id, selectedJob?.status]);

  useEffect(() => () => {
    if (photoPreview) URL.revokeObjectURL(photoPreview);
  }, [photoPreview]);

  function choosePhoto(file) {
    if (photoPreview) URL.revokeObjectURL(photoPreview);
    setPhoto(file || null);
    setPhotoPreview(file ? URL.createObjectURL(file) : "");
    setError("");
  }

  async function submit(event) {
    event.preventDefault();
    if (!photo || !name.trim()) return;
    setSubmitting(true);
    setError("");
    try {
      const form = new FormData();
      form.set("name", name.trim());
      form.set("emblem", emblem.trim());
      form.set("visibility", visibility);
      form.set("rightsAttested", String(rightsAttested));
      form.set("photo", photo);
      const result = await readResult(await fetch("/api/fighters", { method: "POST", body: form }));
      setJobs((current) => [result.job, ...current]);
      setSelectedId(result.job.id);
      setName("");
      setEmblem("");
      setVisibility("public");
      setRightsAttested(false);
      choosePhoto(null);
    } catch (submitError) {
      setError(submitError.message);
    } finally {
      setSubmitting(false);
    }
  }

  async function retry(job) {
    setError("");
    try {
      const result = await readResult(
        await fetch(`/api/fighters/${job.id}/retry`, { method: "POST" }),
      );
      setJobs((current) => current.map((item) => (item.id === job.id ? result.job : item)));
      setSelectedId(job.id);
    } catch (retryError) {
      setError(retryError.message);
    }
  }

  return (
    <section className="creator-section" id="create-fighter" aria-labelledby="creator-title">
      <div className="creator-intro">
        <p className="eyebrow">Fighter lab</p>
        <h2 id="creator-title">Make your own fighter</h2>
        <p>
          Give the pipeline a name and a clear reference photo. It will build the model,
          game assets, announcer clip, and playable bundle automatically.
        </p>
        <div className="creator-facts">
          <span><b>~$2</b> per fighter</span>
          <span><b>Several minutes</b> to build</span>
          <span><b>Safety screened</b> before generation</span>
          <span><b>Server queue</b> survives refreshes</span>
        </div>
        <p className="uploader-note">Uploading as {user.displayName || user.email || "your account"}.</p>
      </div>

      <div className="creator-workbench">
        <form className="fighter-form" onSubmit={submit}>
          <label className={`fighter-photo ${photoPreview ? "has-preview" : ""}`}>
            <input
              type="file"
              accept="image/jpeg,image/png,image/webp"
              onChange={(event) => choosePhoto(event.target.files?.[0])}
              disabled={submitting}
            />
            {photoPreview ? (
              <img src={photoPreview} alt="Fighter reference preview" />
            ) : (
              <span>
                <i>+</i>
                Upload photo
                <small>JPEG, PNG or WebP · 12 MB max</small>
              </span>
            )}
            {photoPreview && <small className="replace-photo">Choose another photo</small>}
          </label>

          <div className="fighter-fields">
            <label>
              <span>Fighter name</span>
              <input
                type="text"
                value={name}
                onChange={(event) => setName(event.target.value)}
                maxLength={80}
                placeholder="e.g. Weird Al Yankovic"
                required
                disabled={submitting}
              />
            </label>
            <label>
              <span>Emblem direction <small>optional</small></span>
              <input
                type="text"
                value={emblem}
                onChange={(event) => setEmblem(event.target.value)}
                maxLength={200}
                placeholder="e.g. a red accordion"
                disabled={submitting}
              />
            </label>
            <fieldset className="visibility-fieldset">
              <legend>Who can see this fighter?</legend>
              <label className={visibility === "public" ? "is-selected" : ""}>
                <input
                  type="radio"
                  name="visibility"
                  value="public"
                  checked={visibility === "public"}
                  onChange={() => setVisibility("public")}
                  disabled={submitting}
                />
                <span>Public <small>Added to the community roster</small></span>
              </label>
              <label className={visibility === "private" ? "is-selected" : ""}>
                <input
                  type="radio"
                  name="visibility"
                  value="private"
                  checked={visibility === "private"}
                  onChange={() => setVisibility("private")}
                  disabled={submitting}
                />
                <span>Private <small>Visible only to your account</small></span>
              </label>
            </fieldset>
            <label className="rights-attestation">
              <input
                type="checkbox"
                checked={rightsAttested}
                onChange={(event) => setRightsAttested(event.target.checked)}
                disabled={submitting}
                required
              />
              <span>
                I confirm I own or have permission to use this character and photo, and that
                the submission does not contain nudity or abusive content.
              </span>
            </label>
            <p className="moderation-copy">
              The name, direction, and photo are safety-screened before the paid build starts.
            </p>
            <button
              className="generate-button"
              type="submit"
              disabled={!photo || !name.trim() || !rightsAttested || submitting}
            >
              {submitting ? "Uploading…" : "Generate fighter →"}
            </button>
          </div>
        </form>

        {error && <p className="creator-error">{error}</p>}

        {selectedJob && (
          <article className={`generation-status is-${selectedJob.status}`}>
            <div className="generation-visual">
              {selectedJob.status === "complete" ? (
                <img src={selectedJob.character.portrait} alt={`Generated portrait of ${selectedJob.name}`} />
              ) : (
                <div className="generation-monogram">{selectedJob.name.slice(0, 1).toUpperCase()}</div>
              )}
            </div>
            <div className="generation-details">
              <div className="generation-heading">
                <div>
                  <small>{selectedJob.status === "complete" ? "Ready to fight" : "Generation job"}</small>
                  <h3>{selectedJob.name}</h3>
                </div>
                <span>{selectedJob.visibility === "private" ? "Private · " : ""}{selectedJob.status}</span>
              </div>
              <div className="progress-track" aria-label={`${selectedJob.progress}% complete`}>
                <i style={{ width: `${selectedJob.progress}%` }} />
              </div>
              <p className="stage-label">
                {selectedJob.stageLabel}
                {ACTIVE_STATUSES.has(selectedJob.status) && <b>{selectedJob.progress}%</b>}
              </p>
              {selectedJob.error && <p className="job-error">{selectedJob.error}</p>}
              {selectedJob.status === "complete" && (
                <div className="finished-actions">
                  <button type="button" onClick={() => onPlay(selectedJob.character)}>
                    Quick match →
                  </button>
                  <span>
                    {selectedJob.costUsd != null ? `$${selectedJob.costUsd.toFixed(2)} · ` : ""}
                    finished {formatTime(selectedJob.completedAt)}
                  </span>
                </div>
              )}
              {selectedJob.status === "failed" && (
                <button className="retry-button" type="button" onClick={() => retry(selectedJob)}>
                  {selectedJob.retry?.label || "Resume generation"}
                </button>
              )}
              {selectedJob.logTail?.length > 0 && selectedJob.status !== "complete" && (
                <details className="job-log">
                  <summary>Pipeline log</summary>
                  <pre>{selectedJob.logTail.join("\n")}</pre>
                </details>
              )}
            </div>
          </article>
        )}

        {jobs.length > 1 && (
          <div className="job-history">
            <span>Recent builds</span>
            <div>
              {jobs.slice(0, 6).map((job) => (
                <button
                  className={job.id === selectedJob?.id ? "is-selected" : ""}
                  type="button"
                  key={job.id}
                  onClick={() => setSelectedId(job.id)}
                >
                  {job.name}<small>{job.status}</small>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
