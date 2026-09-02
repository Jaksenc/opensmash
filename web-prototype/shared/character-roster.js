export function mergeCharactersBySlug(currentCharacters, loadedCharacters) {
  const merged = [];
  const seenSlugs = new Set();

  for (const character of [...loadedCharacters, ...currentCharacters]) {
    if (!character?.slug || seenSlugs.has(character.slug)) continue;
    seenSlugs.add(character.slug);
    merged.push(character);
  }

  return merged;
}
