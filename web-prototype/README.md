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

## Choose the featured characters

Edit `config/characters.json`. Each entry points at a pipeline character and a
vanilla fighter skeleton/moveset:

```json
{ "slug": "queen", "fighter": "kirby" }
```

Valid fighter names are `mario`, `fox`, `donkey`, `samus`, `luigi`, `link`,
`yoshi`, `captain`, `kirby`, `pikachu`, `purin`, and `ness`. The server skips an
entry when its portrait, metadata, or selected `.osb` bundle is missing.

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

Open `/create` and submit a name, JPEG/PNG/WebP reference photo, and optional
emblem direction. The server stores each upload and JSON job record in
`data/fighter-jobs`, then a single worker runs the existing
`pipeline/run_character.py` command. No pipeline source changes are required.
Before invoking the pipeline, the worker flattens multi-frame phone photos,
applies EXIF orientation, converts to plain sRGB RGB, and writes a normalized
PNG capped at 2048px so image providers receive a predictable input.

The page polls the record for progress inferred from the pipeline's current log
messages. Jobs survive server restarts, interrupted jobs are requeued, and
failed jobs can be resumed using the pipeline's existing output-based resume
behavior. Only one fighter runs at a time to avoid collisions in the shared
pipeline output directories.

The worker automatically rerolls provider-generated art up to two times when
output moderation blocks a random result. Temporary rate-limit, timeout, and
5xx failures receive up to three short backoff retries outside the expensive
mesh stages. Invalid inputs and mesh failures stop for manual review.

For UI or API testing without invoking paid providers, disable the worker and
optionally use a temporary job directory:

```bash
FIGHTER_WORKER_DISABLED=1 FIGHTER_JOBS_ROOT=/tmp/opensmash-fighter-jobs pnpm start
```
