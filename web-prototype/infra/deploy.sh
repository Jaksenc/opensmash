#!/usr/bin/env bash
set -euo pipefail

required=(PROJECT_ID REGION PUBLIC_ORIGIN FIREBASE_API_KEY FIREBASE_APP_ID CLOUDFLARE_API_TOKEN CLOUDFLARE_ACCOUNT_ID)
for name in "${required[@]}"; do
  if [[ -z "${!name:-}" ]]; then
    echo "$name is required" >&2
    exit 2
  fi
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
BATTLESHIP_ROOT="$WORKSPACE_ROOT/BattleShip"
SERVICE_NAME="${SERVICE_NAME:-opensmash-web}"
WORKER_JOB="${WORKER_JOB:-opensmash-fighter-worker}"
ARTIFACT_REPOSITORY="${ARTIFACT_REPOSITORY:-opensmash}"
PRIVATE_BUCKET="${PRIVATE_BUCKET:-${PROJECT_ID}-fighter-sources}"
PUBLIC_BUCKET="${PUBLIC_BUCKET:-${PROJECT_ID}-fighter-assets}"
ASSET_BASE_URL="${ASSET_BASE_URL:-https://storage.googleapis.com/${PUBLIC_BUCKET}}"
API_SERVICE_ACCOUNT="${API_SERVICE_ACCOUNT:-opensmash-api}"
WORKER_SERVICE_ACCOUNT="${WORKER_SERVICE_ACCOUNT:-opensmash-worker}"
API_IDENTITY="${API_SERVICE_ACCOUNT}@${PROJECT_ID}.iam.gserviceaccount.com"
WORKER_IDENTITY="${WORKER_SERVICE_ACCOUNT}@${PROJECT_ID}.iam.gserviceaccount.com"
FIREBASE_AUTH_DOMAIN="${FIREBASE_AUTH_DOMAIN:-${PROJECT_ID}.firebaseapp.com}"
IMAGE_ROOT="${REGION}-docker.pkg.dev/${PROJECT_ID}/${ARTIFACT_REPOSITORY}"
VERSION="${VERSION:-$(date -u +%Y%m%d-%H%M%S)}"
API_IMAGE="${IMAGE_ROOT}/web:${VERSION}"
WORKER_IMAGE="${IMAGE_ROOT}/worker:${VERSION}"
COOKIE_SECRET_NAME="${COOKIE_SECRET_NAME:-opensmash-cookie-secret}"
COOKIE_SECRET_PREVIOUS_NAME="${COOKIE_SECRET_PREVIOUS_NAME:-opensmash-cookie-secret-previous}"
DOMAIN="${DOMAIN:-${PUBLIC_ORIGIN#https://}}"
DOMAIN="${DOMAIN%/}"

assert_clean_source() {
  local repo="$1"
  local label="$2"
  shift 2
  local changes
  changes="$(git -C "$repo" status --porcelain --untracked-files=normal -- "$@")"
  if [[ -n "$changes" ]]; then
    echo "$label has source changes that are not committed:" >&2
    printf '%s\n' "$changes" >&2
    echo "Commit or stash them before deploying so Cloud Build receives a reproducible tree." >&2
    exit 2
  fi
}

# Cloud Build uploads the local filesystem, so fail before any remote mutation
# if a file included by either Docker context could differ from a commit.
assert_clean_source "$WORKSPACE_ROOT/pipeline" pipeline \
  web-prototype pipeline skels assets/portrait_style_refs assets/tpose_style_ref
assert_clean_source "$BATTLESHIP_ROOT" BattleShip web scripts port/css_icons torch

# The engine package no longer ships the ROM-derived archive; the browser
# builds it with Torch compiled to wasm (BattleShip/docs/web_rom_extraction.md).
# Build that module from the committed torch submodule + port sources so the
# image never ships a stale one. Needs an activated emsdk (emcmake on PATH),
# same as the engine's own build-wasm.
if ! command -v emcmake >/dev/null 2>&1; then
  echo "emcmake not found: activate emsdk (source emsdk/emsdk_env.sh) before deploying." >&2
  exit 2
fi
"$BATTLESHIP_ROOT/scripts/build_torch_wasm.sh"

# Always regenerate the complete engine package. package_web.sh derives one
# version from every runtime input and preserves separately built bundles.
# It exits non-zero if the Torch module is missing, so a deploy can never
# produce an engine with no way to obtain BattleShip.o2r.
"$BATTLESHIP_ROOT/scripts/package_web.sh" \
  "$BATTLESHIP_ROOT/build-wasm" "$BATTLESHIP_ROOT/web-dist"
for required in torch/torch.wasm torch/recipe.json rom-extract.js torch-worker.js; do
  if [[ ! -f "$BATTLESHIP_ROOT/web-dist/$required" ]]; then
    echo "web-dist is missing $required; the engine could not build its assets in the browser." >&2
    exit 2
  fi
