# GCP deployment

The deploy script provisions the two storage buckets, service accounts,
Artifact Registry repository, container builds, Cloud Run API, and Cloud Run
worker job. It intentionally does not choose Firestore's permanent location or
create secret values on your behalf.

## One-time setup

Choose the Firestore location in the Google Cloud console or create the default
Native-mode database before deploying. Then create these Secret Manager
secrets with real values:

```bash
gcloud secrets create opensmash-cookie-secret --data-file=-
gcloud secrets create opensmash-openai-api-key --data-file=-
gcloud secrets create opensmash-tripo-api-key --data-file=-
gcloud secrets create opensmash-fal-key --data-file=-
gcloud secrets create opensmash-minimax-voice-id --data-file=-
```

Generate the cookie secret with at least 32 random bytes. Do not paste API keys
into `.env.example`, the deploy script, or a container build.

Create a Firebase Web App in the same project, enable Google and Email link in
Authentication, and add the production domain under Authorized domains. For
Apple, create the Apple Service ID and private key, register
`https://PROJECT_ID.firebaseapp.com/__/auth/handler`, then enable Apple in the
Firebase Authentication provider settings. The deploy uses the Web App's
public API key and app ID; these are configuration values, not secrets.

## TURN relay for the ROM handoff (recommended)

"Send ROM to another device" streams the ROM browser-to-browser over WebRTC.
STUN alone only connects devices that can reach each other directly; guest
Wi-Fi with client isolation, cellular, and some home routers block that and the
player sees "The connection between the devices failed". A TURN relay fixes
this. The relay forwards DTLS-encrypted packets it cannot read, so the ROM is
still never readable by any server.

Cloudflare Realtime TURN is the supported option (pay per GB; a relayed 16 MB
handoff costs well under a cent). In the Cloudflare dashboard open
**Realtime → TURN** and enable TURN for the account. Then, with an API token
that has the Calls (Realtime) edit permission, one script creates the key,
stores both values in Secret Manager, and attaches them to the running API:

```bash
CLOUDFLARE_API_TOKEN=... CLOUDFLARE_ACCOUNT_ID=... ./infra/enable-turn.sh
```

Or do it by hand: create the TURN key in the dashboard and store its two values:

```bash
printf '%s' "$TURN_KEY_ID" | gcloud secrets create opensmash-cloudflare-turn-key-id --data-file=-
printf '%s' "$TURN_KEY_API_TOKEN" | gcloud secrets create opensmash-cloudflare-turn-key-token --data-file=-
```

`deploy.sh` detects both secrets and mounts them as `CLOUDFLARE_TURN_KEY_ID`
and `CLOUDFLARE_TURN_KEY_API_TOKEN`; the API then mints 15-minute TURN
credentials for each handoff via `GET /api/handoff/ice`. `/healthz` reports
`"handoffIce": "cloudflare"` once active (`"stun"` means unconfigured). To
enable without a full deploy:

```bash
gcloud run services update "$SERVICE_NAME" --region "$REGION" \
  --update-secrets CLOUDFLARE_TURN_KEY_ID=opensmash-cloudflare-turn-key-id:latest,CLOUDFLARE_TURN_KEY_API_TOKEN=opensmash-cloudflare-turn-key-token:latest
```

A self-hosted coturn works too: set `TURN_URLS`, `TURN_USERNAME`, and
`TURN_CREDENTIAL` on the API instead.

## Build and deploy

The engine package must not contain ROM-derived assets; the browser builds
`BattleShip.o2r` itself with Torch compiled to wasm (see
`BattleShip/docs/web_rom_extraction.md`). `deploy.sh` therefore runs
`BattleShip/scripts/build_torch_wasm.sh` (needs an activated emsdk, like the
engine build) before `package_web.sh`, and aborts if the resulting `web-dist`
lacks the Torch module or still contains `files/BattleShip.o2r`. The API
Dockerfile copies `web-dist/torch`, `rom-extract.js` and `torch-worker.js`
explicitly, so a package built without them fails the image build too.

From `pipeline/web-prototype`:

```bash
PROJECT_ID=your-project \
REGION=us-central1 \
PUBLIC_ORIGIN=https://example.com \
FIREBASE_API_KEY=your-public-web-api-key \
FIREBASE_APP_ID=1:123456789:web:abcdef \
CLOUDFLARE_API_TOKEN=... \
CLOUDFLARE_ACCOUNT_ID=... \
./infra/deploy.sh
```

Run from clean commits in both the `pipeline` and sibling `BattleShip`
repositories. The first deploy creates `opensmash-cookie-secret-previous` by
copying the current signing key; subsequent rotations maintain it.

The API runs with 3 to 6 instances (2 vCPU, 2 GiB, 500 concurrent
requests each, startup CPU boost). Everything that has to agree across
replicas lives in Firestore: job records and leases, the quota re-check inside
the insert transaction, and ROM-handoff rooms (`handoffRooms`, with a TTL
policy on `expireAt` that `deploy.sh` enables). The per-instance in-memory
quota reservation and the ROM-validation rate limiter are only a first line;
across replicas they are looser by the instance count, which is acceptable.
Keep `--min-instances` at 1 or more: a cold start pulls a multi-GB image and
scans the roster, and with `--min-instances 0` the first visitor after a quiet
spell pays for it.

The public bucket works immediately at its `storage.googleapis.com` URL. To put
it behind Cloud CDN, create the backend bucket with one command, then attach it
to the HTTPS load balancer that owns the asset hostname:

```bash
gcloud compute backend-buckets create opensmash-assets \
  --gcs-bucket-name="$PUBLIC_BUCKET" \
  --enable-cdn
```

