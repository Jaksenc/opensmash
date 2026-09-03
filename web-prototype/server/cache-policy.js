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

// Development serves everything no-store so edits show up on reload — except
// build-versioned engine files. Their URL carries the package hash (and the
// server rejects any other hash), so a stale copy can never be served, and
// caching them lets Chrome keep the compiled 7.5 MB wasm between launches
// instead of re-tiering it during the first seconds of every match.
export function cacheControlForEnvironment(productionPolicy, isProduction) {
  if (isProduction || productionPolicy === ENGINE_IMMUTABLE_CACHE_CONTROL) return productionPolicy;
  return DEVELOPMENT_CACHE_CONTROL;
}

export function edgeCacheHeaders(productionPolicy, isProduction) {
  return isProduction
    ? { "Cloudflare-CDN-Cache-Control": productionPolicy }
    : {};
}
