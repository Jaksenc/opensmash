#!/usr/bin/env python3
"""Resumable batch builder for the technique tournament.

For every (character, config) cell: source image -> mesh -> rig ->
convert -> OSB5 bundle. State lives in eval/state.json so the run can be
killed and resumed; each stage is skipped when its artifact exists.
Configs can share the image or mesh of another config (no re-spend).

Usage: build_matrix.py [--chars mao,joey] [--configs A,B] [--stage image|mesh|convert|all]
"""
import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PIPE = os.path.dirname(HERE)
OUT = os.path.join(HERE, "cells")
STATE = os.environ.get("EVAL_STATE", os.path.join(HERE, "state.json"))

N64_TEMPLATE = (
    "A screenshot of a very low-poly 1996 Nintendo 64 fighting-game character "
    "model in T-pose: full body, front view, arms straight out horizontally, "
    "legs clearly apart with a gap between the feet, plain light-gray "
    "background, roughly 800 triangles, facial features painted flat onto the "
    "texture. The character: {desc}. Chunky fighter proportions: oversized "
    "head, short thick legs, big blocky hands. Flat solid colors with faint "
    "per-face shading, crisp boundaries, faceted low-poly look."
)
STYLE_NOTE = (" Match the art style, proportions, pose, framing and background of "
              "the attached low-poly Mario model sheet exactly (it is a STYLE "
              "reference only — the character must be {display}).")
PHOTO_NOTE = " Keep the exact likeness of the person in the attached photo(s)."


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def run(cmd, timeout=900):
    r = subprocess.run(cmd, cwd=PIPE, capture_output=True, text=True, timeout=timeout)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def load_state():
    return json.load(open(STATE)) if os.path.exists(STATE) else {}


def save_state(st):
    json.dump(st, open(STATE, "w"), indent=1)


def cell_dir(ch, cf):
    d = os.path.join(OUT, f"{ch}-{cf}")
    os.makedirs(d, exist_ok=True)
    return d


def stage_image(ch, cdef, cf, cdef_cfg, st):
    """Returns path to the T-pose image for this cell (may be shared)."""
    share = cdef_cfg.get("shares_image_with")
    if share:
        p = os.path.join(OUT, f"{ch}-{share}", "tpose.png")
        if os.path.exists(p):
            return p
        log(f"[{ch}-{cf}] waiting on shared image from {share}")
        return None
    d = cell_dir(ch, cf)
    p = os.path.join(d, "tpose.png")
    if os.path.exists(p):
        return p
    prompt = N64_TEMPLATE.format(desc=cdef["desc"])
    refs = [os.path.join(PIPE, r) for r in cdef.get("refs", [])]
    if cdef_cfg.get("style_ref"):
        refs.append(os.path.join(PIPE, cdef_cfg["style_ref"]))
        prompt += STYLE_NOTE.format(display=cdef["display"])
    if cdef.get("refs"):
        prompt += PHOTO_NOTE
    cmd = ["python3", "gen.py", "image", "--api", cdef_cfg["image_api"]]
    cmd += ["--model", "gpt-image-2" if cdef_cfg["image_api"] == "openai" else "gemini-3.1-flash-image"]
    for r in refs:
        cmd += ["--ref", r]
    cmd += [prompt, p]
    log(f"[{ch}-{cf}] image via {cdef_cfg['image_api']} refs={len(refs)}")
    rc, out = run(cmd, timeout=600)
    if rc != 0 or not os.path.exists(p):
        st.setdefault("errors", []).append({"cell": f"{ch}-{cf}", "stage": "image", "out": out[-400:]})
        log(f"[{ch}-{cf}] IMAGE FAILED: {out[-200:].strip()}")
        return None
    return p


def poll(cmd_status, parse, ok_vals, fail_vals, timeout_s=1500):
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        rc, out = run(cmd_status, timeout=120)
        s = parse(out)
        if s in ok_vals:
            return True
        if s in fail_vals:
            return False
        time.sleep(12)
    return False