Set `ASSET_BASE_URL=https://assets.example.com` on the next deploy after DNS,
certificate, and URL-map routing are in place.

## Custom domain

After the Cloud Run service is deployed, provision Google's recommended global
external HTTPS load balancer and create DNS-only Cloudflare records:

```bash
PROJECT_ID=your-project \
REGION=us-central1 \
DOMAIN=example.com \
CLOUDFLARE_API_TOKEN=... \
./infra/configure-domain.sh
```

The command creates explicit Certificate Manager DNS authorizations for the
apex and `www`, publishes their DNS-only Cloudflare CNAMEs, and waits for the
certificate to become active before creating or changing the HTTPS proxy. It
also provisions an HTTP-to-HTTPS redirect. Override the 30-minute certificate
wait with `CERT_WAIT_SECONDS` if needed.

Additional domains can share the existing load balancer and certificate map.
Give each domain a unique `CERT_PREFIX` so its DNS authorizations, certificate,
and map entries remain independent:

```bash
PROJECT_ID=your-project \
REGION=us-central1 \
DOMAIN=alias.example \
CERT_PREFIX=opensmash-alias \
CLOUDFLARE_API_TOKEN=... \
./infra/configure-domain.sh
```

## Pausing fighter creation

Creation is the only part of the site that spends money per request (GPU time,
image and voice models). `CREATION_ENABLED=0` closes it without touching the
roster: `/api/session` reports `creationEnabled: false`, the create tile and
`/create` show the "Fighter creation is paused" notice instead of the creator,
and
`POST /api/fighters` and `/api/fighters/:id/retry` answer `503`. Any other
value, including an unset one, leaves creation open.

```bash
gcloud run services update opensmash-web --region "$REGION" \
  --update-env-vars CREATION_ENABLED=0
```

The switch takes effect on the next `/api/session` call — no redeploy, no edge
purge, because the shared app shell never carries the flag. Set it back with
`CREATION_ENABLED=1`. `deploy.sh` rewrites the whole environment, so export
`CREATION_ENABLED=0` for a deploy that must keep the lab closed. The switch
only refuses new work: jobs the worker already picked up run to completion.

## Cloudflare edge cache

The main `deploy.sh` command also deploys the engine worker after Cloud Run. It
validates the existing ROM-session cookie before looking up shared `/engine/*`
runtime files in Cloudflare's cache, then enables proxying for the apex and
`www` records. Under `/engine/bundles/*` the origin decides per response:
baked roster bundles are sent `public` and are shared at the edge, while
owner-scoped fighter-lab bundles are `private` and always bypass the shared
cache. Public content-hashed Vite assets use Cloudflare's normal static
cache, and a second Cache Rule covers `/character-assets/*` (portrait tiles
and announcer `.wav` clips, which are outside Cloudflare's default cacheable
extensions).

```bash
CLOUDFLARE_API_TOKEN=... \
CLOUDFLARE_ACCOUNT_ID=... \
COOKIE_SECRET=... \
COOKIE_SECRET_PREVIOUS=... \
./infra/deploy-edge.sh
```

`deploy-edge.sh` remains useful for an edge-only repair. Normally use
`deploy.sh`, which refuses uncommitted build inputs, regenerates the engine
package, synchronizes both cookie verification keys, and purges the previous
edge objects after the new application and Worker versions are active.

The worker stores engine responses at the edge for 24 hours. The engine build
stamps one content-derived version across its manifest, JS, WASM, and runtime
file URLs, so browsers can keep those URLs for one year with `immutable` while
a changed build gets a new URL.

The same script installs a Cache Rule for the shared application shell at `/`
and `/create`. Browsers keep that HTML for 15 seconds, while Cloudflare keeps it
for 30 seconds and may serve it stale during background revalidation. User and
session data remain on uncached `/api/*` requests. On each HTML edge-cache
miss, the Node server embeds the current public character roster into the Vite
shell so the grid can render without waiting for Cloud Run. The shared HTML
never includes cookie-derived/private fighters; after session discovery, a
signed-in browser refreshes the roster through the no-store characters API and
reconciles any additional fighters into the live grid.

Before Cloud Build, deployment reads `config/characters.json` and the committed
`config/baked-assets.json` checksum manifest, then materializes exactly those
baked runtime files from the public GCS bucket. The API image never copies the
git-ignored local `pipeline/play` workspace or character bundles from ignored
`BattleShip/web-dist`, so identical Git commits produce identical baked rosters
and bundle bytes.

Publish a new baked roster only after reviewing the generated local `play/`
outputs. Object keys contain the SHA-256 digest, so publishing is additive and
existing deployments remain reproducible:

```bash
PUBLIC_BUCKET="${PROJECT_ID}-fighter-assets" pnpm assets:publish
git add config/baked-assets.json
```

To verify or materialize the committed roster without deploying:

```bash
PUBLIC_BUCKET="${PROJECT_ID}-fighter-assets" pnpm assets:fetch
```

Rotate the shared cookie signing key with overlap after a full deploy has added
the previous-key secret to both Cloud Run and Cloudflare:

```bash
PROJECT_ID=... REGION=... \
CLOUDFLARE_API_TOKEN=... CLOUDFLARE_ACCOUNT_ID=... \
./infra/rotate-cookie-secret.sh
```

The rotation activates the new key and retains the former key as
`COOKIE_SECRET_PREVIOUS`, so existing 30-day ROM-validation cookies continue to
work. Do not update either provider's copy manually.

## Rollback

Every deploy uses timestamped API and worker image tags. Repoint the API or job
without rebuilding:

```bash
gcloud run services update opensmash-web --region "$REGION" --image API_IMAGE
gcloud run jobs update opensmash-fighter-worker --region "$REGION" --image WORKER_IMAGE
```
