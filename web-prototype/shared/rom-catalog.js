export const ROM_CATALOG = Object.freeze([
  Object.freeze({
    sha1: "4b71f0e01878696733eefa9c80d11c147ecb4984",
    name: "Nintendo All-Star! Dairantou Smash Brothers (Japan)",
    region: "Japan",
    serial: "NALJ",
    size: 16 * 1024 * 1024,
  }),
  Object.freeze({
    sha1: "a9bf83fe73361e8d042c33ed48b3851d7d46712c",
    name: "Super Smash Bros. (Australia)",
    region: "Australia",
    serial: "NALU",
    size: 16 * 1024 * 1024,
  }),
  Object.freeze({
    sha1: "6ee8a41fef66280ce3e3f0984d00b96079442fb9",
    name: "Super Smash Bros. (Europe) (En,Fr,De)",
    region: "Europe",
    serial: "NALP",
    size: 32 * 1024 * 1024,
  }),
  Object.freeze({
    sha1: "e2929e10fccc0aa84e5776227e798abc07cedabf",
    name: "Super Smash Bros. (USA)",
    region: "USA",
    serial: "NALE",
    size: 16 * 1024 * 1024,
  }),
  Object.freeze({
    sha1: "a0aea7d219443209c6580a501601d3151c58d3ac",
    name: "Super Smash Bros. (USA) (LodgeNet)",
    region: "USA",
    serial: null,
    size: 16 * 1024 * 1024,
  }),
]);

export const ROMS_BY_SHA1 = new Map(ROM_CATALOG.map((rom) => [rom.sha1, rom]));
