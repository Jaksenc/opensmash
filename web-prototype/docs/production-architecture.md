# Fighter creation production architecture

## Decision

Use Google Cloud's native services rather than treating Firebase as a separate
platform:

- Firestore is the source of truth for job metadata and revisions.
- Two Cloud Storage buckets own blobs: a private bucket for reference photos,
  checkpoints, and private fighter outputs, plus a public asset bucket for
  immutable public character outputs. The public bucket can sit behind a Cloud
  CDN backend bucket.
- A Cloud Run API serves the website, validates the ROM hash, creates jobs, and
  streams status. It never runs the generation pipeline in production.
- A Cloud Run Job runs one fighter build per execution. The API starts an
  execution with the job ID; the worker reconstructs its workspace from Cloud
  Storage, updates Firestore, and uploads its outputs.
- Firebase Authentication supplies the durable uploader UID used as `ownerId`.
  The separate signed ROM session remains a product/legal gate for gameplay.

Firebase's Emulator Suite is a good way to run Firestore locally, but the app
should continue to use the Google Cloud client libraries and portable data
contracts. This keeps the production architecture straightforward.

## Request and job flow

1. The browser hashes the selected ROM locally and submits only SHA-1 and byte
   count. The API sets a signed, HTTP-only, secure cookie for an accepted hash.
   The browser then keeps the canonical ROM bytes in IndexedDB
   (`shared/rom-store.js`); the engine iframe reads them and builds
   `BattleShip.o2r` locally with Torch compiled to wasm
   (`BattleShip/docs/web_rom_extraction.md`). No ROM-derived asset is served
   by the API or cached at the edge; the engine package holds only code,
   shaders, fonts, and extraction recipes.
2. Every fighter mutation checks both the ROM cookie and a revocation-aware
   Firebase session cookie. `/create` blocks its UI until both checks succeed.
3. The browser uploads the reference photo, visibility, and rights attestation.
   The API validates the form and sends the text plus image to OpenAI's
   multimodal moderation endpoint. Only approved submissions are written to
   `characters/{slug}/sources/{jobId}/photo.{ext}`, recorded in Firestore, and
   dispatched to the Cloud Run Job.
4. The worker claims the job with a Firestore transaction. Claiming must be
   idempotent because execution delivery and retries are at least once.
5. Pipeline stages emit `@@opensmash` JSON progress records. The worker writes
   monotonic document revisions; the UI receives versioned `job.snapshot`
   events over SSE. A slower 15-second reconciliation poll covers dropped
   connections.
6. A successful worker publishes a versioned mini-directory at
   `characters/{slug}/versions/{jobId}-{attempt}/`. Its `manifest.json` lists
   the portrait, announcer audio, character metadata, stock/emblem art, base
   `.osb`, `.osbui`, and every generated skeleton-variant `.osb`. The Firestore
   completion write points at those exact immutable objects.

The resulting object shape is intentionally browsable by character. `sources`
and `checkpoints` always live in the private bucket. A public fighter's
`latest` and `versions` live in the public bucket; a private fighter uses the
same keys in the private bucket and is returned through owner-checked routes:

```text
characters/{slug}/
  latest.json                         # short-cache pointer
  sources/{jobId}/photo.jpg           # private
  checkpoints/{jobId}/...             # private retry state
  versions/{jobId}-{attempt}/
    manifest.json
    character.json
    portrait.png
    stock.png
    emblem.png
    announcer.wav
    injection/{slug}.osb
    injection/{slug}.osbui
    injection/{slug}-{fighter}.osb    # one per generated variant
```

## Job document (protocol version 1)

```json
{
  "protocolVersion": 1,
  "id": "uuid",
  "ownerId": "auth uid",
  "uploader": { "uid": "auth uid", "displayName": "...", "email": "...", "provider": "..." },
  "visibility": "public | private",
  "rightsAttestedAt": "ISO-8601",
  "moderation": { "status": "approved", "model": "omni-moderation-latest", "checkedAt": "ISO-8601" },
  "revision": 18,
  "status": "queued | running | retrying | complete | failed | cancelled",
  "stage": "portrait",
  "stageLabel": "Painting character-select art",
  "progress": 75,
  "attempt": 2,
  "lease": { "executionId": "...", "expiresAt": "..." },
  "retry": {
    "automaticCounts": { "moderation": 1, "transient": 0 },
    "manualRetriesAt": ["ISO-8601"],
    "nextAttemptAt": null,
    "label": null
  },
  "checkpoint": { "savedAt": "ISO-8601", "files": [{ "scope": "output", "name": "rigged.glb", "key": "..." }] },
  "input": { "key": "characters/.../sources/.../photo.jpg", "contentType": "image/jpeg" },
  "artifacts": {
    "manifest": { "key": "characters/.../manifest.json", "url": "https://assets..." },
    "portrait": { "key": "characters/.../portrait.png", "url": "https://assets..." },
    "variants": { "kirby": { "key": "characters/.../name-kirby.osb", "url": "https://assets..." } }
  },
  "createdAt": "ISO-8601",
  "updatedAt": "ISO-8601",
  "startedAt": "ISO-8601",
  "completedAt": null,
  "error": null
}
```