done
if [[ -f "$BATTLESHIP_ROOT/web-dist/files/BattleShip.o2r" ]]; then
  echo "web-dist/files/BattleShip.o2r is present: refusing to deploy a package that ships ROM-derived assets." >&2
  exit 2
fi

gcloud config set project "$PROJECT_ID"
gcloud services enable \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  firestore.googleapis.com \
  identitytoolkit.googleapis.com \
  run.googleapis.com \
  secretmanager.googleapis.com \
  storage.googleapis.com

gcloud firestore databases describe --database='(default)' >/dev/null
# ROM-handoff signalling rooms live in Firestore so every API replica can serve
# either side of a handoff; a TTL policy on expireAt sweeps stale rooms.
gcloud firestore fields ttls update expireAt \
  --collection-group=handoffRooms --enable-ttl --quiet >/dev/null 2>&1 || true

if ! gcloud artifacts repositories describe "$ARTIFACT_REPOSITORY" --location "$REGION" >/dev/null 2>&1; then
  gcloud artifacts repositories create "$ARTIFACT_REPOSITORY" \
    --location "$REGION" --repository-format docker
fi

for bucket in "$PRIVATE_BUCKET" "$PUBLIC_BUCKET"; do
  if ! gcloud storage buckets describe "gs://${bucket}" >/dev/null 2>&1; then
    gcloud storage buckets create "gs://${bucket}" \
      --location "$REGION" --uniform-bucket-level-access
  fi
done
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member "serviceAccount:${API_IDENTITY}" --role roles/firebaseauth.admin >/dev/null

cors_file="$(mktemp)"
trap 'trash "$cors_file" 2>/dev/null || rm "$cors_file"' EXIT
printf '[{"origin":["%s"],"method":["GET","HEAD"],"responseHeader":["Content-Type","Content-Length","ETag"],"maxAgeSeconds":3600}]\n' \
  "$PUBLIC_ORIGIN" > "$cors_file"
gcloud storage buckets update "gs://${PUBLIC_BUCKET}" --cors-file "$cors_file"
gcloud storage buckets add-iam-policy-binding "gs://${PUBLIC_BUCKET}" \
  --member allUsers --role roles/storage.objectViewer

for account in "$API_SERVICE_ACCOUNT" "$WORKER_SERVICE_ACCOUNT"; do
  if ! gcloud iam service-accounts describe "${account}@${PROJECT_ID}.iam.gserviceaccount.com" >/dev/null 2>&1; then
    gcloud iam service-accounts create "$account"
  fi
done

for identity in "$API_IDENTITY" "$WORKER_IDENTITY"; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member "serviceAccount:${identity}" --role roles/datastore.user >/dev/null
done
gcloud storage buckets add-iam-policy-binding "gs://${PRIVATE_BUCKET}" \
  --member "serviceAccount:${API_IDENTITY}" --role roles/storage.objectAdmin >/dev/null
gcloud storage buckets add-iam-policy-binding "gs://${PRIVATE_BUCKET}" \
  --member "serviceAccount:${WORKER_IDENTITY}" --role roles/storage.objectAdmin >/dev/null
gcloud storage buckets add-iam-policy-binding "gs://${PUBLIC_BUCKET}" \
  --member "serviceAccount:${WORKER_IDENTITY}" --role roles/storage.objectAdmin >/dev/null
for bucket in "$PRIVATE_BUCKET" "$PUBLIC_BUCKET"; do
  for identity in "$API_IDENTITY" "$WORKER_IDENTITY"; do
    gcloud storage buckets add-iam-policy-binding "gs://${bucket}" \
      --member "serviceAccount:${identity}" --role roles/storage.bucketViewer >/dev/null
  done
done

for secret in "$COOKIE_SECRET_NAME" opensmash-openai-api-key opensmash-tripo-api-key opensmash-fal-key opensmash-minimax-voice-id; do
  gcloud secrets describe "$secret" >/dev/null
done
if ! gcloud secrets describe "$COOKIE_SECRET_PREVIOUS_NAME" >/dev/null 2>&1; then
  gcloud secrets create "$COOKIE_SECRET_PREVIOUS_NAME" --replication-policy=automatic >/dev/null
  gcloud secrets versions access latest --secret "$COOKIE_SECRET_NAME" | \
    gcloud secrets versions add "$COOKIE_SECRET_PREVIOUS_NAME" --data-file=- >/dev/null
fi
gcloud secrets add-iam-policy-binding "$COOKIE_SECRET_NAME" \
  --member "serviceAccount:${API_IDENTITY}" --role roles/secretmanager.secretAccessor >/dev/null
gcloud secrets add-iam-policy-binding "$COOKIE_SECRET_PREVIOUS_NAME" \
  --member "serviceAccount:${API_IDENTITY}" --role roles/secretmanager.secretAccessor >/dev/null
gcloud secrets add-iam-policy-binding opensmash-openai-api-key \
  --member "serviceAccount:${API_IDENTITY}" --role roles/secretmanager.secretAccessor >/dev/null
