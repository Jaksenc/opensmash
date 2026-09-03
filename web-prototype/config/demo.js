// `?demo=1` live-demo configuration. Picking any fighter from the grid starts
// a deterministic free-for-all against these opponents (first three that are
// not the selected fighter), and pressing T mid-match hands the screen over
// to the looping trailer in fullscreen. Entries are roster slugs, or
// `{ vanilla: <fkind> }` for an untouched original fighter (0 = Mario).
export default Object.freeze({
  match: Object.freeze({
    opponents: Object.freeze([
      "barackobama",
      Object.freeze({ vanilla: 0 }),
      "bobross",
      "chucknorris",
    ]),
    stage: "7", // Saffron City; see STAGES in src/launch-options.js.
    cpuLevel: "3",
  }),
  trailerHotkey: "t",
  // Background music (the launch-flow bed) on the home page; stops on play.
  musicHotkey: "m",
});