Only the server/worker may mutate a job. A write increments `revision`; clients
discard snapshots older than the revision they already hold. Terminal states
are immutable except for an explicit retry, which creates a new attempt, and
`POST /api/fighters/{id}/cancel`, which moves any non-complete job to
`cancelled` (a cancelled job can still be retried).

Every worker write is conditional on the stored `lease.executionId` still
naming that worker. The API clears the lease when it reconciles a silent job
or cancels one, so a worker that outlived its lease fails its next write,
kills the pipeline, and publishes nothing. `claim` refuses `running` and
`retrying` jobs outright, so two containers can never share an attempt.

Public `manifest.json` identifies the uploader only by an opaque
`uploader.id` (a salted SHA-256 of the account uid, `UPLOADER_TOKEN_SALT`),
and the published `character.json` carries only `display`, `short`, and
`emblem`; the model's description of the photographed person stays in the
worker's private output. Objects published before this change are immutable
at the edge and need a one-time cleanup if that matters.

## Retry policy

- Output moderation: reroll the affected generated-art stage at most twice.
- Provider 429, 5xx, timeout, or connection reset: exponential retry at most
  three times for inexpensive stages.
- Mesh generation/rigging: never automatically restart an expensive provider
  call. Tripo task ids are written to `tripo_tasks.json` the moment they
  exist and checkpointed, so a resumed attempt polls the paid task instead
  of buying it again.
- Invalid input and deterministic conversion failures: fail for user action.
- Manual retries: at most `MAX_MANUAL_RETRIES_PER_JOB` (default 3) per job,
  each counted against the owner's daily limit. Automatic budgets do not
  reset on a manual retry.
- Completed stage outputs are checkpointed to the private bucket as each
  stage boundary is reached, on an orderly failure, and on SIGTERM; a retry
  restores them in a fresh worker container. Unchanged files are skipped.
- The worker renews its lease on a timer (one third of
  `FIGHTER_LEASE_SECONDS`) independent of pipeline output. A job whose lease
  still expires, or that stays `queued` past `FIGHTER_QUEUE_TIMEOUT_SECONDS`
  without a dispatch record, is marked interrupted and retryable.
- Cloud Run sends SIGTERM ten seconds before the task timeout. The worker
  stops the pipeline, checkpoints, marks the job resumable, and exits. The
  deployed Cloud Run Job uses zero platform retries.

## Security and abuse controls

The browser-side ROM hash check proves that the browser supplied an accepted
hash string; it does not prove possession to a hostile client. Keep it as a
legal/product gate, not an authorization or anti-abuse boundary. Possession is
enforced by construction instead: the game's Nintendo-derived assets exist
only as an archive the browser builds from a ROM it holds, so a minted cookie
without a ROM yields an engine with nothing to render.

Implemented controls include Firebase uploader identity and account disabling,
one active job per owner, per-user daily and global queue limits, rights
attestation, pre-dispatch text/image moderation, same-origin mutation checks,
ROM-validation throttling, separate private/public buckets, Firestore worker
leases, and Secret Manager injection. Quota is reserved synchronously in
memory before the upload is read, so parallel requests from one account
cannot all observe zero active jobs, and re-checked inside the Firestore
insert transaction so the limit also holds across API instances.

Before treating the site as an unrestricted paid public service:

- add a payment/invite boundary if account creation becomes an abuse vector;
- add a hard project billing alert and daily provider-spend kill switch.

## Search

`GET /api/characters?q=...` searches the configured roster and all completed
Firestore jobs by display name, short name, and slug. Matching is
case-, punctuation-, and accent-insensitive. The browser applies the same
shared matcher immediately, so search remains responsive and server/client
results cannot drift.

## Local development

The default remains dependency-free with respect to cloud services:

```bash
pnpm install
pnpm dev:safe
```

`dev:safe` exercises uploads, ROM authorization, job persistence, SSE, and the
retry UI without running paid providers. Remove `FIGHTER_WORKER_DISABLED=1` (or
use `pnpm dev`) to run the real local pipeline.

To exercise cloud adapters locally, run a Firestore emulator, then start with:

```bash
FIRESTORE_EMULATOR_HOST=127.0.0.1:8080 \
GOOGLE_CLOUD_PROJECT=opensmash-local \
JOB_DATABASE=firestore \
OBJECT_STORE=local \
FIGHTER_WORKER_DISABLED=1 \
pnpm dev
```

Run verification with:

```bash
pnpm test
pnpm build
```

## Deployment

The repository contains separate API and worker images. In local mode the API
still owns a single in-process queue. With `FIGHTER_EXECUTION_MODE=cloud-run`,
it starts the worker job with a `JOB_ID` override and returns immediately. The
worker transactionally claims that job, renews its lease with progress writes,
and releases it on a terminal state. The API reconciles expired leases.

See `infra/README.md` and run `infra/deploy.sh` after creating the Firestore
database and five Secret Manager values.

Relevant primary documentation:

- [Create Cloud Run jobs](https://cloud.google.com/run/docs/create-jobs)
- [Configure Cloud Run job retries and task timeouts](https://cloud.google.com/run/docs/configuring/task-timeout)
- [Firestore emulator](https://cloud.google.com/firestore/native/docs/emulator)
- [Cloud CDN with a Cloud Storage bucket](https://cloud.google.com/cdn/docs/setting-up-cdn-with-bucket)
