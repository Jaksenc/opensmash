const SLUG_PATTERN = /^[a-z0-9]+$/;

export function bakedRosterEntries(config) {
  if (!Array.isArray(config)) throw new Error("Baked character manifest must be an array");

  const seen = new Set();
  return config.map((source, index) => {
    const entry = typeof source === "string" ? { slug: source } : source;
    if (!entry || typeof entry !== "object" || !SLUG_PATTERN.test(entry.slug || "")) {
      throw new Error(`Invalid baked character at manifest index ${index}`);
    }
    if (seen.has(entry.slug)) throw new Error(`Duplicate baked character '${entry.slug}'`);
    seen.add(entry.slug);
    return { ...entry, slug: entry.slug };
  });
}

export function bakedRosterSlugs(config) {
  return bakedRosterEntries(config).map((entry) => entry.slug);
}
