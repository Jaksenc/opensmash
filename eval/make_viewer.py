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
    ap.add_argument("ref_shots")
    ap.add_argument("out")
    ap.add_argument("--name", default="eval")
    ap.add_argument("--labels", default=None, help="replay sidecar json with tour marks")
    args = ap.parse_args()
    labels = LABELS
    if args.labels and os.path.exists(args.labels):
        marks = json.load(open(args.labels))["marks"]
        # +40: game frames elapsed before the scene consumes replay ticks
        labels = {t + 40: lab for t, lab in marks
                  if not lab.startswith(("pre-", "idle", "face", "reface"))}

    def frames_in(d):
        return {int(m.group(1)) for n in os.listdir(d)
                if (m := re.match(r"frame_(\d+)\.png$", n))}

    frames = sorted(frames_in(args.test_shots) & frames_in(args.ref_shots))
    if not frames:
        raise SystemExit("no common frames between the two runs")
    for run, src in (("test", args.test_shots), ("ref", args.ref_shots)):
        os.makedirs(os.path.join(args.out, run), exist_ok=True)
        for f in frames:
            dst = os.path.join(args.out, run, f"frame_{f}.png")
            if not os.path.exists(dst):
                shutil.copy(os.path.join(src, f"frame_{f}.png"), dst)
    html = (HTML.replace("__NAME__", args.name)
                .replace("__FRAMES__", json.dumps(frames))
                .replace("__LABELS__", json.dumps(labels)))
    open(os.path.join(args.out, "index.html"), "w").write(html)
    print(f"viewer: {len(frames)} paired frames -> {args.out}/index.html")


if __name__ == "__main__":
    main()
