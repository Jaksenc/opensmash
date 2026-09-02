// Temporary `?trailer=1` capture configuration. Fighter values are roster
// slugs from config/characters.json. Intro fighters fill the injectable
// opening cards in order; Donkey Kong and Yoshi currently remain vanilla.
//
// Match opponents are an ordered pool. A one-player trailer match takes the
// first three fighters that are not the selected fighter. Keep at least four
// entries if you want selecting one of these opponents to stay deterministic.
export default Object.freeze({
  introFighters: Object.freeze([
    "cleopatra",
    "popefrancis",
    "alberteinstein",
    "thestatueofliber",
    "donaldtrump",
    "santaclaus",
  ]),
  // The two fighters Master Hand handles in the opening room, in order:
  // first pulled from the grid, then dropped into the scene.
  introRoomPicks: Object.freeze([
    "donaldtrump",
    "popefrancis",
  ]),
  match: Object.freeze({
    opponents: Object.freeze([
      "keanureeves",
      "arnoldschwarzene",
      "sylvesterstallon",
      "johncena",
    ]),
    stage: "7", // Saffron City; see STAGES in src/launch-options.js.
    cpuLevel: "3",
  }),
});
