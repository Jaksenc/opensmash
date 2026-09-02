import { useEffect, useState } from "react";
import FlameAction from "./FlameAction.jsx";
import plusIconUrl from "../visual/assets/ui/Plus.png";

async function readResult(response) {
  const result = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(result.error || "Something went wrong.");
  return result;
}

export default function FighterCreator({ onCancel, onCreated }) {
  const [name, setName] = useState("");
  const [emblem, setEmblem] = useState("");
  const [photo, setPhoto] = useState(null);
  const [photoPreview, setPhotoPreview] = useState("");
  const [rightsAttested, setRightsAttested] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

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
    let createdJob = null;
    setSubmitting(true);
    setError("");
    try {
      const form = new FormData();
      form.set("name", name.trim());
      form.set("emblem", emblem.trim());
      form.set("visibility", "private");
      form.set("rightsAttested", String(rightsAttested));
      form.set("photo", photo);
      const result = await readResult(await fetch("/api/fighters", { method: "POST", body: form }));
      setName("");
      setEmblem("");
      setRightsAttested(false);
      choosePhoto(null);
      createdJob = result.job;
    } catch (submitError) {
      setError(submitError.message);
    } finally {
      setSubmitting(false);
    }
    if (createdJob) onCreated?.(createdJob);
  }

  return (
    <section className="creator-section" id="create-fighter" aria-labelledby="creator-title">
      <div className="creator-intro">
        <h2 id="creator-title">Create a Fighter</h2>
        <p>
          Upload a reference photo and name to generate a playable fighter. Fighters are private
          and ran through safety checks before being created.
        </p>
      </div>

      <div className="creator-panel">
        <div className="creator-workbench">
          <form id="fighter-creator-form" className="fighter-form" onSubmit={submit}>
          <label className={`fighter-photo ${photoPreview ? "has-preview" : ""}`}>
            <input
              type="file"
              accept="image/jpeg,image/png,image/webp"
              onChange={(event) => choosePhoto(event.target.files?.[0])}
              disabled={submitting}
            />
            {photoPreview ? (
              <img className="fighter-photo-preview" src={photoPreview} alt="Fighter reference preview" />
            ) : (
              <span className="fighter-photo-empty">
                <img className="fighter-photo-plus" src={plusIconUrl} alt="" aria-hidden="true" />
                <span className="fighter-photo-copy">
                  <strong>Upload photo</strong>
                  <small>JPEG, PNG or WebP · 12 MB max</small>
                </span>
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
          </div>
          </form>

          {error && <p className="creator-error">{error}</p>}
        </div>
      </div>

      <div className="creator-form-actions">
        <FlameAction
          cellClassName="generate-fire-cell"
          className="generate-button"
          type="submit"
          form="fighter-creator-form"
          disabled={!photo || !name.trim() || !rightsAttested || submitting}
        >
          {submitting ? "Uploading…" : "Create Fighter"}
        </FlameAction>
        <button
          className="launch-flow-action creator-cancel-button"
          type="button"
          onClick={onCancel}
          disabled={submitting}
        >
          Cancel
        </button>
      </div>
    </section>
  );
}
