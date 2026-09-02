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

The API is initially capped at one instance so uploader quotas and
local upload parsing cannot race across replicas. Firestore leases still make
worker execution idempotent. Raise the API instance cap only after moving quota
reservation into a Firestore transaction.

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

## Cloudflare edge cache

The main `deploy.sh` command also deploys the engine worker after Cloud Run. It
validates the existing ROM-session cookie before looking up shared `/engine/*`
runtime files in Cloudflare's cache, then enables proxying for the apex and
`www` records. Private-capable `/engine/bundles/*` requests always bypass the
shared cache. Public content-hashed Vite assets use Cloudflare's normal static
cache.

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

Before Cloud Build, deployment reads `config/characters.json` and stages exactly
those baked fighters from committed `pipeline/play` outputs. The API image never
copies character bundles from ignored `BattleShip/web-dist`, so identical Git
commits produce identical baked rosters and bundle bytes.

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
