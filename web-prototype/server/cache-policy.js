export const DEVELOPMENT_CACHE_CONTROL = "no-store";

export function cacheControlForEnvironment(productionPolicy, isProduction) {
  return isProduction ? productionPolicy : DEVELOPMENT_CACHE_CONTROL;
}

export function edgeCacheHeaders(productionPolicy, isProduction) {
  return isProduction
    ? { "Cloudflare-CDN-Cache-Control": productionPolicy }
    : {};
}
