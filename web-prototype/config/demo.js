// `?demo=1` live-demo configuration. Picking any fighter from the grid starts
// a deterministic free-for-all against these opponents (first three that are
// not the selected fighter), and pressing T mid-match hands the screen over
// to the looping trailer (pinned in-page, no browser fullscreen). Entries are
// roster slugs, or `{ vanilla: <fkind> }` for an untouched original fighter
// (0 = Mario).
export default Object.freeze({
  match: Object.freeze({
    opponents: Object.freeze([
      "barackobama",
      Object.freeze({ vanilla: 0 }),
      "bobross",
      "chucknorris",
    ]),
    // Per-pick opponent sets (roster slugs / `{ vanilla }`), for the tiles
    // the presenter is likely to click in the second half of the demo.
    // Anyone not listed fights `opponents`.
    opponentsFor: Object.freeze({
      darioamodei: Object.freeze(["roon", "jesuschrist", "kimjongun"]),
      roon: Object.freeze(["darioamodei", "jesuschrist", "kimjongun"]),
      samaltman: Object.freeze(["darioamodei", "elonmusk", "diddy"]),
    }),
    // Body the fighter spawns with (a CHARACTER_MESHES value) for the pick and
    // the opponents; anyone not listed keeps their roster default. Mario is
    // always built; other targets must be in the character's `variants`.
    // Keep every vanilla fighter unique in the match: a second fighter on
    // the same base bumps the vanilla one into an alt costume.
    bases: Object.freeze({
      thomasdimson: "luigi",
      barackobama: "link",
      bobross: "ness",
      roon: "kirby",
      darioamodei: "captain",
    }),
    // Stage ids from STAGES in src/launch-options.js. Default is Dream Land
    // (6), the series' signature stage; picks listed in `stageFor` get their
    // own so the two demo matches never share a backdrop (4 = Hyrule Castle).
    stage: "6",
    stageFor: Object.freeze({
      roon: "4",
      darioamodei: "4",
    }),
    cpuLevel: "3",
  }),
  // Demo-only grid order: these fighters are pulled out of their usual spots
  // and re-inserted, in this order, immediately before `spotlightBefore` so
  // the bottom of the roster is a wall of "what in god's name" next to the
  // presenter's own tile. Unknown slugs are skipped.
  spotlightBefore: "thomasdimson",
  spotlight: Object.freeze([
    "andrejkarpathy",
    "dwaynetherockjoh",
    "elonmusk",
    "borisjohnson",
    "marthastewart",
    "miketyson",
    "krampus",
    "kimjongun",
    "monalisa",
    "morganfreeman",
    "jeffbezos",
    "michaeljordan",
    "humptydumpty",
    "santaclaus",
    "joebiden",
    "diddy",
    "jensenhuang",
    "pikotaro",
    "billnye",
    "cthulhu",
    "gordonramsay",
    "joerogan",
    "loganpaul",
    "willsmith",
    "dannydevito",
    "drphil",
    "markzuckerberg",
    "kyliejenner",
    "ilyasutskever",
    "berniesanders",
    "bettywhite",
    "shaquilleoneal",
    "beyonc",
    "gabenewell",
    "justinbieber",
    "elvispresley",
    "gretathunberg",
    "steveharvey",
    "mrt",
    "roon",
    "jesuschrist",
    "bobross",
    "judgejudy",
    "arnoldschwarzene",
    "tomcruise",
    "hulkhogan",
    "mrbeast",
    "larrydavid",
    "elizabethholmes",
    "ishowspeed",
    "ladygaga",
    "robford",
    "jackblack",
    "jerryspringer",
    "jerryseinfeld",
    "sambankmanfried",
    "postmalone",
    "johncena",
    "guyfieri",
    "saltbae",
    "kevinhart",
    "samaltman",
    "flavorflav",
    "snoopdogg",
    "thegrimreaper",
    "colonelsanders",
    "marilynmonroe",
    "warrenbuffett",
    "martinshkreli",
    "petedavidson",
    "oprahwinfrey",
    "nicolascage",
    "taylorswift",
    "steveballmer",
    "rickygervais",
    "genghiskhan",
    "popefrancis",
    "keanureeves",
    "billgates",
    "steveirwin",
    "darioamodei",
    "chucknorris",
    "barackobama",
  ]),
  // Presenter hotkeys (none of these are engine keys: the game map uses
  // WASD/arrows, J K L I O U, T F G H, Space/Enter and modifiers).
  // P: boot the presenter's match straight into the pinned (pseudo-
  //    fullscreen) shell, so the VS card frames exactly on screen.
  // N: close the game and glide the roster down to `scrollTarget`, ready
  //    for the second pick.
  presenter: "thomasdimson",
  startHotkey: "p",
  scrollHotkey: "n",
  scrollTarget: "roon",
  scrollDurationMs: 2800,
  // N closes the game, which would leave dead air under the glide: bring the
  // home-page music bed up with it (it stops again on the next pick).
  musicOnScroll: true,
  // Every demo pick (click or P) opens in the pinned shell; Esc releases.
  pinOnPlay: true,
  trailerHotkey: "t",
  // Background music (the launch-flow bed) on the home page; stops on play.
  musicHotkey: "m",
});
