# Website

This directory is the standalone OpenSmash website. It is intentionally kept
separate from the character-generation and BattleShip pipelines.

Run it from the repository root with:

```bash
python3 -m http.server 4173 --directory website
```

The main page is `index.html`. Static models, textures, source UI references,
and brand art live in `assets/`. Older browser-only render experiments live in
`prototypes/`. The procedural stone module is kept beside the page because the
main site imports it directly.
