#!/usr/bin/env bash
set -euo pipefail

required=(PROJECT_ID REGION DOMAIN CLOUDFLARE_API_TOKEN)
for name in "${required[@]}"; do
  if [[ -z "${!name:-}" ]]; then
    echo "$name is required" >&2
    exit 2
  fi
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="${SERVICE_NAME:-opensmash-web}"
PREFIX="${PREFIX:-opensmash-web}"
CERT_PREFIX="${CERT_PREFIX:-opensmash}"
WWW_DOMAIN="www.${DOMAIN}"
CERT_WAIT_SECONDS="${CERT_WAIT_SECONDS:-1800}"

gcloud services enable compute.googleapis.com certificatemanager.googleapis.com \
  --project "$PROJECT_ID"

zone_response="$(curl -fsS "https://api.cloudflare.com/client/v4/zones?name=${DOMAIN}&status=active" \
  -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}")"
zone_id="$(printf '%s' "$zone_response" | jq -r '.result[0].id // ""')"
if [[ -z "$zone_id" ]]; then
  echo "Cloudflare zone not found for $DOMAIN" >&2
  exit 2
fi

upsert_dns_record() {
  local record_type="$1"
  local record_name="$2"
  local record_content="$3"
  local proxied="${4:-false}"
  local records_response record_id payload response
  records_response="$(curl -fsS -G \
    "https://api.cloudflare.com/client/v4/zones/${zone_id}/dns_records" \
    -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" \
    --data-urlencode "type=${record_type}" --data-urlencode "name=${record_name}")"
  record_id="$(printf '%s' "$records_response" | jq -r '.result[0].id // ""')"
  payload="$(jq -nc --arg type "$record_type" --arg name "$record_name" \
    --arg content "$record_content" --argjson proxied "$proxied" \
    '{type:$type, name:$name, content:$content, ttl:1, proxied:$proxied}')"
  if [[ -z "$record_id" ]]; then
    response="$(curl -fsS -X POST \
      "https://api.cloudflare.com/client/v4/zones/${zone_id}/dns_records" \
      -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" \
      -H 'Content-Type: application/json' --data "$payload")"
  else
    response="$(curl -fsS -X PUT \
      "https://api.cloudflare.com/client/v4/zones/${zone_id}/dns_records/${record_id}" \
      -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" \
      -H 'Content-Type: application/json' --data "$payload")"
  fi
  if [[ "$(printf '%s' "$response" | jq -r '.success')" != true ]]; then
    printf '%s\n' "$response" | jq '{errors}' >&2
    exit 2
  fi
}

create_dns_authorization() {
  local authorization_name="$1"
  local domain="$2"
  if ! gcloud certificate-manager dns-authorizations describe "$authorization_name" \
    --location=global --project "$PROJECT_ID" >/dev/null 2>&1; then
    gcloud certificate-manager dns-authorizations create "$authorization_name" \
      --domain="$domain" --location=global --project "$PROJECT_ID"
  fi
  local cname_name cname_data
  cname_name="$(gcloud certificate-manager dns-authorizations describe "$authorization_name" \
    --location=global --project "$PROJECT_ID" \
    --format='value(dnsResourceRecord.name)' | sed 's/\.$//')"
  cname_data="$(gcloud certificate-manager dns-authorizations describe "$authorization_name" \
    --location=global --project "$PROJECT_ID" \
    --format='value(dnsResourceRecord.data)' | sed 's/\.$//')"
  upsert_dns_record CNAME "$cname_name" "$cname_data"
}

create_dns_authorization "${CERT_PREFIX}-apex-auth" "$DOMAIN"
create_dns_authorization "${CERT_PREFIX}-www-auth" "$WWW_DOMAIN"

if ! gcloud certificate-manager certificates describe "${CERT_PREFIX}-apex-cert-dns" \
  --location=global --project "$PROJECT_ID" >/dev/null 2>&1; then
  gcloud certificate-manager certificates create "${CERT_PREFIX}-apex-cert-dns" \
    --domains="$DOMAIN" --dns-authorizations="${CERT_PREFIX}-apex-auth" \
    --scope=default --location=global --project "$PROJECT_ID"
fi
if ! gcloud certificate-manager certificates describe "${CERT_PREFIX}-www-cert-dns" \
  --location=global --project "$PROJECT_ID" >/dev/null 2>&1; then
  gcloud certificate-manager certificates create "${CERT_PREFIX}-www-cert-dns" \
    --domains="$WWW_DOMAIN" --dns-authorizations="${CERT_PREFIX}-www-auth" \
    --scope=default --location=global --project "$PROJECT_ID"
fi
if ! gcloud certificate-manager maps describe "${PREFIX}-cert-map" \
  --location=global --project "$PROJECT_ID" >/dev/null 2>&1; then
  gcloud certificate-manager maps create "${PREFIX}-cert-map" \
    --location=global --project "$PROJECT_ID"
fi
if ! gcloud certificate-manager maps entries describe "${CERT_PREFIX}-apex-entry" \
  --map="${PREFIX}-cert-map" --location=global --project "$PROJECT_ID" >/dev/null 2>&1; then
  gcloud certificate-manager maps entries create "${CERT_PREFIX}-apex-entry" \
    --map="${PREFIX}-cert-map" --certificates="${CERT_PREFIX}-apex-cert-dns" \
    --hostname="$DOMAIN" --location=global --project "$PROJECT_ID"
