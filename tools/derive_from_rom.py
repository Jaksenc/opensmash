#!/usr/bin/env python3
"""Regenerate every game-derived reference file in this repo from the user's
own SSB64 (US) ROM + the BattleShip o2r asset archive, and prove the result
byte-identical to the committed copies.

    tools/derive_from_rom.py --verify                 # table + exit 1 on any diff
    tools/derive_from_rom.py --out /some/dir          # derive into a directory tree
    tools/derive_from_rom.py                          # derive in place (tracked paths)

Everything is produced by the existing extractors (imported, not forked):
  tools/extract_sprites.py               o2r Sprite decoder (portraits, labels)
  pipeline/extract_vanilla_emblems.py    emblem_ref.png
  pipeline/build_glyph_atlas.py          glyph_*/tileglyph_* atlases
  tools/cssfont/locked_icons.py          SearchGlass.png / Plus.png
  stone-tile-investigation/extract_source_tile.py
  pipeline/render_announcer_refs.py      announcer WAVs (ROM)

Targets (all under the repo root):
  assets/css-font/portraits/<Name>.png   12 portraits + FireBg, 45x43 RGBA32,
                                         MNPlayersPortraits llMNPlayersPortraits*Sprite
  assets/css-font/locked/*.png           QuestionMark + four *Shadow (same file),
                                         SearchGlass/Plus synthesized by locked_icons
  web-prototype/visual/assets/ui_refs/
    tile_<f>.png    48x45  the same portrait Sprites in texel-storage layout
                    (width_img=48, the three strips stacked without overlap) --
                    what sprite_codec.decode gives for an engine dump
    name_<f>.png    Wx16   MNPlayersCommon ll*TextSprite (IA8), storage layout
    stockicon_ref.png      Mario's 8x10 CI4 stock icon (MarioModel
                    llMarioModelStockSprite) nearest-scaled 32x on a 320x320 canvas
    emblem_ref.png, glyph_*.png, tileglyph_*.png, glyph_backup/glyph_{66,67,68,75}.png
  stone-tile-investigation/source-stone-tile{,-8x,-4up}.png + source-analysis.json
  eval/announcer_conditioning_corrected/** (ROM)

Engine-run derivations (skels/*.skel, skels/parts/*.json, and the four
glyph_{66,67,68,75}.png sliced from the engine's own css_name sprite dumps)
live in tools/derive_skeletons.py; pass --skeletons here to run both, or call
it directly. Together the two scripts regenerate every game-derived file in
the repo except skels/reference/mario.skel (captured at an older spawn point;
see derive_skeletons.py).
"""
import argparse
import contextlib
import filecmp
import os
import shutil
import sys
import tempfile
import hashlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BATTLESHIP = os.path.join(os.path.dirname(ROOT), "BattleShip")
DEFAULT_ROM = os.path.join(BATTLESHIP, "baserom.us.z64")
DEFAULT_O2R = next((p for p in (os.path.join(BATTLESHIP, b, "BattleShip.o2r")
                                for b in ("build-us", "build-wasm")) if os.path.exists(p)),
                   os.path.join(BATTLESHIP, "build-us", "BattleShip.o2r"))
ROM_SHA1 = "e2929e10fccc0aa84e5776227e798abc07cedabf"

for p in (HERE, os.path.join(HERE, "cssfont"), os.path.join(ROOT, "pipeline"),
          os.path.join(ROOT, "stone-tile-investigation")):
    sys.path.insert(0, p)

import extract_sprites as es                      # noqa: E402
import build_glyph_atlas as glyph_atlas           # noqa: E402
import extract_vanilla_emblems as emblems         # noqa: E402
import extract_source_tile as stone_tile          # noqa: E402
import locked_icons                               # noqa: E402
import render_announcer_refs as announcer         # noqa: E402

PORTRAITS = "assets/css-font/portraits"
LOCKED = "assets/css-font/locked"
UI_REFS = "web-prototype/visual/assets/ui_refs"
STONE = "stone-tile-investigation"
ANNOUNCER = "eval/announcer_conditioning_corrected"

