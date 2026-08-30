#!/usr/bin/env python3
"""Build a frame-aligned side-by-side web player from two deterministic runs.

The replay tour is deterministic, so tick N of the test run and tick N of the
reference run differ only in the replaced mesh. The player shows TEST | REF
side by side as a synced video (play/pause/scrub/speed), steps frame by
frame, and has a flicker mode that alternates both runs on one panel —
anything that "moves" while flickering is a pipeline difference.

Usage:
  make_viewer.py test_shots_dir ref_shots_dir out_dir --name queen-samus
"""
import argparse
import json
import os
import re
import shutil

LABELS = {410: "walk", 455: "idle", 515: "jab", 557: "jab2", 605: "ftilt", 675: "utilt",
          745: "crouch", 785: "fsmash", 895: "usmash", 975: "jump", 990: "air",
          1045: "land", 1085: "jump2", 1099: "nair", 1155: "shield",
          1225: "taunt", 1300: "idle", 1350: "walk-back", 1420: "idle", 1505: "special"}

HTML = """<!doctype html><html><head><meta charset="utf-8"><title>__NAME__</title>
<style>
  html,body { margin:0; background:#0c0c10; color:#ccc; font:13px/1.5 ui-monospace,monospace; }
  #wrap { display:flex; flex-direction:column; align-items:center; gap:8px; padding:10px; }
  #panels { display:flex; gap:6px; justify-content:center; }
  .panel { position:relative; }
  .panel img { display:block; width:46vw; max-height:66vh; object-fit:contain; background:#000; }
  .panel .cap { position:absolute; top:6px; left:8px; padding:1px 8px; border-radius:4px;
                font-weight:700; background:#0009; }
  #capT { color:#ffd479; } #capR { color:#8fe0a4; }
  body.flicker #panelR { display:none; }
  body.flicker .panel img { width:80vw; max-height:74vh; }
  #bar { display:flex; gap:14px; align-items:center; width:92vw; }
  #scrub { flex:1; }
  .tag { padding:2px 10px; border-radius:5px; background:#222; white-space:nowrap; }
  button { background:#222; color:#ddd; border:1px solid #444; border-radius:5px;
           font:inherit; padding:2px 12px; cursor:pointer; }
  button.on { background:#5a3f13; color:#ffd479; border-color:#8a6420; }
  #load { color:#777; }
  #help { color:#666; font-size:12px; }
</style></head><body>
<div id="wrap">
  <div id="panels">
    <div class="panel" id="panelT"><span class="cap" id="capT">TEST __NAME__</span><img id="imT"></div>
    <div class="panel" id="panelR"><span class="cap" id="capR">REFERENCE vanilla</span><img id="imR"></div>
  </div>
  <div id="bar">
    <button id="play">&#9654;</button>
    <input type="range" id="scrub" min="0" value="0">
    <span class="tag" id="tick"></span>
    <span class="tag" id="label"></span>
    <button id="spd">1x</button>
    <button id="flick">flicker</button>
  </div>
  <div id="help">space=play/pause &nbsp; a/d=frame step &nbsp; &larr;&rarr;=jump &nbsp; f=flicker mode (one panel alternating test/ref) &nbsp; loops at end</div>
  <div id="load"></div>
</div>
<script>
const FRAMES = __FRAMES__;
const LABELS = __LABELS__;
const imT = document.getElementById('imT'), imR = document.getElementById('imR');
const scrub = document.getElementById('scrub'); scrub.max = FRAMES.length - 1;
let i = 0, playing = false, speed = 1, timer = null, flickB = false, flickTimer = null;
const cacheT = [], cacheR = [];
let loaded = 0;
FRAMES.forEach((f, j) => {
  for (const [c, run] of [[cacheT, 'test'], [cacheR, 'ref']]) {
    const im = new Image();
    im.src = run + '/frame_' + f + '.png';
    im.onload = () => { if (++loaded % 50 === 0 || loaded === FRAMES.length * 2)
      document.getElementById('load').textContent =
        loaded < FRAMES.length * 2 ? 'preloading ' + loaded + '/' + FRAMES.length * 2 : ''; };
    c.push(im);
  }
});
function update() {
  const f = FRAMES[i];
  if (document.body.classList.contains('flicker')) {
    imT.src = (flickB ? cacheR : cacheT)[i].src;
    document.getElementById('capT').textContent = flickB ? 'REFERENCE vanilla' : 'TEST __NAME__';
    document.getElementById('capT').style.color = flickB ? '#8fe0a4' : '#ffd479';
  } else {
    imT.src = cacheT[i].src; imR.src = cacheR[i].src;
    document.getElementById('capT').textContent = 'TEST __NAME__';
    document.getElementById('capT').style.color = '#ffd479';
  }
  scrub.value = i;
  document.getElementById('tick').textContent = 'tick ' + f + ' (' + (i+1) + '/' + FRAMES.length + ')';
  let lab = '', best = -1;
  for (const k in LABELS) { if (+k <= f && +k > best) { best = +k; lab = LABELS[k]; } }
  document.getElementById('label').textContent = lab;
}
function setPlaying(p) {
  playing = p;
  document.getElementById('play').innerHTML = p ? '&#10074;&#10074;' : '&#9654;';
  clearInterval(timer);
  if (p) timer = setInterval(() => { i = (i + 1) % FRAMES.length; update(); }, 50 / speed);
}
function step(d) { setPlaying(false); i = Math.max(0, Math.min(FRAMES.length - 1, i + d)); update(); }
document.getElementById('play').addEventListener('click', () => setPlaying(!playing));
scrub.addEventListener('input', () => { setPlaying(false); i = +scrub.value; update(); });
document.getElementById('spd').addEventListener('click', (e) => {
  speed = speed === 1 ? 0.5 : speed === 0.5 ? 2 : 1;
  e.target.textContent = speed + 'x';
  if (playing) setPlaying(true);
});
function setFlicker(on) {
  document.body.classList.toggle('flicker', on);
  document.getElementById('flick').classList.toggle('on', on);
  clearInterval(flickTimer); flickTimer = null;
  if (on && !playing) flickTimer = setInterval(() => { flickB = !flickB; update(); }, 320);
  update();
}
document.getElementById('flick').addEventListener('click', () =>
  setFlicker(!document.body.classList.contains('flicker')));
document.addEventListener('keydown', (e) => {
  if (e.code === 'Space') { e.preventDefault(); setPlaying(!playing); }
  else if (e.key === 'd') step(1);
  else if (e.key === 'a') step(-1);
  else if (e.code === 'ArrowRight') step(15);
  else if (e.code === 'ArrowLeft') step(-15);
  else if (e.key === 'f') setFlicker(!document.body.classList.contains('flicker'));
});
update();
</script></body></html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("test_shots")
    ap.add_argument("ref_shots", nargs="?", default=None)
    ap.add_argument("out")
    ap.add_argument("--split", action="store_true",
                    help="single dual-fighter run: left half = test (P1), right half = reference (P2)")
    ap.add_argument("--name", default="eval")
    ap.add_argument("--labels", default=None, help="replay sidecar json with tour marks")
    args = ap.parse_args()
    labels = LABELS
    if args.labels and os.path.exists(args.labels):
        marks = json.load(open(args.labels))["marks"]
        # capture frames are replay ticks — marks align directly
        labels = {t: lab for t, lab in marks
                  if not lab.startswith(("pre-", "idle", "face", "reface"))}

    def frames_in(d):
        return {int(m.group(1)) for n in os.listdir(d)
                if (m := re.match(r"frame_(\d+)\.png$", n))}

    if args.split:
        # one dual-fighter run: P1 (test) walks the tour left of P2
        # (vanilla reference) doing the identical tour — same frame, so
        # zero run-to-run jitter. The pair drifts around during walks, so
        # a fixed middle split leaks each fighter into the other's panel;
        # instead detect the two silhouettes per frame and crop a fixed
        # window around each.
        from PIL import Image
        import numpy as np
        frames = sorted(frames_in(args.test_shots))
        if not frames:
            raise SystemExit("no frames")
        os.makedirs(os.path.join(args.out, "test"), exist_ok=True)
        os.makedirs(os.path.join(args.out, "ref"), exist_ok=True)
        WIN = 520
        last = None
        for f in frames:
            dt = os.path.join(args.out, "test", f"frame_{f}.png")
            dr = os.path.join(args.out, "ref", f"frame_{f}.png")
            if os.path.exists(dt) and os.path.exists(dr):
                continue
            im = Image.open(os.path.join(args.test_shots, f"frame_{f}.png"))
            w, h = im.size
            a = np.asarray(im.convert("RGB")).astype(int)
            bg = (abs(a[:, :, 0] - 52) < 16) & (abs(a[:, :, 1] - 52) < 16) & (abs(a[:, :, 2] - 58) < 16)
            colx = (~bg).sum(axis=0)
            xs = np.nonzero(colx > 2)[0]
            if len(xs) < 10:
                centers = last or (w // 3, 2 * w // 3)
            else:
                # widest interior gap between occupied columns = the split
                gaps = np.diff(xs)
                gi = int(np.argmax(gaps))
                if gaps[gi] < 20:
                    centers = last or (w // 3, 2 * w // 3)
                else:
                    left = xs[: gi + 1]
                    right = xs[gi + 1:]
                    centers = (int(left.mean()), int(right.mean()))
            last = centers
            for cx, dst in zip(centers, (dt, dr)):
                x0 = max(0, min(w - WIN, cx - WIN // 2))
                im.crop((x0, 0, x0 + WIN, h)).save(dst)
    else:
        if not args.ref_shots:
            raise SystemExit("ref_shots required without --split")
        common = sorted(frames_in(args.test_shots) & frames_in(args.ref_shots))
        if not common:
            raise SystemExit("no common frames between the two runs")
        # auto-align: the two runs boot a few ticks apart, so identical
        # frame numbers can be different animation phases (fast moves then
        # look "distorted"). Estimate the constant offset by matching the
        # fighter's centroid path, then pair test[f] with ref[f + delta].
        import numpy as np
        from PIL import Image
        step = common[1] - common[0] if len(common) > 1 else 2

        def centroid(path):
            a = np.asarray(Image.open(path).convert("RGB")).astype(int)
            m = (abs(a[:, :, 0] - 52) > 18) | (abs(a[:, :, 1] - 52) > 18) | (abs(a[:, :, 2] - 58) > 18)
            ys, xs = np.nonzero(m)
            if len(xs) < 50:
                return None
            return (float(xs.mean()), float(ys.mean()))

        probe = [f for f in common if f <= common[0] + 400]
        ct = {f: centroid(os.path.join(args.test_shots, f"frame_{f}.png")) for f in probe}
        cr = {f: centroid(os.path.join(args.ref_shots, f"frame_{f}.png")) for f in probe}
        best_d, best_err = 0, None
        for d in range(-10, 11, step if step > 1 else 1):
            errs = []
            for f in probe:
                a, b = ct.get(f), cr.get(f + d)
                if a and b:
                    errs.append(abs(a[0] - b[0]) + abs(a[1] - b[1]))
            if len(errs) > 20:
                e = sum(errs) / len(errs)
                if best_err is None or e < best_err:
                    best_err, best_d = e, d
        if best_err is None or best_err > 30:
            # a trustworthy match keeps the fighter paths within a few
            # pixels; anything worse means the probe failed — don't shift.
            if best_d:
                print(f"run alignment: probe inconclusive "
                      f"(err {best_err if best_err is not None else -1:.1f}px), no shift applied")
            best_d = 0
        elif best_d:
            print(f"run alignment: reference shifted {best_d:+d} ticks "
                  f"(mean centroid error {best_err:.1f}px)")
        # viewport normalization: the native Metal window sometimes renders
        # into a sub-region of the frame (the long-standing resize bug),
        # leaving black bands and a smaller fighter. The game viewport is
        # the non-black region — crop to it and rescale so both runs
        # present identically regardless of the window lottery.
        def viewport_bbox(sample_paths):
            boxes = []
            for sp in sample_paths:
                a = np.asarray(Image.open(sp).convert("RGB")).astype(int)
                nb = a.sum(axis=2) > 30
                ys, xs = np.nonzero(nb)
                if len(xs) > 1000:
                    boxes.append((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))
            if not boxes:
                return None
            return (min(b[0] for b in boxes), min(b[1] for b in boxes),
                    max(b[2] for b in boxes), max(b[3] for b in boxes))

        frames = [f for f in common if (f + best_d) in frames_in(args.ref_shots)]
        OUT_W, OUT_H = 1024, 768
        for run, src, off in (("test", args.test_shots, 0), ("ref", args.ref_shots, best_d)):
            os.makedirs(os.path.join(args.out, run), exist_ok=True)
            probe_paths = [os.path.join(src, f"frame_{f + off}.png") for f in frames[:200:20]]
            vb = viewport_bbox(probe_paths)
            for f in frames:
                dst = os.path.join(args.out, run, f"frame_{f}.png")
                if os.path.exists(dst):
                    continue
                im = Image.open(os.path.join(src, f"frame_{f + off}.png"))
                if vb:
                    im = im.crop(vb)
                im.resize((OUT_W, OUT_H), Image.LANCZOS).save(dst)
    html = (HTML.replace("__NAME__", args.name)
                .replace("__FRAMES__", json.dumps(frames))
                .replace("__LABELS__", json.dumps(labels)))
    open(os.path.join(args.out, "index.html"), "w").write(html)
    print(f"viewer: {len(frames)} paired frames -> {args.out}/index.html")


if __name__ == "__main__":
    main()
