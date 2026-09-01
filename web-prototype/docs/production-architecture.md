# Fighter creation production architecture

## Decision

Use Google Cloud's native services rather than treating Firebase as a separate
platform:

- Firestore is the source of truth for job metadata and revisions.
- Two Cloud Storage buckets own blobs: a private source bucket for reference
  photos and a public asset bucket for immutable character outputs. The public
  bucket can sit behind a Cloud CDN backend bucket.
- A Cloud Run API serves the website, validates the ROM hash, creates jobs, and
  streams status. It never runs the generation pipeline in production.
- A Cloud Run Job runs one fighter build per execution. The API starts an
  execution with the job ID; the worker reconstructs its workspace from Cloud
  Storage, updates Firestore, and uploads its outputs.
- The signed ROM session carries a random anonymous `ownerId`, isolating job
  history without collecting an account. Firebase Auth or another login can
  replace that identity later without changing the job schema.

Firebase's Emulator Suite is a good way to run Firestore locally, but the app
should continue to use the Google Cloud client libraries and portable data
contracts. This keeps the production architecture straightforward.

## Request and job flow

1. The browser hashes the selected ROM locally and submits only SHA-256 and byte
   count. The API sets a signed, HTTP-only, secure cookie for an accepted hash.
2. Every fighter endpoint checks that cookie. `/create` also blocks its UI until
   validation succeeds.
3. The browser uploads the reference photo. The API validates its type and
   limits, puts it at `characters/{slug}/sources/{jobId}/photo.{ext}`, creates the Firestore
   document, and starts the Cloud Run Job execution.
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
and `checkpoints` live in the private bucket; `latest` and `versions` live in
the public asset bucket:

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
  "revision": 18,
  "status": "queued | running | retrying | complete | failed | cancelled",
  "stage": "portrait",
  "stageLabel": "Painting character-select art",
  "progress": 75,
  "attempt": 2,
  "lease": { "executionId": "...", "expiresAt": "..." },
  "retry": {
    "automaticCounts": { "moderation": 1, "transient": 0 },
    "nextAttemptAt": null,
    "label": null
  },
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
are immutable except for an explicit retry, which creates a new attempt.

## Retry policy

- Output moderation: reroll the affected generated-art stage at most twice.
- Provider 429, 5xx, timeout, or connection reset: exponential retry at most
  three times for inexpensive stages.
- Mesh generation/rigging: never automatically restart an expensive provider
  call unless its provider task ID is persisted and polling can resume.
- Invalid input and deterministic conversion failures: fail for user action.
- An orderly pipeline failure saves completed files to a private checkpoint;
  manual retry restores them in a fresh worker container.
- An infrastructure interruption expires its lease and becomes retryable. The
  deployed Cloud Run Job uses zero platform retries to avoid silently buying a
  second expensive mesh after an abrupt container loss.

Persist provider task IDs before polling them. Without that checkpoint, a
container interruption can spend twice for the same mesh.

## Security and abuse controls

The browser-side ROM hash check proves that the browser supplied an accepted
hash string; it does not prove possession to a hostile client. Keep it as a
legal/product gate, not an authorization or anti-abuse boundary.

Implemented controls include anonymous owner isolation, one active job per
owner, per-session daily and global queue limits, same-origin mutation checks,
ROM-validation throttling, separate private/public buckets, Firestore worker
leases, and Secret Manager injection. The deploy starts with one API instance
so quota checks cannot race.

Before raising that instance cap or treating the site as an unrestricted paid
public service:

- move quota reservation into a Firestore transaction;
- add a durable authenticated identity or payment/invite boundary;
- add a hard project billing alert and daily provider-spend kill switch;
- persist Tripo task IDs before polling so abrupt mesh-stage interruption can
  resume the provider task instead of requiring an explicit rerun.

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
