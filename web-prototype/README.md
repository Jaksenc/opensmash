# OpenSmash web prototype

A deliberately small React site and Node server that lives beside the existing
`pipeline/website` work. It reads character portraits and metadata from
`pipeline/play/ui` and serves the existing browser engine from
`BattleShip/web-dist`; those outputs are not copied into this app.

## Run it

```bash
cd web-prototype
pnpm install
pnpm dev
```

Open <http://127.0.0.1:4174>. For a production-style run:

```bash
pnpm build
COOKIE_SECRET="replace-me" pnpm start
```

Use `PORT` to change the port. Set a stable, private `COOKIE_SECRET` in any real
deployment so validation cookies survive restarts and cannot be forged.

For production architecture, durable GCP adapters, the versioned status
contract, and the API/worker cutover checklist, see
[`docs/production-architecture.md`](docs/production-architecture.md).
Deployment prerequisites and the one-command GCP rollout are in
[`infra/README.md`](infra/README.md).

## Choose the featured characters

Every character staged in `BattleShip/web-dist/bundles` appears automatically.
Edit `config/characters.json` only to pin characters to the front of the roster:

```json
{ "slug": "queen" }
```

The prototype uses the same deterministic, balanced skeleton/moveset assignment
as the game. A character can declare `base` or `preferred_bases` in its pipeline
`character.json`; otherwise it is balanced across the production-ready targets.
Donkey Kong and Yoshi remain available as explicit targets but are excluded from
the default pool. Completed database generation jobs are appended when they have
not yet been staged into the engine bundle directory.

## ROM gate

The browser reads the selected file locally, unwraps ordinary unencrypted ZIPs,
normalizes N64 `.z64` / `.v64` / `.n64` byte order plus recognized leading
headers and trailing padding, and compares the canonical SHA-1 and size against
`shared/rom-catalog.js`. It sends only that canonical digest and byte count to
`POST /api/validate-rom`; the server checks the same shared catalog and issues a
signed, HTTP-only, 30-day cookie. The accepted catalog covers the known Japan,
Australia, Europe, USA, and USA LodgeNet images. The engine routes return 401
without that cookie, and the cookie itself is signed with HMAC-SHA-256.

The ROM and archive bytes are never uploaded or stored. Password-protected and
unsupported archives must be extracted by the user first. The current WASM
package already contains the project's extracted engine assets.

Use the `Dev: clear ROM` button in the header to expire the validation cookie
and exercise the first-run flow again.

## Generate a fighter

Open `/create`, validate a supported ROM, sign in, and submit a name,
JPEG/PNG/WebP reference photo, optional emblem direction, and public/private
visibility. Public is the default. The uploader must attest that they own or
have permission to use the character and photo. The server safety-screens the
text and image with `omni-moderation-latest` before it creates or dispatches a
paid generation job. In local mode the server stores
uploads and job records under `data/`; the production adapters use Firestore
and Cloud Storage. A single local worker runs the existing
`pipeline/run_character.py` command.
Before invoking the pipeline, the worker flattens multi-frame phone photos,
applies EXIF orientation, converts to plain sRGB RGB, and writes a normalized
PNG capped at 2048px so image providers receive a predictable input.

The pipeline emits versioned JSON progress records and the page receives
versioned job snapshots over server-sent events, with a slow reconciliation
poll as backup. Jobs survive server restarts, interrupted jobs are requeued, and
failed jobs can be resumed using the pipeline's existing output-based resume
behavior. Only one fighter runs at a time to avoid collisions in the shared
pipeline output directories. In GCP mode the API launches a dedicated Cloud
Run Job, which claims the Firestore record with a renewable lease.

The worker automatically rerolls provider-generated art up to two times when
output moderation blocks a random result. Temporary rate-limit, timeout, and
5xx failures receive up to three short backoff retries outside the expensive
mesh stages. Invalid inputs and mesh failures stop for manual review.

Production authentication uses Firebase Authentication with Google, Apple,
and passwordless email providers. Firebase's UID becomes the durable job
`ownerId`; the job also records the uploader profile. Private outputs are kept
in the private object bucket and served only through owner-checked API routes.
Disable an abusive uploader in Firebase Authentication to block future
creation and retry requests.

For UI or API testing without invoking paid providers, disable the worker and
optionally use a temporary job directory:

Use `pnpm dev:safe` during development. Local JSON records and a local object
store are the defaults. Set `JOB_DATABASE=firestore` and `OBJECT_STORE=gcs`
with the values shown in `.env.example` to use the production adapters.
