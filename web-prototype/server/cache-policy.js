export const DEVELOPMENT_CACHE_CONTROL = "no-store";
export const ENGINE_REVALIDATE_CACHE_CONTROL = "public, no-cache";
export const ENGINE_IMMUTABLE_CACHE_CONTROL = "public, max-age=31536000, immutable";
export const PRIVATE_ENGINE_BUNDLE_CACHE_CONTROL = "private, no-store";

export function engineCacheControl(relative, searchParams) {
  if (relative.startsWith("bundles/")) return PRIVATE_ENGINE_BUNDLE_CACHE_CONTROL;
  if (searchParams.has("v") && relative !== "index.html" && !relative.startsWith("bundles/")) {
    return ENGINE_IMMUTABLE_CACHE_CONTROL;
  }
  return ENGINE_REVALIDATE_CACHE_CONTROL;
}

export function cacheControlForEnvironment(productionPolicy, isProduction) {
  return isProduction ? productionPolicy : DEVELOPMENT_CACHE_CONTROL;
}

export function edgeCacheHeaders(productionPolicy, isProduction) {
  return isProduction
    ? { "Cloudflare-CDN-Cache-Control": productionPolicy }
    : {};
}
