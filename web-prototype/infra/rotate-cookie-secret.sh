#!/usr/bin/env bash
set -euo pipefail

required=(PROJECT_ID REGION CLOUDFLARE_API_TOKEN CLOUDFLARE_ACCOUNT_ID)
for name in "${required[@]}"; do
  if [[ -z "${!name:-}" ]]; then
    echo "$name is required" >&2
    exit 2
  fi
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="${SERVICE_NAME:-opensmash-web}"
COOKIE_SECRET_NAME="${COOKIE_SECRET_NAME:-opensmash-cookie-secret}"
COOKIE_SECRET_PREVIOUS_NAME="${COOKIE_SECRET_PREVIOUS_NAME:-opensmash-cookie-secret-previous}"
WRANGLER_VERSION="${WRANGLER_VERSION:-4.34.0}"
new_secret="${NEW_COOKIE_SECRET:-$(openssl rand -base64 48 | tr -d '\n')}"
export CLOUDFLARE_API_TOKEN CLOUDFLARE_ACCOUNT_ID

put_edge_secret() {
  local name="$1"
  local value="$2"
  printf '%s' "$value" | \
    npx --yes "wrangler@${WRANGLER_VERSION}" secret put "$name" \
      --config "$SCRIPT_DIR/wrangler.jsonc"
}

gcloud config set project "$PROJECT_ID" >/dev/null
service_json="$(gcloud run services describe "$SERVICE_NAME" --region "$REGION" --format=json)"
if ! printf '%s' "$service_json" | jq -e --arg secret "$COOKIE_SECRET_PREVIOUS_NAME" \
  '[.spec.template.spec.containers[].env[]? | select(.valueFrom.secretKeyRef.name == $secret)] | length > 0' >/dev/null; then
  echo "$SERVICE_NAME must first be deployed with COOKIE_SECRET_PREVIOUS support." >&2
  exit 2
fi

current_secret="$(gcloud secrets versions access latest --secret "$COOKIE_SECRET_NAME")"
if [[ "$new_secret" == "$current_secret" ]]; then
  echo "The new cookie secret must differ from the current secret." >&2
  exit 2
fi

if ! gcloud secrets describe "$COOKIE_SECRET_PREVIOUS_NAME" >/dev/null 2>&1; then
  gcloud secrets create "$COOKIE_SECRET_PREVIOUS_NAME" --replication-policy=automatic >/dev/null
fi

echo "==> Preserving the current key as the overlap key"
printf '%s' "$current_secret" | \
  gcloud secrets versions add "$COOKIE_SECRET_PREVIOUS_NAME" --data-file=- >/dev/null
put_edge_secret COOKIE_SECRET_PREVIOUS "$current_secret"

# Update the edge first. It now accepts the new key and the old overlap key,
# while the origin still signs with the old key. This order avoids a window in
# which a newly signed cookie is rejected at Cloudflare.
echo "==> Activating the new key at the edge"
put_edge_secret COOKIE_SECRET "$new_secret"

echo "==> Activating the new key at the origin"
if ! new_version_name="$(printf '%s' "$new_secret" | \
  gcloud secrets versions add "$COOKIE_SECRET_NAME" --data-file=- --format='value(name)')"; then
  put_edge_secret COOKIE_SECRET "$current_secret"
  echo "Failed to add the new origin secret; the edge key was restored." >&2
  exit 1
fi
new_version="${new_version_name##*/}"

rotation_marker="$(date -u +%Y%m%d-%H%M%S)"
if ! gcloud run services update "$SERVICE_NAME" \
  --region "$REGION" \
  --update-secrets "COOKIE_SECRET=${COOKIE_SECRET_NAME}:latest,COOKIE_SECRET_PREVIOUS=${COOKIE_SECRET_PREVIOUS_NAME}:latest" \
  --update-env-vars "COOKIE_SECRET_ROTATED_AT=${rotation_marker}"; then
  gcloud secrets versions disable "$new_version" --secret "$COOKIE_SECRET_NAME" --quiet >/dev/null
  put_edge_secret COOKIE_SECRET "$current_secret"
  echo "Cloud Run did not activate the new key; the new version was disabled and the edge key restored." >&2
  exit 1
fi

echo "Cookie signing key rotated. Existing cookies remain valid through COOKIE_SECRET_PREVIOUS."