# ll*Sprite offsets from BattleShip/include/reloc_data.us.h
PORTRAIT_SPRITES = {  # reloc_menus/MNPlayersPortraits, portrait name -> ui_refs fighter key
    "Mario": (0x4728, "mario"), "Luigi": (0x6978, "luigi"), "Donkey": (0x8bc8, "dk"),
    "Samus": (0xae18, "samus"), "Fox": (0xd068, "fox"), "Kirby": (0xf2b8, "kirby"),
    "Link": (0x11508, "link"), "Yoshi": (0x13758, "yoshi"), "Pikachu": (0x159a8, "pikachu"),
    "Ness": (0x17bf8, "ness"), "Captain": (0x19e48, "captain"), "Purin": (0x1c098, "purin"),
}
PORTRAIT_EXTRA = {"FireBg": 0x24D0}
LOCKED_SPRITES = {"QuestionMark": 0xF68, "CaptainShadow": 0x1e2e8, "LuigiShadow": 0x20538,
                  "NessShadow": 0x22788, "PurinShadow": 0x249d8}
NAME_SPRITES = {  # reloc_menus/MNPlayersCommon ll MNPlayersCommon<X>TextSprite
    "mario": 0x1838, "luigi": 0x1b18, "dk": 0x1ff8, "samus": 0x2358, "fox": 0x25b8,
    "kirby": 0x28e8, "link": 0x2ba0, "yoshi": 0x2ed8, "pikachu": 0x32f8, "ness": 0x35b0,
    "captain": 0x3998, "purin": 0x3db8,
}
STOCK_SPRITE = ("reloc_fighters_main/MarioModel", 0x72d0)  # llMarioModelStockSprite
BACKUP_GLYPHS = ("glyph_66.png", "glyph_67.png", "glyph_68.png", "glyph_75.png")

MANUAL = {
    f"{UI_REFS}/glyph_66.png": "hand re-sliced B from in-engine dump (0d6a8d90); atlas output is glyph_backup/",
    f"{UI_REFS}/glyph_67.png": "hand re-sliced C from in-engine dump (0d6a8d90); atlas output is glyph_backup/",
    f"{UI_REFS}/glyph_68.png": "hand re-sliced D from in-engine dump (0d6a8d90); atlas output is glyph_backup/",
    f"{UI_REFS}/glyph_75.png": "hand re-sliced K from in-engine dump (0d6a8d90); atlas output is glyph_backup/",
}


def tracked_targets():
    """Relative paths of every file this script accounts for (derived + manual)."""
    out = [f"{PORTRAITS}/{n}.png" for n in list(PORTRAIT_SPRITES) + list(PORTRAIT_EXTRA)]
    out += [f"{LOCKED}/{n}.png" for n in list(LOCKED_SPRITES) + ["SearchGlass", "Plus"]]
    keys = [k for _, k in PORTRAIT_SPRITES.values()]
    out += [f"{UI_REFS}/tile_{k}.png" for k in keys] + [f"{UI_REFS}/name_{k}.png" for k in keys]
    out += [f"{UI_REFS}/stockicon_ref.png", f"{UI_REFS}/emblem_ref.png"]
    bold = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    out += [f"{UI_REFS}/glyph_{ord(c)}.png" for c in bold]
    out += [f"{UI_REFS}/tileglyph_{ord(c)}.png" for c in "." + bold]
    out += [f"{UI_REFS}/glyph_backup/{b}" for b in BACKUP_GLYPHS]
    out += [f"{STONE}/{n}" for n in ("source-stone-tile.png", "source-stone-tile-8x.png",
                                     "source-stone-tile-4up.png", "source-analysis.json")]
    out += [f"{ANNOUNCER}/individual/{slug}.wav"
            for slug, _, _ in announcer.NAME_LINES + announcer.PHRASE_LINES]
    out += [f"{ANNOUNCER}/{n}" for n in ("conditioning_identity.wav", "conditioning_style.wav",
                                         "manifest.json")]
    return out


