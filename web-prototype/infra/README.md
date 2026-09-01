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

## Build and deploy

From `pipeline/web-prototype`:

```bash
PROJECT_ID=your-project \
REGION=us-central1 \
PUBLIC_ORIGIN=https://example.com \
./infra/deploy.sh
```

The API is initially capped at one instance so anonymous-session quotas and
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

## Rollback

Every deploy uses timestamped API and worker image tags. Repoint the API or job
without rebuilding:

```bash
gcloud run services update opensmash-web --region "$REGION" --image API_IMAGE
gcloud run jobs update opensmash-fighter-worker --region "$REGION" --image WORKER_IMAGE
```
