# Procedural stone tile pipeline

This pipeline generates new `64 × 32` pixel-art stone tiles in the visual
language of the extracted Smash 64 character-select background. It does not
copy source pixels.

The generator synthesizes its height fields directly on a torus using broad
periodic Fourier forms plus a small set of chunky wrapped chisel cuts. Fine
noise is deliberately restrained. Directional relief lighting, palette
quantization, and every candidate-selection metric are wrap-aware: a cut or
ledge crossing one edge continues from the opposite edge.

## Run

```sh
python3 website/stone-tile-pipeline/generate_stone_tile.py \
  --seed 64 \
  --candidates 128 \
  --name procedural-stone
```

For interactive seed exploration, open `playground.html` through the local
site server. It generates and ranks 96 periodic candidates in the browser,
shows one native tile and a zoomable tiled wall, and exports PNG or SVG.

The same arguments always produce byte-identical output. Change `--seed` for a
new family of candidates. Increase `--candidates` when you want the automatic
style ranker to search harder.

## Outputs

- `procedural-stone.png` — native paletted `64 × 32` tile
- `procedural-stone.svg` — equivalent integer-run SVG
- `procedural-stone-8x.png` — nearest-neighbor inspection preview
- `procedural-stone-4up.png` — exact `2 × 2` repeat at 8× scale
- `procedural-stone-style-comparison.png` — source style beside generation
- `procedural-stone-report.json` — palette, structure, style, and seam metrics

The report's seam test compares each wrap transition against the distribution
of transitions inside the tile. It also verifies all four quadrants of the
`2 × 2` repeat are byte-identical to the native tile.

## Verify

```sh
python3 website/stone-tile-pipeline/test_pipeline.py
```
