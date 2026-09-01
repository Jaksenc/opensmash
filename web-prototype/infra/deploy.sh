#!/usr/bin/env bash
set -euo pipefail

required=(PROJECT_ID REGION PUBLIC_ORIGIN FIREBASE_API_KEY FIREBASE_APP_ID)
for name in "${required[@]}"; do
  if [[ -z "${!name:-}" ]]; then
    echo "$name is required" >&2
    exit 2
  fi
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
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

for secret in opensmash-cookie-secret opensmash-openai-api-key opensmash-tripo-api-key opensmash-fal-key opensmash-minimax-voice-id; do
  gcloud secrets describe "$secret" >/dev/null
done
gcloud secrets add-iam-policy-binding opensmash-cookie-secret \
  --member "serviceAccount:${API_IDENTITY}" --role roles/secretmanager.secretAccessor >/dev/null
gcloud secrets add-iam-policy-binding opensmash-openai-api-key \
  --member "serviceAccount:${API_IDENTITY}" --role roles/secretmanager.secretAccessor >/dev/null
for secret in opensmash-openai-api-key opensmash-tripo-api-key opensmash-fal-key opensmash-minimax-voice-id; do
  gcloud secrets add-iam-policy-binding "$secret" \
    --member "serviceAccount:${WORKER_IDENTITY}" --role roles/secretmanager.secretAccessor >/dev/null
done

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
  --port 8080 --cpu 1 --memory 1Gi --concurrency 40 \
  --min-instances 0 --max-instances 1 --timeout 3600 \
  --set-env-vars "JOB_DATABASE=firestore,OBJECT_STORE=gcs,FIGHTER_JOBS_ROOT=/tmp/fighter-jobs,FIGHTER_EXECUTION_MODE=cloud-run,GOOGLE_CLOUD_PROJECT=${PROJECT_ID},CLOUD_RUN_REGION=${REGION},CLOUD_RUN_WORKER_JOB=${WORKER_JOB},GCS_PRIVATE_BUCKET=${PRIVATE_BUCKET},GCS_PUBLIC_BUCKET=${PUBLIC_BUCKET},ASSET_BASE_URL=${ASSET_BASE_URL},ALLOWED_ORIGINS=${PUBLIC_ORIGIN},FIREBASE_AUTH_ENABLED=1,FIREBASE_PROJECT_ID=${PROJECT_ID},FIREBASE_API_KEY=${FIREBASE_API_KEY},FIREBASE_AUTH_DOMAIN=${FIREBASE_AUTH_DOMAIN},FIREBASE_APP_ID=${FIREBASE_APP_ID},FIREBASE_AUTH_PROVIDERS=google|apple|email,FIGHTER_MODERATION_ENABLED=1" \
  --set-secrets "COOKIE_SECRET=opensmash-cookie-secret:latest,OPENAI_API_KEY=opensmash-openai-api-key:latest"

echo "Deployed ${SERVICE_NAME} and ${WORKER_JOB} at version ${VERSION}."