def derive(out, rom, o2r, log=print):
    """Write every derivable target under `out`. Returns {relpath: note} for
    targets that could NOT be produced (missing source / manual)."""
    skipped = dict(MANUAL)
    mk = lambda rel: (os.makedirs(os.path.join(out, os.path.dirname(rel)), exist_ok=True),
                      os.path.join(out, rel))[1]

    if not os.path.exists(o2r):
        log(f"!! o2r not found: {o2r}")
        for rel in tracked_targets():
            if not rel.startswith(ANNOUNCER) and rel not in skipped:
                skipped[rel] = f"MISSING-SOURCE {o2r}"
    else:
        # --- CSS portraits + locked placeholders (reloc_menus/MNPlayersPortraits)
        por = es.load_reloc("reloc_menus/MNPlayersPortraits", o2r)
        for name, (off, key) in PORTRAIT_SPRITES.items():
            es.decode_sprite(por, off, name).save(mk(f"{PORTRAITS}/{name}.png"))
            es.decode_sprite(por, off, name, storage=True).save(mk(f"{UI_REFS}/tile_{key}.png"))
        for name, off in PORTRAIT_EXTRA.items():
            es.decode_sprite(por, off, name).save(mk(f"{PORTRAITS}/{name}.png"))
        for name, off in LOCKED_SPRITES.items():
            es.decode_sprite(por, off, name).save(mk(f"{LOCKED}/{name}.png"))
        with tempfile.TemporaryDirectory() as tmp:  # preview sheet is not a tracked file
            locked_icons.main(out=os.path.join(out, LOCKED),
                              preview=os.path.join(tmp, "preview.png"),
                              portraits=os.path.join(out, PORTRAITS))
        log(f"portraits/locked: {len(PORTRAIT_SPRITES) + len(PORTRAIT_EXTRA) + len(LOCKED_SPRITES) + 2} files")

        # --- CSS panel names (reloc_menus/MNPlayersCommon, IA8, storage layout)
        common = es.load_reloc("reloc_menus/MNPlayersCommon", o2r)
        for key, off in NAME_SPRITES.items():
            es.decode_sprite(common, off, key, storage=True).save(mk(f"{UI_REFS}/name_{key}.png"))

        # --- Mario stock icon, 32x nearest on a 320 square
        from PIL import Image
        model = es.load_reloc(STOCK_SPRITE[0], o2r)
        icon = es.decode_sprite(model, STOCK_SPRITE[1], "stock")
        sheet = Image.new("RGBA", (320, 320), (0, 0, 0, 0))
        sheet.paste(icon.resize((icon.width * 32, icon.height * 32), Image.NEAREST), (0, 0))
        sheet.save(mk(f"{UI_REFS}/stockicon_ref.png"))

        # --- emblems + glyph atlases (atlas reads the dumps just written)
        emblems.main(["--o2r", o2r, "--out", mk(f"{UI_REFS}/emblem_ref.png")])
        refs = os.path.join(out, UI_REFS)
        with tempfile.TemporaryDirectory() as tmp:
            glyph_atlas.main(refs=refs, out=tmp)
            for f in sorted(os.listdir(tmp)):
                rel = f"{UI_REFS}/{f}"
                if rel in MANUAL:   # keep the hand-fixed letters; atlas copy -> backup
                    shutil.copy(os.path.join(tmp, f), mk(f"{UI_REFS}/glyph_backup/{f}"))
                else:
                    shutil.copy(os.path.join(tmp, f), mk(rel))
        log("ui_refs: tiles, names, stock, emblems, glyph atlases")

        # --- stone tile investigation
        stone_tile.main(o2r, os.path.join(out, STONE))

    if not os.path.exists(rom):
        log(f"!! ROM not found: {rom}")
        for rel in tracked_targets():
            if rel.startswith(ANNOUNCER):
                skipped[rel] = f"MISSING-SOURCE {rom}"
    else:
        with open(rom, "rb") as f:
            sha = hashlib.sha1(f.read()).hexdigest()
        if sha != ROM_SHA1:
            log(f"!! ROM sha1 {sha} != expected US ROM {ROM_SHA1}; announcer output may differ")
        announcer.main([os.path.join(out, ANNOUNCER), "--rom", rom])
    return skipped