for secret in opensmash-openai-api-key opensmash-tripo-api-key opensmash-fal-key opensmash-minimax-voice-id; do
  gcloud secrets add-iam-policy-binding "$secret" \
    --member "serviceAccount:${WORKER_IDENTITY}" --role roles/secretmanager.secretAccessor >/dev/null
done

# Materialize the content-addressed, checksum-pinned baked roster from GCS.
# Generated play/ outputs are deliberately absent from Git and the build context.
PUBLIC_BUCKET="$PUBLIC_BUCKET" \
  node "$WORKSPACE_ROOT/pipeline/web-prototype/scripts/fetch-baked-characters.mjs"

cd "$WORKSPACE_ROOT"
gcloud builds submit . \
  --ignore-file pipeline/web-prototype/docker/api.Dockerfile.dockerignore \
  --config pipeline/web-prototype/infra/cloudbuild-api.yaml \
  --substitutions "_IMAGE=${API_IMAGE}"
gcloud builds submit . \
  --ignore-file pipeline/web-prototype/docker/worker.Dockerfile.dockerignore \
  --config pipeline/web-prototype/infra/cloudbuild-worker.yaml \
  --substitutions "_IMAGE=${WORKER_IMAGE}"

gcloud run jobs deploy "$WORKER_JOB" \
  --image "$WORKER_IMAGE" \
  --region "$REGION" \
  --service-account "$WORKER_IDENTITY" \
  --cpu 4 --memory 8Gi \
  --task-timeout 3600s --max-retries 0 --tasks 1 --parallelism 1 \
  --set-env-vars "JOB_DATABASE=firestore,OBJECT_STORE=gcs,FIGHTER_JOBS_ROOT=/tmp/fighter-jobs,GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GCS_PRIVATE_BUCKET=${PRIVATE_BUCKET},GCS_PUBLIC_BUCKET=${PUBLIC_BUCKET},ASSET_BASE_URL=${ASSET_BASE_URL}" \
  --set-secrets "OPENAI_API_KEY=opensmash-openai-api-key:latest,TRIPO_API_KEY=opensmash-tripo-api-key:latest,FAL_KEY=opensmash-fal-key:latest,MINIMAX_ANNOUNCER_VOICE_ID=opensmash-minimax-voice-id:latest"

gcloud run jobs add-iam-policy-binding "$WORKER_JOB" \
  --region "$REGION" \
  --member "serviceAccount:${API_IDENTITY}" \
  --role roles/run.invoker >/dev/null

gcloud run deploy "$SERVICE_NAME" \
  --image "$API_IMAGE" \
  --region "$REGION" \
  --service-account "$API_IDENTITY" \
  --allow-unauthenticated \
  --ingress internal-and-cloud-load-balancing \
  --port 8080 --cpu 1 --memory 1Gi --concurrency 200 \
  --min-instances 0 --max-instances 1 --timeout 3600 \
  --set-env-vars "JOB_DATABASE=firestore,OBJECT_STORE=gcs,FIGHTER_JOBS_ROOT=/tmp/fighter-jobs,FIGHTER_EXECUTION_MODE=cloud-run,GOOGLE_CLOUD_PROJECT=${PROJECT_ID},CLOUD_RUN_REGION=${REGION},CLOUD_RUN_WORKER_JOB=${WORKER_JOB},GCS_PRIVATE_BUCKET=${PRIVATE_BUCKET},GCS_PUBLIC_BUCKET=${PUBLIC_BUCKET},ASSET_BASE_URL=${ASSET_BASE_URL},ALLOWED_ORIGINS=${PUBLIC_ORIGIN},FIREBASE_AUTH_ENABLED=1,FIREBASE_PROJECT_ID=${PROJECT_ID},FIREBASE_API_KEY=${FIREBASE_API_KEY},FIREBASE_AUTH_DOMAIN=${FIREBASE_AUTH_DOMAIN},FIREBASE_APP_ID=${FIREBASE_APP_ID},FIREBASE_AUTH_PROVIDERS=google|apple|email,FIGHTER_MODERATION_ENABLED=1" \
  --set-secrets "COOKIE_SECRET=${COOKIE_SECRET_NAME}:latest,COOKIE_SECRET_PREVIOUS=${COOKIE_SECRET_PREVIOUS_NAME}:latest,OPENAI_API_KEY=opensmash-openai-api-key:latest"

cookie_secret="$(gcloud secrets versions access latest --secret "$COOKIE_SECRET_NAME")"
cookie_secret_previous="$(gcloud secrets versions access latest --secret "$COOKIE_SECRET_PREVIOUS_NAME")"
COOKIE_SECRET="$cookie_secret" \
COOKIE_SECRET_PREVIOUS="$cookie_secret_previous" \
DOMAIN="$DOMAIN" \
  "$SCRIPT_DIR/deploy-edge.sh"

echo "Deployed ${SERVICE_NAME}, ${WORKER_JOB}, and Cloudflare edge at version ${VERSION}."