fi
if ! gcloud certificate-manager maps entries describe "${CERT_PREFIX}-www-entry" \
  --map="${PREFIX}-cert-map" --location=global --project "$PROJECT_ID" >/dev/null 2>&1; then
  gcloud certificate-manager maps entries create "${CERT_PREFIX}-www-entry" \
    --map="${PREFIX}-cert-map" --certificates="${CERT_PREFIX}-www-cert-dns" \
    --hostname="$WWW_DOMAIN" --location=global --project "$PROJECT_ID"
fi

if ! gcloud compute addresses describe "${PREFIX}-ip" --global --project "$PROJECT_ID" >/dev/null 2>&1; then
  gcloud compute addresses create "${PREFIX}-ip" --global --ip-version=IPV4 \
    --network-tier=PREMIUM --project "$PROJECT_ID"
fi
if ! gcloud compute network-endpoint-groups describe "${PREFIX}-neg" --region "$REGION" --project "$PROJECT_ID" >/dev/null 2>&1; then
  gcloud compute network-endpoint-groups create "${PREFIX}-neg" --region "$REGION" \
    --network-endpoint-type=serverless --cloud-run-service="$SERVICE_NAME" --project "$PROJECT_ID"
fi
if ! gcloud compute backend-services describe "${PREFIX}-backend" --global --project "$PROJECT_ID" >/dev/null 2>&1; then
  gcloud compute backend-services create "${PREFIX}-backend" --global \
    --load-balancing-scheme=EXTERNAL_MANAGED --protocol=HTTP --project "$PROJECT_ID"
  gcloud compute backend-services add-backend "${PREFIX}-backend" --global \
    --network-endpoint-group="${PREFIX}-neg" --network-endpoint-group-region="$REGION" \
    --project "$PROJECT_ID"
fi
if ! gcloud compute url-maps describe "${PREFIX}-map" --global --project "$PROJECT_ID" >/dev/null 2>&1; then
  gcloud compute url-maps create "${PREFIX}-map" --global \
    --default-service="${PREFIX}-backend" --project "$PROJECT_ID"
fi
elapsed=0
while [[ "$(gcloud certificate-manager certificates describe "${CERT_PREFIX}-apex-cert-dns" \
  --location=global --project "$PROJECT_ID" --format='value(managed.state)')" != ACTIVE ||
  "$(gcloud certificate-manager certificates describe "${CERT_PREFIX}-www-cert-dns" \
  --location=global --project "$PROJECT_ID" --format='value(managed.state)')" != ACTIVE ]]; do
  if (( elapsed >= CERT_WAIT_SECONDS )); then
    echo "Certificate did not become ACTIVE within ${CERT_WAIT_SECONDS}s; HTTPS proxy was not changed" >&2
    exit 1
  fi
  sleep 15
  ((elapsed += 15))
done
if ! gcloud compute target-https-proxies describe "${PREFIX}-https-proxy" --global --project "$PROJECT_ID" >/dev/null 2>&1; then
  gcloud compute target-https-proxies create "${PREFIX}-https-proxy" --global \
    --url-map="${PREFIX}-map" --certificate-map="${PREFIX}-cert-map" --project "$PROJECT_ID"
else
  gcloud compute target-https-proxies update "${PREFIX}-https-proxy" --global \
    --certificate-map="${PREFIX}-cert-map" --project "$PROJECT_ID"
fi
if ! gcloud compute forwarding-rules describe "${PREFIX}-https" --global --project "$PROJECT_ID" >/dev/null 2>&1; then
  gcloud compute forwarding-rules create "${PREFIX}-https" --global \
    --load-balancing-scheme=EXTERNAL_MANAGED --network-tier=PREMIUM \
    --address="${PREFIX}-ip" --target-https-proxy="${PREFIX}-https-proxy" \
    --ports=443 --project "$PROJECT_ID"
fi

gcloud compute url-maps import opensmash-http-redirect --global \
  --source="$SCRIPT_DIR/http-redirect-url-map.yaml" --project "$PROJECT_ID" --quiet
if ! gcloud compute target-http-proxies describe "${PREFIX}-http-proxy" --global --project "$PROJECT_ID" >/dev/null 2>&1; then
  gcloud compute target-http-proxies create "${PREFIX}-http-proxy" --global \
    --url-map=opensmash-http-redirect --project "$PROJECT_ID"
fi
if ! gcloud compute forwarding-rules describe "${PREFIX}-http" --global --project "$PROJECT_ID" >/dev/null 2>&1; then
  gcloud compute forwarding-rules create "${PREFIX}-http" --global \
    --load-balancing-scheme=EXTERNAL_MANAGED --network-tier=PREMIUM \
    --address="${PREFIX}-ip" --target-http-proxy="${PREFIX}-http-proxy" \
    --ports=80 --project "$PROJECT_ID"
fi

load_balancer_ip="$(gcloud compute addresses describe "${PREFIX}-ip" --global \
  --project "$PROJECT_ID" --format='value(address)')"
upsert_dns_record A "$DOMAIN" "$load_balancer_ip" true
upsert_dns_record A "$WWW_DOMAIN" "$load_balancer_ip" true
gcloud run services update "$SERVICE_NAME" --region "$REGION" \
  --ingress=internal-and-cloud-load-balancing --project "$PROJECT_ID" >/dev/null
printf 'Load balancer and DNS configured for %s at %s\n' "$DOMAIN" "$load_balancer_ip"
