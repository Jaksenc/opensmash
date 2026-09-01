export function normalizeSearchText(value) {
  return String(value || "")
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

export function matchesCharacterSearch(character, query) {
  const terms = normalizeSearchText(query).split(/\s+/).filter(Boolean);
  if (!terms.length) return true;
  const haystack = normalizeSearchText([
    character.name,
    character.display,
    character.short,
    character.slug,
  ].filter(Boolean).join(" "));
  return terms.every((term) => haystack.includes(term));
}
