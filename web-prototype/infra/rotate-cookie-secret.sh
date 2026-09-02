#!/usr/bin/env bash
set -euo pipefail

required=(PROJECT_ID REGION)
for name in "${required[@]}"; do
  if [[ -z "${!name:-}" ]]; then
    echo "$name is required" >&2
    exit 2
  fi
done

SERVICE_NAME="${SERVICE_NAME:-opensmash-web}"
COOKIE_SECRET_NAME="${COOKIE_SECRET_NAME:-opensmash-cookie-secret}"
COOKIE_SECRET_PREVIOUS_NAME="${COOKIE_SECRET_PREVIOUS_NAME:-opensmash-cookie-secret-previous}"
new_secret="${NEW_COOKIE_SECRET:-$(openssl rand -base64 48 | tr -d '\n')}"

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

echo "==> Activating the new key at the origin"
new_version_name="$(printf '%s' "$new_secret" | \
  gcloud secrets versions add "$COOKIE_SECRET_NAME" --data-file=- --format='value(name)')"
new_version="${new_version_name##*/}"

rotation_marker="$(date -u +%Y%m%d-%H%M%S)"
if ! gcloud run services update "$SERVICE_NAME" \
  --region "$REGION" \
  --update-secrets "COOKIE_SECRET=${COOKIE_SECRET_NAME}:latest,COOKIE_SECRET_PREVIOUS=${COOKIE_SECRET_PREVIOUS_NAME}:latest" \
  --update-env-vars "COOKIE_SECRET_ROTATED_AT=${rotation_marker}"; then
  gcloud secrets versions disable "$new_version" --secret "$COOKIE_SECRET_NAME" --quiet >/dev/null
  echo "Cloud Run did not activate the new key; the new version was disabled." >&2
  exit 1
fi

echo "Cookie signing key rotated. Existing cookies remain valid through COOKIE_SECRET_PREVIOUS."
