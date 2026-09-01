import { useEffect, useState } from "react";
import FlameAction from "./FlameAction.jsx";
import RetroChoiceGrid from "./RetroChoiceGrid.jsx";

const VISIBILITY_OPTIONS = [
  { value: "public", label: "Public", description: "Added to the community roster" },
  { value: "private", label: "Private", description: "Visible only to your account" },
];

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
  const [visibility, setVisibility] = useState("public");
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
      form.set("visibility", visibility);
      form.set("rightsAttested", String(rightsAttested));
      form.set("photo", photo);
      const result = await readResult(await fetch("/api/fighters", { method: "POST", body: form }));
      setName("");
      setEmblem("");
      setVisibility("public");
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
        <p>Upload a reference photo and name to generate a playable fighter.</p>
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
              <RetroChoiceGrid
                className="creator-visibility-grid"
                name="visibility"
                value={visibility}
                options={VISIBILITY_OPTIONS}
                onChange={setVisibility}
                disabled={submitting}
              />
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