def compare(rel, derived, committed):
    """-> (status, reason)"""
    if not os.path.exists(committed):
        return "NO-COMMITTED-COPY", "not present in the repo"
    if not os.path.exists(derived):
        return "NOT-DERIVED", "script produced no file"
    if filecmp.cmp(derived, committed, shallow=False):
        return "IDENTICAL", ""
    if rel.endswith(".png"):
        from PIL import Image
        import numpy as np
        a, b = Image.open(derived), Image.open(committed)
        if a.size != b.size:
            return "DIFFERS", f"size {a.size} vs committed {b.size}"
        if a.mode != b.mode:
            return "DIFFERS", f"mode {a.mode} vs committed {b.mode}"
        n = int((np.array(a) != np.array(b)).any(-1).sum()) if a.mode != "1" else -1
        if n == 0:
            return "PIXEL-IDENTICAL", "same pixels, different PNG encoding"
        return "DIFFERS", f"{n} px differ"
    if rel.endswith(".json"):
        import json
        try:
            da, db = json.load(open(derived)), json.load(open(committed))
        except Exception as e:  # noqa: BLE001
            return "DIFFERS", f"unparseable json ({e})"
        if isinstance(da, dict) and isinstance(db, dict):
            keys = [k for k in set(da) | set(db) if da.get(k) != db.get(k)]
            if keys == ["source_archive"]:  # provenance label only, not game data
                return "IDENTICAL", "(source_archive label ignored)"
            return "DIFFERS", "fields differ: " + ", ".join(sorted(keys))
        return "DIFFERS", "content differs"
    sa, sb = os.path.getsize(derived), os.path.getsize(committed)
    return "DIFFERS", f"size {sa} vs {sb}" if sa != sb else "same size, bytes differ"


def verify(rom, o2r):
    with tempfile.TemporaryDirectory(prefix="derive_verify_") as tmp:
        with open(os.devnull, "w") as null, contextlib.redirect_stdout(null):
            skipped = derive(tmp, rom, o2r, log=lambda *a: None)
        rows = []
        for rel in tracked_targets():
            if rel in skipped:
                note = skipped[rel]
                status = "MISSING-SOURCE" if note.startswith("MISSING-SOURCE") else "MANUAL"
                rows.append((rel, status, note.replace("MISSING-SOURCE ", "")))
                continue
            rows.append((rel,) + compare(rel, os.path.join(tmp, rel), os.path.join(ROOT, rel)))
    width = max(len(r[0]) for r in rows)
    for rel, status, reason in rows:
        print(f"{rel:<{width}}  {status:<16} {reason}")
    counts = {}
    for _, status, _ in rows:
        counts[status] = counts.get(status, 0) + 1
    print("\n" + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    bad = [r for r in rows if r[1] in ("DIFFERS", "NOT-DERIVED", "MISSING-SOURCE")]
    return 1 if bad else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rom", default=DEFAULT_ROM)
    ap.add_argument("--o2r", default=DEFAULT_O2R)
    ap.add_argument("--out", default=ROOT,
                    help="root to write the tracked paths under (default: in place)")
    ap.add_argument("--verify", action="store_true",
                    help="derive into a temp dir and compare against the committed files")
    ap.add_argument("--skeletons", action="store_true",
                    help="also run tools/derive_skeletons.py --glyphs (boots the native engine "
                         "13 times) for skels/ and the four engine-sliced glyphs")
    ap.add_argument("--build-dir", default=os.path.join(BATTLESHIP, "build-us"),
                    help="native BattleShip build used by --skeletons")
    a = ap.parse_args(argv)
    if a.verify:
        rc = verify(a.rom, a.o2r)
    else:
        rc = 0
        skipped = derive(a.out, a.rom, a.o2r)
        for rel, note in sorted(skipped.items()):
            print(f"skipped {rel}: {note}")
    if a.skeletons:
        import subprocess
        cmd = [sys.executable, os.path.join(HERE, "derive_skeletons.py"), "--glyphs",
               "--build-dir", a.build_dir]
        cmd += ["--verify"] if a.verify else ["--out", a.out]
        print("\n==> " + " ".join(cmd), flush=True)
        rc = max(rc, subprocess.call(cmd))
    return rc


if __name__ == "__main__":
    sys.exit(main())
