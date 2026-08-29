# Smash Weights

## Retro cartridge

`assets/n64-cartridge-tripo.glb` is a Tripo P1 multiview model generated from
front, side, and back references. It is used by the floating lower-right
control in `index.html` and rendered inside
the same low-resolution Three.js post-process as the glove, including the
posterized palette, dithered alpha edge, and dark one-texel outline.

The original procedural fallback can be rebuilt with:

```bash
blender --background --python tools/build_cartridge_model.py
```

## Mesh generation

Meshy and Tripo are configured through the git-ignored `.env` file. The mesh
generator is dependency-free and uses Python 3's standard library.

Validate both API connections without spending generation credits:

```bash
python3 tools/generate_mesh.py check
```

Generate an untextured GLB (the cheaper geometry-only path):

```bash
python3 tools/generate_mesh.py generate \
  --provider meshy \
  --prompt "a low-poly fighting-game arena platform"
```

```bash
python3 tools/generate_mesh.py generate \
  --provider tripo \
  --prompt "a low-poly fighting-game arena platform"
```

Generate from ordered front, left, back, and right reference images with
Tripo's multiview model:

```bash
python3 tools/generate_mesh.py generate-multiview \
  --front front.png \
  --left left.png \
  --back back.png \
  --right right.png \
  --target-polycount 8000 \
  --name referenced-model.glb
```

Add `--textured` for textures and PBR maps. Meshy accepts optional texture
guidance with `--texture-prompt`; either provider accepts `--target-polycount`.
For example:

```bash
python3 tools/generate_mesh.py generate \
  --provider meshy \
  --prompt "a chunky red arcade joystick, centered, no background" \
  --textured \
  --texture-prompt "red enamel, brushed steel base, subtle wear" \
  --target-polycount 12000
```

Finished models are downloaded to `assets/generated/` by default. This folder
is git-ignored because generated GLBs can be large. Use `--output-dir` or
`--name` to change the destination. Run the CLI with `--help` for all options.

Generation consumes provider credits. `--textured` may consume additional
credits, and Meshy's textured flow runs a preview task followed by a refine task.
