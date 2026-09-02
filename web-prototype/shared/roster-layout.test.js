import test from "node:test";
import assert from "node:assert/strict";

import { rosterGridDimensions, rosterReserveHeight } from "./roster-layout.js";

function filteredLayout(visibleCellCount, reservedCellCount, columns) {
  const visible = rosterGridDimensions(visibleCellCount, columns);
  const reserved = rosterGridDimensions(reservedCellCount, columns);
  return { ...visible, reservedHeight: reserved.height };
}

function totalRosterFootprint(layout, renderedWidth) {
  return layout.height * renderedWidth / layout.width
    + rosterReserveHeight(layout, renderedWidth);
}

test("NES and J searches preserve the full roster footprint", () => {
  for (const columns of [3, 6]) {
    const full = filteredLayout(18, 18, columns);
    const nes = filteredLayout(2, 18, columns); // Search + Ness
    const j = filteredLayout(3, 18, columns); // Search + Joey + Jigglypuff
    const expected = totalRosterFootprint(full, 720);

    assert.ok(Math.abs(totalRosterFootprint(nes, 720) - expected) < 1e-9);
    assert.ok(Math.abs(totalRosterFootprint(j, 720) - expected) < 1e-9);
  }
});

test("the reserve grows with asynchronously added fighter cells", () => {
  const stale = filteredLayout(3, 18, 6);
  const current = filteredLayout(3, 19, 6);

  assert.ok(totalRosterFootprint(current, 720) > totalRosterFootprint(stale, 720));
  assert.equal(current.reservedHeight, rosterGridDimensions(19, 6).height);
});
