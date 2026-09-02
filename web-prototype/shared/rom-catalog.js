// ROMs the site accepts. Acceptance is not just "is this a real Smash 64
// dump": the browser must also be able to BUILD the engine's assets from it
// (BattleShip/docs/web_rom_extraction.md) and the engine must be compiled for
// that region. Today both hold only for the US v1.0 image:
//   - Torch's config.yml carries US and JP recipes, but the web package ships
//     yamls/us only and the engine wasm is region-compiled for US.
//   - Europe (NALP), Australia (NALU) and the US LodgeNet variant have no
//     Torch recipe at all; extraction would report "unsupported ROM".
// Adding a region means: a Torch recipe for its hash, packaging its yamls,
// and an engine build for that region — then add its entry here.
export const ROM_CATALOG = Object.freeze([
  Object.freeze({
    sha1: "e2929e10fccc0aa84e5776227e798abc07cedabf",
    name: "Super Smash Bros. (USA)",
    region: "USA",
    serial: "NALE",
    size: 16 * 1024 * 1024,
  }),
]);

// Known dumps we recognise but cannot run, so the rejection can say why
// instead of "not a supported ROM".
export const UNSUPPORTED_ROMS = Object.freeze([
  Object.freeze({
    sha1: "4b71f0e01878696733eefa9c80d11c147ecb4984",
    name: "Nintendo All-Star! Dairantou Smash Brothers (Japan)",
    region: "Japan",
    size: 16 * 1024 * 1024,
  }),
  Object.freeze({
    sha1: "a9bf83fe73361e8d042c33ed48b3851d7d46712c",
    name: "Super Smash Bros. (Australia)",
    region: "Australia",
    size: 16 * 1024 * 1024,
  }),
  Object.freeze({
    sha1: "6ee8a41fef66280ce3e3f0984d00b96079442fb9",
    name: "Super Smash Bros. (Europe) (En,Fr,De)",
    region: "Europe",
    size: 32 * 1024 * 1024,
  }),
  Object.freeze({
    sha1: "a0aea7d219443209c6580a501601d3151c58d3ac",
    name: "Super Smash Bros. (USA) (LodgeNet)",
    region: "USA (LodgeNet)",
    size: 16 * 1024 * 1024,
  }),
]);

export const ROMS_BY_SHA1 = new Map(ROM_CATALOG.map((rom) => [rom.sha1, rom]));
export const UNSUPPORTED_ROMS_BY_SHA1 = new Map(UNSUPPORTED_ROMS.map((rom) => [rom.sha1, rom]));
