#!/usr/bin/env bash
# Create a Cloudflare Realtime TURN key for the ROM handoff, store its two
# values in Secret Manager, and attach them to the running Cloud Run API.
# Idempotent: re-running adds new secret versions and re-points the service.
#
#   CLOUDFLARE_API_TOKEN=... ./infra/enable-turn.sh            # scoped token (Calls: Edit)
#   CLOUDFLARE_API_KEY=... CLOUDFLARE_EMAIL=... ./infra/enable-turn.sh   # legacy Global API Key
#
# CLOUDFLARE_ACCOUNT_ID is optional when the credential sees exactly one
# account. TURN must be enabled for the account first (dashboard → Realtime →
# TURN). After this, https://<domain>/healthz should report
# "handoffIce":"cloudflare".
set -euo pipefail

cf_auth=()
if [[ -n "${CLOUDFLARE_API_TOKEN:-}" ]]; then
  cf_auth=(-H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}")
elif [[ -n "${CLOUDFLARE_API_KEY:-}" && -n "${CLOUDFLARE_EMAIL:-}" ]]; then
  cf_auth=(-H "X-Auth-Email: ${CLOUDFLARE_EMAIL}" -H "X-Auth-Key: ${CLOUDFLARE_API_KEY}")
else
  echo "set CLOUDFLARE_API_TOKEN, or CLOUDFLARE_API_KEY + CLOUDFLARE_EMAIL" >&2
  exit 1
fi
if [[ -z "${CLOUDFLARE_ACCOUNT_ID:-}" ]]; then
  CLOUDFLARE_ACCOUNT_ID="$(curl -fsS "https://api.cloudflare.com/client/v4/accounts?per_page=5" "${cf_auth[@]}" |
    python3 -c 'import json,sys; r=json.load(sys.stdin)["result"]; assert len(r)==1, f"{len(r)} accounts visible; set CLOUDFLARE_ACCOUNT_ID"; print(r[0]["id"])')"
fi
PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${REGION:-us-central1}"
SERVICE_NAME="${SERVICE_NAME:-opensmash-web}"
KEY_NAME="${TURN_KEY_NAME:-opensmash-rom-handoff}"
ID_SECRET=opensmash-cloudflare-turn-key-id
TOKEN_SECRET=opensmash-cloudflare-turn-key-token

echo "Creating TURN key '${KEY_NAME}' on Cloudflare account ${CLOUDFLARE_ACCOUNT_ID}…"
response="$(curl -fsS -X POST \
  "https://api.cloudflare.com/client/v4/accounts/${CLOUDFLARE_ACCOUNT_ID}/calls/turn_keys" \
  "${cf_auth[@]}" \
  -H "Content-Type: application/json" \
  --data "{\"name\":\"${KEY_NAME}\"}")"
key_id="$(printf '%s' "$response" | python3 -c 'import json,sys; r=json.load(sys.stdin); assert r.get("success"), r; print(r["result"]["uid"])')"
key_token="$(printf '%s' "$response" | python3 -c 'import json,sys; print(json.load(sys.stdin)["result"]["secret"])')"
echo "TURN key id: ${key_id}"

store() {
  local name="$1" value="$2"
  if gcloud secrets describe "$name" --project "$PROJECT_ID" >/dev/null 2>&1; then
    printf '%s' "$value" | gcloud secrets versions add "$name" --project "$PROJECT_ID" --data-file=- >/dev/null
  else
    printf '%s' "$value" | gcloud secrets create "$name" --project "$PROJECT_ID" --replication-policy=automatic --data-file=- >/dev/null
  fi
}
store "$ID_SECRET" "$key_id"
store "$TOKEN_SECRET" "$key_token"
echo "Stored ${ID_SECRET} and ${TOKEN_SECRET}."

api_identity="$(gcloud run services describe "$SERVICE_NAME" --region "$REGION" --project "$PROJECT_ID" --format='value(spec.template.spec.serviceAccountName)')"
for secret in "$ID_SECRET" "$TOKEN_SECRET"; do
  gcloud secrets add-iam-policy-binding "$secret" --project "$PROJECT_ID" \
    --member "serviceAccount:${api_identity}" --role roles/secretmanager.secretAccessor >/dev/null
done

echo "Attaching secrets to Cloud Run service ${SERVICE_NAME} (${REGION})…"
gcloud run services update "$SERVICE_NAME" --region "$REGION" --project "$PROJECT_ID" --quiet \
  --update-secrets "CLOUDFLARE_TURN_KEY_ID=${ID_SECRET}:latest,CLOUDFLARE_TURN_KEY_API_TOKEN=${TOKEN_SECRET}:latest" >/dev/null

url="$(gcloud run services describe "$SERVICE_NAME" --region "$REGION" --project "$PROJECT_ID" --format='value(status.url)')"
echo "Done. Health: $(curl -fsS "${url}/healthz" 2>/dev/null || echo '(service URL not directly reachable; check https://smash.fun/healthz)')"
echo "Expect \"handoffIce\":\"cloudflare\". deploy.sh will keep the secrets mounted on future deploys."
