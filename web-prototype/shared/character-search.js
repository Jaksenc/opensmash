export function normalizeSearchText(value) {
  return String(value || "")
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

function allowedTypos(term) {
  if (term.length < 4) return 0;
  return term.length < 8 ? 1 : 2;
}

// Optimal-string-alignment distance: Levenshtein edits plus one adjacent
// transposition, which covers common name-search mistakes such as "maroi".
function editDistance(left, right) {
  const rows = Array.from(
    { length: left.length + 1 },
    () => new Array(right.length + 1).fill(0),
  );

  for (let row = 0; row <= left.length; row += 1) rows[row][0] = row;
  for (let column = 0; column <= right.length; column += 1) rows[0][column] = column;

  for (let row = 1; row <= left.length; row += 1) {
    for (let column = 1; column <= right.length; column += 1) {
      const substitutionCost = left[row - 1] === right[column - 1] ? 0 : 1;
      rows[row][column] = Math.min(
        rows[row - 1][column] + 1,
        rows[row][column - 1] + 1,
        rows[row - 1][column - 1] + substitutionCost,
      );

      if (
        row > 1
        && column > 1
        && left[row - 1] === right[column - 2]
        && left[row - 2] === right[column - 1]
      ) {
        rows[row][column] = Math.min(rows[row][column], rows[row - 2][column - 2] + 1);
      }
    }
  }

  return rows[left.length][right.length];
}

function fuzzyTermMatch(term, candidates) {
  const maxDistance = allowedTypos(term);
  if (!maxDistance) return false;

  return candidates.some((candidate) => (
    Math.abs(candidate.length - term.length) <= maxDistance
    && editDistance(term, candidate) <= maxDistance
  ));
}

export function matchesCharacterSearch(character, query) {
  const terms = normalizeSearchText(query).split(/\s+/).filter(Boolean);
  if (!terms.length) return true;
  const fields = [
    character.name,
    character.display,
    character.short,
    character.slug,
  ].filter(Boolean).map(normalizeSearchText).filter(Boolean);
  const haystack = fields.join(" ");
  const fuzzyCandidates = [...new Set(fields.flatMap((field) => [
    ...field.split(/\s+/),
    field.replace(/\s+/g, ""),
  ]))];

  return terms.every((term) => (
    haystack.includes(term) || fuzzyTermMatch(term, fuzzyCandidates)
  ));
}
