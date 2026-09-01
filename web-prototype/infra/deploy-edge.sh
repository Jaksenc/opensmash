#!/usr/bin/env bash
set -euo pipefail

required=(CLOUDFLARE_API_TOKEN CLOUDFLARE_ACCOUNT_ID COOKIE_SECRET)
for name in "${required[@]}"; do
  if [[ -z "${!name:-}" ]]; then
    echo "$name is required" >&2
    exit 2
  fi
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOMAIN="${DOMAIN:-smashtheweights.com}"
WRANGLER_VERSION="${WRANGLER_VERSION:-4.34.0}"
export CLOUDFLARE_API_TOKEN CLOUDFLARE_ACCOUNT_ID

zone_response="$(curl -fsS -G "https://api.cloudflare.com/client/v4/zones" \
  -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" \
  --data-urlencode "name=${DOMAIN}" --data-urlencode "status=active")"
zone_id="$(printf '%s' "$zone_response" | jq -r '.result[0].id // ""')"
if [[ -z "$zone_id" ]]; then
  echo "Cloudflare zone not found for $DOMAIN" >&2
  exit 2
fi

echo "==> Deploying authenticated engine cache worker"
npx --yes "wrangler@${WRANGLER_VERSION}" deploy --config "$SCRIPT_DIR/wrangler.jsonc"
printf '%s' "$COOKIE_SECRET" | \
  npx --yes "wrangler@${WRANGLER_VERSION}" secret put COOKIE_SECRET \
    --config "$SCRIPT_DIR/wrangler.jsonc"

for hostname in "$DOMAIN" "www.${DOMAIN}"; do
  record_response="$(curl -fsS -G \
    "https://api.cloudflare.com/client/v4/zones/${zone_id}/dns_records" \
    -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" \
    --data-urlencode "type=A" --data-urlencode "name=${hostname}")"
  record_id="$(printf '%s' "$record_response" | jq -r '.result[0].id // ""')"
  record_content="$(printf '%s' "$record_response" | jq -r '.result[0].content // ""')"
  if [[ -z "$record_id" || -z "$record_content" ]]; then
    echo "A record not found for $hostname" >&2
    exit 2
  fi
  payload="$(jq -nc --arg name "$hostname" --arg content "$record_content" \
    '{type:"A", name:$name, content:$content, ttl:1, proxied:true}')"
  curl -fsS -X PUT \
    "https://api.cloudflare.com/client/v4/zones/${zone_id}/dns_records/${record_id}" \
    -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" \
    -H "Content-Type: application/json" --data "$payload" >/dev/null
done

curl -fsS -X PATCH \
  "https://api.cloudflare.com/client/v4/zones/${zone_id}/settings/ssl" \
  -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" \
  -H "Content-Type: application/json" --data '{"value":"strict"}' >/dev/null

curl -fsS -X POST \
  "https://api.cloudflare.com/client/v4/zones/${zone_id}/purge_cache" \
  -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" \
  -H "Content-Type: application/json" --data '{"purge_everything":true}' >/dev/null

echo "Cloudflare proxy and authenticated engine cache are active for $DOMAIN."
