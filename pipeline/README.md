# Pipeline scripts

The Python entry points keep their original filenames in this directory. Each
one supports both direct-file execution and package-module execution from the
repository root:

```bash
python3 pipeline/run_character.py "Character Name"
python3 -m pipeline.run_character "Character Name"
```

The main groups are:

- Character generation: `run_character.py`, `expand_character.py`, `gen.py`,
  and `tripo.py`
- Mesh conversion and inspection: `convert_glb.py`, `convert_rigged.py`,
  `auto_skin.py`, `texture_check.py`, and the `render_*.py` tools
- UI generation: `gen_ui_assets.py`, `build_glyph_atlas.py`,
  `emblem_stencil.py`, `pixel_font.py`, and `sprite_codec.py`
- Announcer generation: `generate_announcer.py`, `announcer_voice.py`,
  `dump_fgm_bank.py`, and `render_announcer_refs.py`
- Evaluation support: `run_eval.py`, `make_replay.py`, `frames_from_log.py`,
  `compare_runs.py`, `crop_fighters.py`, and `report.py`

Batch sweep drivers live in `scripts/`. Evaluation experiments and generated
results remain in `eval/`.
