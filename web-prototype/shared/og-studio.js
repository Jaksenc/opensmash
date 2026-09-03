export const OG_IMAGE_WIDTH = 1200;
export const OG_IMAGE_HEIGHT = 630;
export const OG_MIN_ZOOM = .45;
export const OG_MAX_ZOOM = 2.5;

export const OG_FIGHTER_BODIES = Object.freeze([
  { value: "mario", label: "Mario", fkind: 0 },
  { value: "fox", label: "Fox", fkind: 1 },
  { value: "donkey", label: "Donkey Kong", fkind: 2 },
  { value: "samus", label: "Samus", fkind: 3 },
  { value: "luigi", label: "Luigi", fkind: 4 },
  { value: "link", label: "Link", fkind: 5 },
  { value: "yoshi", label: "Yoshi", fkind: 6 },
  { value: "captain", label: "Captain Falcon", fkind: 7 },
  { value: "kirby", label: "Kirby", fkind: 8 },
  { value: "pikachu", label: "Pikachu", fkind: 9 },
  { value: "purin", label: "Jigglypuff", fkind: 10 },
  { value: "ness", label: "Ness", fkind: 11 },
]);

// Back-to-front paint order. The fighters are deliberately staggered like a
// team photo instead of sitting on a regular character-select grid.
export const OG_ROSTER_SLOTS = Object.freeze([
  { id: "back-left", label: "Back 1", x: 50, y: 58, width: 270, height: 360, zoom: .96 },
  { id: "back-left-center", label: "Back 2", x: 325, y: 45, width: 270, height: 360, zoom: .98 },
  { id: "back-right-center", label: "Back 3", x: 605, y: 45, width: 270, height: 360, zoom: .98 },
  { id: "back-right", label: "Back 4", x: 880, y: 58, width: 270, height: 360, zoom: .96 },
  { id: "middle-left", label: "Middle 1", x: -40, y: 122, width: 300, height: 400, zoom: 1.01 },
  { id: "middle-left-center", label: "Middle 2", x: 240, y: 103, width: 300, height: 400, zoom: 1.03 },
  { id: "middle-right-center", label: "Middle 3", x: 660, y: 103, width: 300, height: 400, zoom: 1.03 },
  { id: "middle-right", label: "Middle 4", x: 940, y: 122, width: 300, height: 400, zoom: 1.01 },
  { id: "front-left", label: "Front 1", x: 182, y: 155, width: 335, height: 450, zoom: 1.06 },
  { id: "front-center", label: "Front center", x: 432, y: 140, width: 335, height: 450, zoom: 1.09 },
  { id: "front-right", label: "Front 3", x: 682, y: 155, width: 335, height: 450, zoom: 1.06 },
]);

export function shuffledRoster(characters, count, random = Math.random) {
  const pool = Array.isArray(characters) ? [...characters] : [];
  for (let index = pool.length - 1; index > 0; index -= 1) {
    const swapIndex = Math.floor(random() * (index + 1));
    [pool[index], pool[swapIndex]] = [pool[swapIndex], pool[index]];
  }
  return pool.slice(0, Math.max(0, Math.floor(Number(count) || 0)));
}

export function availableBodyModels(character) {
  if (!character) return [];
  const available = new Set(["mario", character.base, ...(character.variants || [])]);
  return OG_FIGHTER_BODIES.filter(({ value }) => available.has(value));
}

export function fighterFrame(slot, placement, sourceWidth = 480, sourceHeight = 640) {
  const zoom = Number.isFinite(placement?.zoom) ? placement.zoom : slot.zoom;
  const width = slot.height * sourceWidth / sourceHeight * zoom;
  const height = slot.height * zoom;
  return {
    x: slot.x + (slot.width - width) / 2 + (placement?.offsetX || 0) * slot.width * .16,
    y: slot.y + (slot.height - height) / 2 + (placement?.offsetY || 0) * slot.height * .1,
    width,
    height,
  };
}

export function fighterSlotAtPoint(x, y, placements, slots = OG_ROSTER_SLOTS) {
  for (let index = Math.min(slots.length, placements.length) - 1; index >= 0; index -= 1) {
    if (!placements[index]?.slug) continue; // empty position: nothing to grab
    const frame = fighterFrame(slots[index], placements[index]);
    if (x >= frame.x && x <= frame.x + frame.width && y >= frame.y && y <= frame.y + frame.height) {
      return index;
    }
  }
  return -1;
}

export function resizeHandleAtPoint(x, y, slot, placement, radius = 18) {
  const frame = fighterFrame(slot, placement);
  const handles = {
    nw: [frame.x, frame.y],
    ne: [frame.x + frame.width, frame.y],
    se: [frame.x + frame.width, frame.y + frame.height],
    sw: [frame.x, frame.y + frame.height],
  };
  for (const [name, [handleX, handleY]] of Object.entries(handles)) {
    if (Math.abs(x - handleX) <= radius && Math.abs(y - handleY) <= radius) return name;
  }
  return null;
}

export function rosterSlotAtPoint(x, y, slots = OG_ROSTER_SLOTS) {
  for (let index = slots.length - 1; index >= 0; index -= 1) {
    const slot = slots[index];
    if (
      x >= slot.x && x <= slot.x + slot.width &&
      y >= slot.y && y <= slot.y + slot.height
    ) return index;
  }
  return -1;
}