def stage_mesh(ch, cf, cdef_cfg, img, st):
    share = cdef_cfg.get("shares_mesh_with")
    if share:
        p = os.path.join(OUT, f"{ch}-{share}", "rigged.glb")
        return p if os.path.exists(p) else None
    d = cell_dir(ch, cf)
    p = os.path.join(d, "rigged.glb")
    if os.path.exists(p):
        return p
    provider = cdef_cfg["mesh"]
    log(f"[{ch}-{cf}] mesh via {provider}")
    try:
        if provider == "meshy":
            rc, out = run(["python3", "gen.py", "img3d", "--polycount", "4000", img], timeout=300)
            tid = json.loads(out.strip().splitlines()[-1])["result"]
            ok = poll(["python3", "gen.py", "status", tid],
                      lambda o: json.loads(o.strip().splitlines()[-1]).get("status"),
                      {"SUCCEEDED"}, {"FAILED", "CANCELED"})
            if not ok:
                raise RuntimeError("meshy img3d failed")
            base = os.path.join(d, "base.glb")
            run(["python3", "gen.py", "download", tid, base], timeout=600)
            rc, out = run(["python3", "gen.py", "rig", base], timeout=300)
            rid = json.loads(out.strip().splitlines()[-1])
            rid = rid.get("result", rid) if isinstance(rid, dict) else rid
            ok = poll(["python3", "gen.py", "rigstatus", rid],
                      lambda o: json.loads(o.strip().splitlines()[-1]).get("status"),
                      {"SUCCEEDED"}, {"FAILED", "CANCELED"})
            if not ok:
                raise RuntimeError("meshy rig failed")
            run(["python3", "gen.py", "rigdownload", rid, p], timeout=600)
        else:  # tripo
            rc, out = run(["python3", "tripo.py", "upload", img], timeout=300)
            tok = json.loads(out.strip().splitlines()[-1])
            tok = tok.get("data", tok)["image_token"]
            rc, out = run(["python3", "tripo.py", "img3d", tok], timeout=300)
            if rc != 0:
                raise RuntimeError("tripo rejected: " + out[-160:].strip())
            tid = json.loads(out.strip().splitlines()[-1])
            tid = tid.get("data", tid)["task_id"]

            def tstat(o):
                import re
                m = re.search(r'"status": "([a-z]+)"', o)
                return m.group(1) if m else None
            if not poll(["python3", "tripo.py", "status", tid], tstat, {"success"}, {"failed", "cancelled", "banned"}):
                raise RuntimeError("tripo img3d failed")
            base = os.path.join(d, "base.glb")
            run(["python3", "tripo.py", "download", tid, base], timeout=600)
            rc, out = run(["python3", "tripo.py", "rig", tid], timeout=300)
            rid = json.loads(out.strip().splitlines()[-1])
            rid = rid.get("data", rid)["task_id"]
            if not poll(["python3", "tripo.py", "status", rid], tstat, {"success"}, {"failed", "cancelled", "banned"}):
                raise RuntimeError("tripo rig failed")
            run(["python3", "tripo.py", "download", rid, p], timeout=600)
        if not os.path.exists(p):
            raise RuntimeError("no rigged glb")
        return p
    except Exception as e:
        st.setdefault("errors", []).append({"cell": f"{ch}-{cf}", "stage": "mesh", "out": str(e)[-400:]})
        log(f"[{ch}-{cf}] MESH FAILED: {e}")
        return None


def stage_convert(ch, cf, cdef_cfg, img, rigged, st):
    d = cell_dir(ch, cf)
    osb = os.path.join(d, "bundle.osb")
    if os.path.exists(osb):
        return osb
    bundle = os.path.join(d, "bundle.json")
    cmd = ["python3", "convert_rigged.py", "--mild-color", "--no-profile", "--flatten"]
    for x in cdef_cfg.get("convert_extra", []):
        cmd.append(x)
        if x == "--project-source":
            cmd.append(img)
    cmd += [rigged, "mario-frames.skel", bundle]
    log(f"[{ch}-{cf}] convert")
    rc, out = run(cmd, timeout=1200)
    if rc != 0:
        st.setdefault("errors", []).append({"cell": f"{ch}-{cf}", "stage": "convert", "out": out[-500:]})
        log(f"[{ch}-{cf}] CONVERT FAILED: {out[-300:].strip()}")
        return None
    open(os.path.join(d, "convert.log"), "w").write(out)
    rc, out = run(["python3", "convert_rigged.py", "--binary5", bundle, osb], timeout=600)
    if rc != 0 or not os.path.exists(osb):
        st.setdefault("errors", []).append({"cell": f"{ch}-{cf}", "stage": "binary5", "out": out[-400:]})
        return None
    return osb


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chars", default=None)
    ap.add_argument("--configs", default=None)
    ap.add_argument("--stage", default="all")
    a = ap.parse_args()
    chars = json.load(open(os.path.join(HERE, "characters.json")))
    cfgs = json.load(open(os.path.join(HERE, "configs.json")))
    chs = a.chars.split(",") if a.chars else list(chars)
    cfs = a.configs.split(",") if a.configs else list(cfgs)
    st = load_state()
    # order: non-sharing configs first so shared artifacts exist
    cfs = sorted(cfs, key=lambda c: 1 if (cfgs[c].get("shares_image_with") or cfgs[c].get("shares_mesh_with")) else 0)
    for ch in chs:
        for cf in cfs:
            key = f"{ch}-{cf}"
            cell = st.setdefault("cells", {}).setdefault(key, {})
            img = stage_image(ch, chars[ch], cf, cfgs[cf], st)
            cell["image"] = img
            save_state(st)
            if not img or a.stage == "image":
                continue
            rigged = stage_mesh(ch, cf, cfgs[cf], img, st)
            cell["rigged"] = rigged
            save_state(st)
            if not rigged or a.stage == "mesh":
                continue
            osb = stage_convert(ch, cf, cfgs[cf], img, rigged, st)
            cell["osb"] = osb
            cell["done"] = bool(osb)
            save_state(st)
            log(f"[{key}] {'DONE' if osb else 'incomplete'}")
    save_state(st)
    done = sum(1 for c in st.get("cells", {}).values() if c.get("done"))
    log(f"matrix: {done} cells done, {len(st.get('errors', []))} errors")


if __name__ == "__main__":
    main()
