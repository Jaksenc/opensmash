#!/usr/bin/env python3
"""Regenerate skels/ skeleton + vanilla part dumps by running the engine.

For each fighter kind the native BattleShip build is launched with
SSB64_DUMP_SKELETON=<fkind> (hook: BattleShip/decomp/src/ft/ftport.c
port_dump_skeleton, fired from ftManagerMakeFighter). Its ssb64.log is then
split into the committed artefacts:

  skels/fk<N>-all.log / skels/donkey-all.log   first dump only: SKELDUMP/MESHV/MESHDUMP lines
  skels/<name>.skel                            SKELDUMP/SKELDUMP2 lines only
  skels/parts/vanilla-<name>-parts.json        {raw_joint: [[x,y,z],...]} from
                                               MESHV lines (mario, link)
  skels/parts/vanilla-<name>-parts.canonical.json
        same vertices re-keyed from the target's raw joint id to the
        canonical (Mario) joint id via the inverse of skels/<name>.profile.json
        "map" (canonical -> target); joints the map does not name are
        dropped, raw log order is kept (10 non-mario/link targets)

JSON is written with json.dumps defaults (", " / ": " separators, no indent,
no trailing newline) — that is the committed formatting.

Mario is special: skels/mario-frames.skel is exactly the SKELDUMP2 lines of
the mario dump; skels/reference/mario.skel is the SKELDUMP (v1) lines only,
but the committed copy was captured before SSB64_BOOT_BATTLE existed, at a
different spawn (root (-3,510,0) instead of (-2400,1022,0)) — every joint's
world position differs by exactly that root offset, locals/hierarchy are
identical. It cannot be reproduced byte-for-byte with the current boot.
skels/link-parts.log is the MESHV/MESHDUMP lines only (no SKELDUMP lines).

Not derived here (hand-authored): skels/*.profile.json, skels/VALIDATION.md,
skels/print_tree.py.

dl= pointers: the engine prints each joint's display-list pointer with %p
(ftport.c port_dump_skeleton), i.e. an ASLR'd host heap address that changes
every launch (0x63bd2b308 one run, 0xcff92b308 the next). The loaded asset
block is mapped at a 4 MiB-aligned base (every observed run-to-run slide is
a multiple of 0x400000, across 11 fighters x 3 runs), so the low 22 bits are
the stable offset inside the block; bits 22-31 are NOT stable, a 32-bit mask
does not work. The only consumer, pipeline/convert_glb.py load_skeleton,
uses dl solely as a boolean (!= "0x0"). This script therefore writes dl
normalized to pointer & 0x3fffff (dl=0x2b308; dl=0x0 stays) so output is
deterministic, and --verify applies the same normalization to the committed
side before comparing.

--glyphs: additionally boots into the VS character-select screen
(SSB64_START_SCENE=16) with SSB64_DUMP_SPRITES=<dir>, decodes the
css_name_fk<N> IA8 name sprites with pipeline/sprite_codec.py and re-slices
the four hand-cut glyphs of commit 0d6a8d90 (B, C, D, K) into
<out>/web-prototype/visual/assets/ui_refs/glyph_{66,67,68,75}.png.
Needs Pillow (via sprite_codec).

--verify derives into a temp dir and compares byte-for-byte against the
committed files, printing a per-file table; exit 1 on any difference.
Numeric drift in .skel lines is reported per joint.

stdlib only for the skeleton part (numpy optional, unused).
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SKELS = os.path.join(ROOT, "skels")
LOG = os.path.expanduser("~/Library/Application Support/BattleShip/ssb64.log")

FIGHTERS = ["mario", "fox", "donkey", "samus", "luigi", "link",
            "yoshi", "captain", "kirby", "pikachu", "purin", "ness"]

# committed raw-log names are not uniform
RAW_LOG_NAME = {"donkey": "donkey-all.log", "link": "link-parts.log"}
# which fighters have a raw (non-canonical) parts json committed
RAW_PARTS = {"mario", "link"}
# which fighters have a .skel under skels/ (mario's lives in reference/)
# skels/reference/mario.skel is a legacy capture (pre-SKELDUMP2 hook, different
# spawn point) still read by pipeline/texture_check.py. It cannot be reproduced
# and is never written here; mario gets the same mario.skel layout as every
# other fighter plus mario-frames.skel (its SKELDUMP2 lines).
LEGACY_UNDERIVABLE = {os.path.join("reference", "mario.skel"):
                      "legacy capture at a different spawn point; kept as committed"}
# raw logs that were committed without their SKELDUMP lines
MESH_ONLY_LOG = {"link"}

MESHV_RE = re.compile(rb"MESHV: j=(\d+) x=(-?\d+) y=(-?\d+) z=(-?\d+)")
DL_RE = re.compile(rb" dl=0x([0-9a-fA-F]+)")


DL_MASK = 0x3fffff  # 4 MiB-aligned mapping base -> low 22 bits are stable


def normalize_dl(data):
    """' dl=0x63bd2b308' -> ' dl=0x2b308' (pointer & DL_MASK); dl=0x0 kept.
    The engine prints a %p host pointer; only the offset inside the 4 MiB-
    aligned asset mapping survives ASLR (see module docstring)."""
    return DL_RE.sub(lambda m: b" dl=0x%x" % (int(m.group(1), 16) & DL_MASK), data)


# ---------------------------------------------------------------- parsing
def first_dump(raw_bytes):
    """Reduce a full ssb64.log to the committed '-all.log' form: only the
    SKELDUMP/MESHV/MESHDUMP lines of the FIRST dump. The boot is <fk> vs
    <fk>, so ftManagerMakeFighter fires the hook once per player; the
    committed logs keep player 1 only (player 2 spawns mirrored, different
    world positions). MESHWALK lines (host pointers) are dropped."""
    out = []
    begins = 0
    # mesh-only logs (committed link-parts.log) have no begin marker
    has_begin = b"SKELDUMP: begin" in raw_bytes
    for line in raw_bytes.splitlines(keepends=True):
        if line.startswith(b"SKELDUMP: begin"):
            begins += 1
            if begins > 1:
                break
        if (begins or not has_begin) and \
                line.startswith((b"SKELDUMP", b"MESHV:", b"MESHDUMP:")):
            out.append(line)
    return b"".join(out)


def split_log(dump_bytes):
    """-> (skel_bytes, {raw_joint_str: [[x,y,z],...]}) from a first_dump() log."""
    skel = []
    parts = {}
    for line in dump_bytes.splitlines(keepends=True):
        if line.startswith(b"SKELDUMP"):
            skel.append(line)
            continue
        m = MESHV_RE.match(line)
        if m:
            parts.setdefault(m.group(1).decode(), []).append(
                [int(m.group(2)), int(m.group(3)), int(m.group(4))])
    return b"".join(skel), parts


def canonicalize(parts, profile_path):
    """Re-key target joint ids -> canonical ids via inverse of profile map.

    A canonical id may map onto the same target joint twice (samus 15/16
    -> 16); the first canonical id listed wins, matching the committed
    files."""
    prof = json.load(open(profile_path))
    inv = {}
    for canon, target in prof["map"].items():
        inv.setdefault(str(target), canon)
    return {inv[j]: v for j, v in parts.items() if j in inv}


def dumps(obj):
    return json.dumps(obj).encode()


def outputs_for(name, out_dir, raw_bytes):
    """Write every artefact for one fighter; -> {relpath: bytes}."""
    fk = FIGHTERS.index(name)
    raw_bytes = normalize_dl(first_dump(raw_bytes))
    skel_bytes, parts = split_log(raw_bytes)
    files = {}
    log_bytes = raw_bytes
    if name in MESH_ONLY_LOG:
        log_bytes = b"".join(l for l in raw_bytes.splitlines(keepends=True)
                             if not l.startswith(b"SKELDUMP"))
    files[RAW_LOG_NAME.get(name, f"fk{fk}-all.log")] = log_bytes
    if not skel_bytes:
        pass  # mesh-only source log: no .skel can be produced
    else:
        files[f"{name}.skel"] = skel_bytes
        if name == "mario":
            lines = skel_bytes.splitlines(keepends=True)
            files["mario-frames.skel"] = b"".join(l for l in lines if l.startswith(b"SKELDUMP2:"))
    if name in RAW_PARTS:
        files[os.path.join("parts", f"vanilla-{name}-parts.json")] = dumps(parts)
    prof = os.path.join(SKELS, f"{name}.profile.json")
    if name != "mario" and os.path.exists(prof):
        files[os.path.join("parts", f"vanilla-{name}-parts.canonical.json")] = \
            dumps(canonicalize(parts, prof))
    # out_dir mirrors the repo root, so in-place regeneration is --out <repo>.
    for rel, data in files.items():
        p = os.path.join(out_dir, "skels", rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(data)
    return files


# ---------------------------------------------------------------- engine
def pin_window(build):
    """Same as run_eval.py: pin window size/position (cfg file is untracked)."""
    cfg_path = os.path.join(build, "BattleShip.cfg.json")
    try:
        cfg = json.load(open(cfg_path))
        cfg.setdefault("Window", {}).update({
            "Width": 1280, "Height": 960, "PositionX": 0, "PositionY": 40,
            "Fullscreen": {"Enabled": False}})
        json.dump(cfg, open(cfg_path, "w"), indent=1)
    except Exception as e:  # noqa: BLE001
        print("warn: could not pin window config:", e, file=sys.stderr)


def run_engine(build, fk, max_frames):
    """Boot a <fk> vs <fk> battle with the skeleton dump enabled; -> log bytes."""
    exe = os.path.join(build, "BattleShip")
    if not os.access(exe, os.X_OK):
        raise SystemExit(f"engine binary not found/executable: {exe}")
    pin_window(build)
    env = dict(os.environ)
    env.update({
        "SSB64_BOOT_BATTLE": f"{fk},{fk},4,0",
        "SSB64_MUTE": "1",
        "SSB64_MAX_FRAMES": str(max_frames),
        "SSB64_DUMP_SKELETON": str(fk),
    })
    for k in ("SSB64_INJECT_BUNDLE", "SSB64_REPLAY_PLAY", "SSB64_DUMP_FRAMES"):
        env.pop(k, None)
    if os.path.exists(LOG):
        os.remove(LOG)
    subprocess.run(["./BattleShip"], cwd=build, env=env,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   check=True, timeout=300)
    with open(LOG, "rb") as f:
        return f.read()


# ---------------------------------------------------------------- glyphs
UI_REFS = os.path.join("web-prototype", "visual", "assets", "ui_refs")
# letter -> (fkind whose CSS name sprite is cut, x0, x1). These are the cuts
# that reproduce commit 0d6a8d90's hand re-slice byte-for-byte. NOTE they
# are offset by one column from pipeline/build_glyph_atlas.py BOLD_CUTS
# (B kirby 29-38, C pikachu 30-38, D dk 4-14, K dk 16-26): rebuilding the
# atlas with that script would regenerate these four glyphs differently.
GLYPH_CUTS = {"B": (8, 24, 33), "C": (9, 31, 40), "D": (2, 3, 13), "K": (2, 15, 25)}


def run_engine_css(build, out_dir, max_frames):
    """Boot to the VS character-select screen with the sprite dump on."""
    exe = os.path.join(build, "BattleShip")
    if not os.access(exe, os.X_OK):
        raise SystemExit(f"engine binary not found/executable: {exe}")
    pin_window(build)
    env = dict(os.environ)
    env.update({
        "SSB64_BOOT_BATTLE": "0,8,4,0",   # pre-seeds the board; START_SCENE keeps the CSS
        "SSB64_START_SCENE": "16",        # 16 = VS character select
        "SSB64_MUTE": "1",
        "SSB64_MAX_FRAMES": str(max_frames),
        "SSB64_DUMP_SPRITES": out_dir,    # port_ui_css_hook -> css_name_fk<N>.{json,bufs}
    })
    for k in ("SSB64_INJECT_BUNDLE", "SSB64_REPLAY_PLAY", "SSB64_DUMP_FRAMES",
              "SSB64_DUMP_SKELETON", "SSB64_INJECT_FKIND"):
        env.pop(k, None)
    os.makedirs(out_dir, exist_ok=True)
    if os.path.exists(LOG):
        os.remove(LOG)
    subprocess.run(["./BattleShip"], cwd=build, env=env,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   check=True, timeout=300)


def slice_glyphs(dump_dir, out_dir):
    """css_name_fk<N> dumps -> glyph_<ord>.png; -> {relpath: bytes}."""
    import io
    sys.path.insert(0, os.path.join(ROOT, "pipeline"))
    import sprite_codec  # noqa: E402  (needs Pillow)
    files = {}
    cache = {}
    for ch, (fk, x0, x1) in GLYPH_CUTS.items():
        if fk not in cache:
            cache[fk] = sprite_codec.decode(os.path.join(dump_dir, f"css_name_fk{fk}"))[0]
        g = cache[fk].crop((x0, 0, x1, 16)).copy()
        # IA8 texels with alpha 0 can carry a non-zero intensity (invisible);
        # the committed glyphs store those as (0,0,0,0).
        px = g.load()
        for y in range(g.height):
            for x in range(g.width):
                if px[x, y][3] == 0:
                    px[x, y] = (0, 0, 0, 0)
        buf = io.BytesIO()
        g.save(buf, "PNG")
        rel = os.path.join(UI_REFS, f"glyph_{ord(ch)}.png")
        p = os.path.join(out_dir, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(buf.getvalue())
        files[rel] = buf.getvalue()
    return files


def png_drift(a, b):
    try:
        import io
        from PIL import Image
        ia, ib = Image.open(io.BytesIO(a)).convert("RGBA"), Image.open(io.BytesIO(b)).convert("RGBA")
    except Exception as e:  # noqa: BLE001
        return f"cannot decode png: {e}"
    if ia.size != ib.size:
        return f"size differs {ia.size} vs {ib.size}"
    n = sum(1 for p, q in zip(ia.getdata(), ib.getdata()) if p != q)
    return f"{n} pixel(s) differ" if n else "same pixels, different PNG encoding"


# ---------------------------------------------------------------- verify
SK1 = re.compile(rb"SKELDUMP: joint=(\d+) parent=(-?\d+) world=\(([^)]*)\) "
                 rb"local=\(([^)]*)\) dl=(\S+) flags=(\S+)")
SK2 = re.compile(rb"SKELDUMP2: joint=(\d+) (.*)")


def skel_drift(a, b):
    """One-line description of how two .skel byte strings differ."""
    def index(data):
        d = {}
        for line in data.splitlines():
            m = SK1.match(line)
            if m:
                d[("SKELDUMP", int(m.group(1)))] = m
                continue
            m = SK2.match(line)
            if m:
                d[("SKELDUMP2", int(m.group(1)))] = m
        return d
    ia, ib = index(a), index(b)
    if set(ia) != set(ib):
        only_a = sorted(set(ia) - set(ib))
        only_b = sorted(set(ib) - set(ia))
        return f"joint set differs: missing={only_a[:6]} extra={only_b[:6]}"
    numeric, ptr = [], []
    for k in sorted(ia):
        ma, mb = ia[k], ib[k]
        if k[0] == "SKELDUMP":
            if (ma.group(2), ma.group(3), ma.group(4), ma.group(6)) != \
               (mb.group(2), mb.group(3), mb.group(4), mb.group(6)):
                numeric.append(k[1])
            elif ma.group(5) != mb.group(5):
                ptr.append(k[1])
        elif ma.group(2) != mb.group(2):
            numeric.append(k[1])
    if numeric:
        # all-world-shifted-by-root-offset (different spawn point)?
        def wl(m):
            return (tuple(float(v) for v in m.group(3).split(b",")),
                    tuple(float(v) for v in m.group(4).split(b",")))
        sk = [k for k in ia if k[0] == "SKELDUMP"]
        if ("SKELDUMP", 0) in ia and sk:
            off = tuple(x - y for x, y in zip(wl(ia[("SKELDUMP", 0)])[0],
                                              wl(ib[("SKELDUMP", 0)])[0]))
            ok = all(max(abs((wl(ia[k])[0][i] - wl(ib[k])[0][i]) - off[i])
                         for i in range(3)) < 0.0015
                     and (k[1] == 0 or wl(ia[k])[1] == wl(ib[k])[1])
                     and ia[k].group(2) == ib[k].group(2) for k in sk)
            if ok and any(off):
                return (f"different spawn point: every world= shifted by root offset "
                        f"{off}; hierarchy and local= identical"
                        + ("; committed lacks SKELDUMP2 lines" if
                           any(k[0] == "SKELDUMP2" for k in ib) and
                           not any(k[0] == "SKELDUMP2" for k in ia) else ""))
        j = numeric[0]
        k = ("SKELDUMP", j) if ("SKELDUMP", j) in ia and \
            ia[("SKELDUMP", j)].group(0) != ib[("SKELDUMP", j)].group(0) else ("SKELDUMP2", j)
        return (f"numeric drift on joints {sorted(set(numeric))}; e.g. "
                f"{ia[k].group(0).decode().strip()} -> {ib[k].group(0).decode().strip()}")
    if ptr:
        return (f"dl= in-block offsets differ on {len(ptr)} joints "
                f"(asset layout changed; all numeric content identical)")
    # fall back: something else (begin/end lines, extra text)
    la, lb = a.splitlines(), b.splitlines()
    for i, (x, y) in enumerate(zip(la, lb)):
        if x != y:
            return f"line {i+1} differs: {x[:60]!r} vs {y[:60]!r}"
    return f"length differs ({len(la)} vs {len(lb)} lines)"


def log_drift(a, b):
    """Raw engine logs: compare the parts that matter."""
    sa, pa = split_log(a)
    sb, pb = split_log(b)
    if pa != pb:
        return "MESHV vertex data differs"
    if sa != sb:
        return "SKELDUMP lines differ: " + skel_drift(sa, sb)
    return "only non-dump log lines differ (timestamps/pointers/boot chatter)"


def json_drift(a, b):
    try:
        ja, jb = json.loads(a), json.loads(b)
    except ValueError:
        return "invalid json"
    if ja == jb:
        return "same content, different formatting"
    if set(ja) != set(jb):
        return f"joint keys differ: {sorted(set(ja) ^ set(jb))}"
    bad = [k for k in ja if ja[k] != jb[k]]
    return f"vertex data differs for joints {bad}"


def compare(rel, derived, committed_path):
    if not os.path.exists(committed_path):
        return "NOT-COMMITTED", "no such file in the repo (nothing to compare)"
    committed = open(committed_path, "rb").read()
    if rel.endswith((".skel", ".log")):
        committed = normalize_dl(committed)  # same low-32-bit dl= form as derived
    if committed == derived:
        return "IDENTICAL", ""
    if rel.endswith(".skel"):
        return "DIFFERS", skel_drift(committed, derived)
    if rel.endswith(".log"):
        return "DIFFERS", log_drift(committed, derived)
    if rel.endswith(".png"):
        return "DIFFERS", png_drift(committed, derived)
    return "DIFFERS", json_drift(committed, derived)


# ---------------------------------------------------------------- main
def expected_files(name):
    fk = FIGHTERS.index(name)
    rels = [RAW_LOG_NAME.get(name, f"fk{fk}-all.log"), f"{name}.skel"]
    if name == "mario":
        rels.append("mario-frames.skel")
    if name in RAW_PARTS:
        rels.append(os.path.join("parts", f"vanilla-{name}-parts.json"))
    if name != "mario":
        rels.append(os.path.join("parts", f"vanilla-{name}-parts.canonical.json"))
    return rels


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--build-dir", default=os.path.join(ROOT, "BattleShip", "build-us"))
    ap.add_argument("--out", help="output root mirroring the repo layout (skels/..., "
                                  "web-prototype/...); pass the repo root to regenerate in place")
    ap.add_argument("--fighters", default=",".join(FIGHTERS),
                    help="comma list of names or fkinds (default all 12)")
    ap.add_argument("--max-frames", type=int, default=400,
                    help="SSB64_MAX_FRAMES: engine exits on its own after this")
    ap.add_argument("--from-logs", metavar="DIR",
                    help="do not run the engine; re-derive from raw logs in DIR "
                         "(e.g. skels/ itself) — checks the parsing/transform only")
    ap.add_argument("--verify", action="store_true",
                    help="derive into a temp dir and compare against skels/")
    ap.add_argument("--glyphs", action="store_true",
                    help="also dump the CSS name sprites and re-slice the "
                         "B/C/D/K glyph PNGs (one extra engine launch)")
    args = ap.parse_args()

    names = []
    for tok in args.fighters.split(","):
        tok = tok.strip()
        if not tok:
            continue
        names.append(FIGHTERS[int(tok)] if tok.isdigit() else tok)
    for n in names:
        if n not in FIGHTERS:
            raise SystemExit(f"unknown fighter {n!r}; choose from {FIGHTERS}")

    if not args.out and not args.verify:
        ap.error("need --out DIR and/or --verify")
    out = args.out or tempfile.mkdtemp(prefix="derive-skels-")
    os.makedirs(out, exist_ok=True)

    produced = {}
    ran = set()
    for n in names:
        fk = FIGHTERS.index(n)
        if args.from_logs:
            p = os.path.join(args.from_logs, RAW_LOG_NAME.get(n, f"fk{fk}-all.log"))
            if not os.path.exists(p):
                print(f"{n}: no raw log at {p}, skipped", file=sys.stderr)
                continue
            raw = open(p, "rb").read()
        else:
            print(f"[{n}] running engine (fkind={fk}) ...", file=sys.stderr, flush=True)
            raw = run_engine(args.build_dir, fk, args.max_frames)
        files = outputs_for(n, out, raw)
        produced.update(files)
        ran.add(n)
        print(f"[{n}] wrote {len(files)} files to {out}", file=sys.stderr)

    if args.glyphs:
        # The engine's css_name_fk<N> dumps are an intermediate: keep them out
        # of the output tree so --out <repo> never leaves strays behind.
        dump_dir = tempfile.mkdtemp(prefix="derive-skels-sprites-")
        if args.from_logs:
            dump_dir = os.path.join(args.from_logs, "sprite-dump")
        else:
            print("[glyphs] running engine (character select, sprite dump) ...",
                  file=sys.stderr, flush=True)
            run_engine_css(args.build_dir, dump_dir, args.max_frames)
        produced.update(slice_glyphs(dump_dir, out))
        print(f"[glyphs] wrote {len(GLYPH_CUTS)} glyph PNGs to {out}", file=sys.stderr)

    if not args.verify:
        return 0

    rows = []
    bad = 0
    if args.glyphs:
        for ch in GLYPH_CUTS:
            rel = os.path.join(UI_REFS, f"glyph_{ord(ch)}.png")
            status, why = compare(rel, produced[rel], os.path.join(ROOT, rel))
            if status not in ("IDENTICAL", "NOT-COMMITTED"):
                bad += 1
            rows.append((rel, status, why))
    for n in names:
        for rel in expected_files(n):
            committed = os.path.join(SKELS, rel)
            if rel not in produced:
                status, why = "NOT-PRODUCED", ("source log has no SKELDUMP lines"
                                               if rel.endswith(".skel") and n in ran
                                               else "engine did not run / no raw log")
            else:
                status, why = compare(rel, produced[rel], committed)
            if status not in ("IDENTICAL", "NOT-COMMITTED"):
                bad += 1
            rows.append((os.path.join("skels", rel), status, why))
    for rel, why in LEGACY_UNDERIVABLE.items():
        rows.append((os.path.join("skels", rel), "LEGACY", why))
    w = max(len(r[0]) for r in rows)
    for path, status, why in rows:
        print(f"{path:<{w}}  {status:<13} {why}")
    print(f"\n{len(rows) - bad}/{len(rows)} ok; derived output in {out}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
