#!/usr/bin/env python3
"""One command: name -> playable injected fighter with full UI assets.

  run_character.py "Weird Al Yankovic" [--short WEIRDAL] [--photo ref.png]
                   [--emblem "context or object"] [--out play/ui/<slug>]
                   [--force-stage <stage>]

Stages (each skipped if its output already exists — delete a file or use
--force-stage to redo): expand -> tpose -> mesh (Tripo v3 + rig) ->
convert -> portrait art -> stock art -> ui pack -> announcer voice -> stage.

LLM callouts: Gemini for the character description, gpt-image-2 for the
three images, MiniMax (via fal) for the announcer clip. Everything else is
deterministic.
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
WEBDIST = os.path.join(HERE, "..", "BattleShip", "web-dist", "bundles")

N64_TEMPLATE = (
    "A screenshot of a very low-poly 1996 Nintendo 64 fighting-game character "
    "model in T-pose: full body, front view, arms straight out horizontally, "
    "legs clearly apart with a gap between the feet, plain light-gray "
    "background, roughly 800 triangles, facial features painted flat onto the "
    "texture. The character: {desc} Chunky fighter proportions: oversized "
    "head, short thick legs, big blocky hands, hands empty (nothing held, "
    "nothing hanging from the arms). Flat solid colors with faint "
    "per-face shading, crisp boundaries, faceted low-poly look. "
    "Match the art style, proportions, pose, framing and background of the "
    "attached low-poly Mario model sheet exactly (it is a STYLE reference "
    "only — the character must be {display})."
)
PHOTO_NOTE = " Keep the exact likeness of the person in the attached photo(s)."
PORTRAIT_TEMPLATE = (
    "Character select screen portrait tile for a 1999 Nintendo 64 fighting "
    "game, in exactly the same art style as the three reference portrait "
    "tiles (pre-rendered 90s CGI bust, soft plastic-like shading, slightly "
    "grainy, dark fiery red-black background with embers): a bust portrait "
    "of the character shown in the fourth reference image. Head and "
    "shoulders, three-quarter view facing slightly left, dramatic warm "
    "lighting from upper left. NO text, NO letters, NO border. Square image."
)
STOCK_TEMPLATE = (
    "A tiny video-game stock/life icon in the exact style of the first "
    "reference image (Super Smash Bros 64 stock icon): the head of the "
    "character from the second reference image, drawn as extremely simple "
    "chibi pixel art with huge bold shapes, flat solid colors only (max 6 "
    "colors), thick black outline around the whole silhouette, straight-on "
    "view, centered, filling the frame. Solid pure green background "
    "(#00FF00). No text, no shading gradients, no dithering."
)
EMBLEM_TEMPLATE = (
    "A flat 2D video game series emblem symbol for the character {display}: "
    "ONE single iconic object strongly associated with this character{obj} "
    "— never the character themselves, no face, no figure — in the chunky "
    "simple style of the 1990s Nintendo 64 series emblems in the first "
    "reference image (the game's own ten emblems: mushroom, DK, screw "
    "attack, Star Fox, star, triforce, Yoshi egg, F-Zero, Poke Ball, "
    "globe). One bold glyph, straight-on view, perfectly centered, filling "
    "most of the frame, strong dark outline. "
    "CRITICAL: the emblem is also read as a ONE-COLOR STENCIL, so it must "
    "be recognizable from its shape alone. Build the object out of a few "
    "LARGE flat color regions with strong light/dark contrast between "
    "neighbors, each separated by a thick dark line, so the interior "
    "structure is as bold as the outline — the way the Poke Ball's band "
    "and center or Yoshi's egg spots survive as pure shape. No thin "
    "scratches, hairlines or engraved detail. "
    "Flat solid colors only (max 5 colors), no shading gradients, no "
    "dithering. Solid pure green background (#00FF00). No text, no letters."
)
# appended on a re-roll when the stencil came out as a featureless blob
EMBLEM_RETRY = (
    " The previous attempt was one solid uncut shape and read as a blob. "
    "Give the object much bolder INTERNAL structure: two or three big "
    "clearly separated regions of very different brightness (a dark region "
    "against a light region), and thick dark dividing lines across the "
    "body of the object."
)


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def sh(cmd, timeout=900):
    r = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd[:3])}... failed:\n{(r.stdout or '') + (r.stderr or '')}"[-800:])
    return r.stdout


def tripo_json(out):
    """tripo.py prints one JSON object (possibly {'code':0,'data':...}).
    Some Tripo status payloads embed raw control characters — fall back to
    regex field extraction rather than dying on strict JSON."""
    i = out.index("{")
    try:
        obj = json.loads(out[i:], strict=False)
        return obj.get("data", obj)
    except json.JSONDecodeError:
        fields = dict(re.findall(r'"(\w+)"\s*:\s*"([^"\x00-\x1f]*)"', out))
        if "status" in fields or "task_id" in fields or "image_token" in fields:
            return fields
        raise


def stage_needed(path, force, name):
    if force == name:
        return True
    return not os.path.exists(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("--short", default=None, help="display name for in-game text (<=7 chars, A-Z)")
    ap.add_argument("--photo", default=None)
    ap.add_argument("--emblem", default=None,
                    help="context for the series emblem, or the object itself "
                         "(\"a red accordion\", \"he restores lighthouses\"). "
                         "Default: inferred from the name and photo. Also "
                         "editable afterwards as \"emblem\" in character.json.")
    ap.add_argument("--out", default=None)
    ap.add_argument("--force-stage", default=None,
                    choices=["expand", "tpose", "mesh", "convert", "variants", "portrait", "stock", "emblem", "ui", "voice"])
    a = ap.parse_args()

    slug = re.sub(r"[^a-z0-9]", "", a.name.lower())[:16]
    out = a.out or os.path.join(HERE, "play", "ui", slug)
    os.makedirs(out, exist_ok=True)
    F = lambda n: os.path.join(out, n)
    force = a.force_stage

    # 1. expand ----------------------------------------------------------
    if stage_needed(F("character.json"), force, "expand"):
        log("expand: describing character")
        cmd = ["python3", "expand_character.py", a.name]
        if a.photo:
            cmd += ["--photo", a.photo]
        if a.emblem:
            cmd += ["--emblem", a.emblem]
        open(F("character.json"), "w").write(sh(cmd, timeout=180))
    cdef = json.loads(open(F("character.json")).read())
    short = (a.short or cdef.get("short") or re.sub(r"[^A-Za-z]", "", cdef["display"]).upper())
    short = re.sub(r"[^A-Z]", "", short.upper())[:7]
    log(f"character: {cdef['display']} (short: {short})")

    # 2. tpose -----------------------------------------------------------
    if stage_needed(F("tpose.png"), force, "tpose"):
        log("tpose: generating source image")
        prompt = N64_TEMPLATE.format(desc=cdef["desc"], display=cdef["display"])
        cmd = ["python3", "gen.py", "image", "--api", "openai", "--model", "gpt-image-2",
               "--ref", os.path.join(HERE, "vg7-tpose.png")]
        if a.photo:
            cmd += ["--ref", a.photo]
            prompt += PHOTO_NOTE
        sh(cmd + [prompt, F("tpose.png")], timeout=600)

    # 3. mesh + rig ------------------------------------------------------
    if stage_needed(F("rigged.glb"), force, "mesh"):
        log("mesh: uploading to Tripo")
        tok = tripo_json(sh(["python3", "tripo.py", "upload", F("tpose.png")], timeout=300))["image_token"]
        task = tripo_json(sh(["python3", "tripo.py", "img3d", tok], timeout=120))["task_id"]
        log(f"mesh: img3d task {task}")
        for _ in range(90):
            st = tripo_json(sh(["python3", "tripo.py", "status", task], timeout=60))
            if st["status"] in ("success", "failed", "banned"):
                break
            time.sleep(10)
        if st["status"] != "success":
            raise RuntimeError(f"img3d {st['status']}")
        rig = tripo_json(sh(["python3", "tripo.py", "rig", task], timeout=120))["task_id"]
        log(f"mesh: rig task {rig}")
        for _ in range(90):
            st = tripo_json(sh(["python3", "tripo.py", "status", rig], timeout=60))
            if st["status"] in ("success", "failed", "banned"):
                break
            time.sleep(10)
        if st["status"] != "success":
            raise RuntimeError(f"rig {st['status']}")
        sh(["python3", "tripo.py", "download", rig, F("rigged.glb")], timeout=600)

    # 4. convert ---------------------------------------------------------
    osb = os.path.join(HERE, "play", f"{slug}.osb")
    if stage_needed(osb, force, "convert"):
        log("convert: retargeting onto the game skeleton")
        outtxt = sh(["python3", "convert_rigged.py", "--mild-color", "--no-profile", "--flatten",
                     F("rigged.glb"), "mario-frames.skel", F("bundle.json")], timeout=900)
        torn = re.search(r"torn-tri cut: (\d+)", outtxt)
        if torn and int(torn.group(1)) > 80:
            raise RuntimeError(f"torn-tri gate: {torn.group(1)} > 80 — bad mesh, re-roll tpose/mesh")
        sh(["python3", "convert_rigged.py", "--binary5", F("bundle.json"), osb], timeout=300)

    # 4b. variants -------------------------------------------------------
    # Conversion is pure deterministic geometry (no model calls), so cut
    # the mesh onto EVERY target fighter skeleton with a profile. Gives
    # multi-injection demos a free pick of slots per character.
    variants = sorted(
        os.path.basename(pj)[:-len(".profile.json")]
        for pj in glob.glob(os.path.join(HERE, "skels", "*.profile.json")))
    for tgt in variants:
        vosb = os.path.join(HERE, "play", f"{slug}-{tgt}.osb")
        if not stage_needed(vosb, force, "variants"):
            continue
        log(f"variants: retargeting onto {tgt}")
        vjson = F(f"bundle-{tgt}.json")
        try:
            sh(["python3", "convert_rigged.py", "--mild-color", "--flatten",
                "--target", os.path.join(HERE, "skels", f"{tgt}.profile.json"),
                F("rigged.glb"), os.path.join(HERE, "skels", f"{tgt}.skel"), vjson],
               timeout=900)
            sh(["python3", "convert_rigged.py", "--binary5", vjson, vosb], timeout=300)
        except Exception as e:
            log(f"variants: {tgt} FAILED ({e}) — continuing")

    # 5+6. UI art --------------------------------------------------------
    if stage_needed(F("portrait_raw.png"), force, "portrait"):
        log("portrait: generating tile art")
        refs = []
        for r in ("tile_mario", "tile_samus", "tile_link"):
            up = F(f"_styleref_{r}.png")
            sh(["python3", "-c",
                f"from PIL import Image; im=Image.open('ui_refs/{r}.png').convert('RGB');"
                f"im.resize((im.width*8,im.height*8),Image.LANCZOS).save('{up}')"])
            refs += ["--ref", up]
        sh(["python3", "gen.py", "image"] + refs + ["--ref", F("tpose.png"),
            PORTRAIT_TEMPLATE, F("portrait_raw.png")], timeout=600)
    if stage_needed(F("stock_raw.png"), force, "stock"):
        log("stock: generating icon art")
        sh(["python3", "gen.py", "image", "--ref", os.path.join(HERE, "ui_refs", "stockicon_ref.png"),
            "--ref", F("tpose.png"), STOCK_TEMPLATE, F("stock_raw.png")], timeout=600)
    if stage_needed(F("emblem_raw.png"), force, "emblem"):
        # --emblem beats whatever the expander inferred, so the object can be
        # steered without re-running the expand stage.
        obj = a.emblem or cdef.get("emblem") or ""
        log(f"emblem: generating series-emblem art{' (' + obj + ')' if obj else ''}")
        prompt = EMBLEM_TEMPLATE.format(display=cdef["display"],
                                        obj=f", specifically {obj}," if obj else "")
        # The engine draws the emblem as a flat one-color stencil, so gate on
        # the stencil, not on the art: a gorgeous solid object is still a blob.
        for _ in range(2):
            sh(["python3", "gen.py", "image",
                "--ref", os.path.join(HERE, "ui_refs", "emblem_ref.png"),
                prompt, F("emblem_raw.png")], timeout=600)
            st = json.loads(sh(["python3", "emblem_stencil.py", F("emblem_raw.png")],
                               timeout=120))
            log(f"emblem: stencil cut {st['cut_frac']:.0%} in {st['cuts']} holes")
            if not st.get("blobby"):
                break
            log("emblem: featureless blob — re-rolling with bolder interior")
            prompt += EMBLEM_RETRY

    # 7. pack ------------------------------------------------------------
    osbui = F(f"{slug}.osbui")
    if stage_needed(osbui, force, "ui"):
        log("ui: packing .osbui")
        sh(["python3", "gen_ui_assets.py", osbui, "--art", F("portrait_raw.png"),
            "--stock-art", F("stock_raw.png"), "--emblem", F("emblem_raw.png"),
            "--name", short], timeout=300)

    # 8. voice -----------------------------------------------------------
    wav = F("announcer.wav")
    if stage_needed(wav, force, "voice"):
        log("voice: generating announcer clip")
        sh(["python3", "announcer_voice.py", cdef["display"], "--slug", slug,
            "--out", wav, "--no-stage"], timeout=300)

    # 9. stage -----------------------------------------------------------
    if os.path.isdir(WEBDIST):
        stage_files = [(osb, f"{slug}.osb"), (osbui, f"{slug}.osbui"), (wav, f"{slug}.wav")]
        for tgt in variants:
            vosb = os.path.join(HERE, "play", f"{slug}-{tgt}.osb")
            if os.path.exists(vosb):
                stage_files.append((vosb, f"{slug}-{tgt}.osb"))
        for src, base in stage_files:
            dst = os.path.join(WEBDIST, base)
            open(dst, "wb").write(open(src, "rb").read())
        log(f"staged into web-dist/bundles ({len(stage_files)} files)")
    url = (f"http://localhost:8600/index.html?inject=bundles/{slug}.osb"
           f"&inject_ui=bundles/{slug}.osbui&inject_voice=bundles/{slug}.wav"
           f"&SSB64_START_SCENE=16")
    log(f"done: {url}")


if __name__ == "__main__":
    main()
