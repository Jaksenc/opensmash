#!/usr/bin/env python3
"""Render-based facing check: does the converted bundle face the camera?

  facing_check.py play/ui/<slug>/bundle.json play/ui/<slug>/tpose.png [--skel skels/mario-frames.skel]

Renders the bundle at yaw 0 and yaw 180 (preview_bundle.py, the in-game
texture path) and asks the vision model which render matches the t-pose,
which is the FRONT view by construction. Prints one JSON line:
  {"flipped": bool, "front_render": "A"|"B", "confidence": ..., "cost_usd": ...}
"flipped" means the yaw-0 render shows the back, i.e. convert_rigged's
geometric cues (skin colour / head offset / toe reach) misread this body and
the conversion should be redone with --flip-facing. Built for non-human
bodies (Cthulhu, the Jersey Devil) where there are no skin verts to vote.
"""
import argparse, base64, json, os, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gen import http, ENV, token_cost

SCHEMA = {"type": "object",
          "properties": {"front_render": {"type": "string", "enum": ["A", "B"]},
                         "confidence": {"type": "string", "enum": ["high", "medium", "low"]}},
          "required": ["front_render", "confidence"], "additionalProperties": False}
PROMPT = ("Image 1 is the reference: a character model sheet seen from the FRONT (face and chest toward "
          "the camera). Images 2 (render A) and 3 (render B) are the same character's converted 3D "
          "model rendered from opposite sides. Which render shows the character's FRONT, matching the "
          "reference — face, eyes, chest, or the front of the costume toward the camera? If a render "
          "shows the back of the head, the back of a cape or wings covering the torso, or no facial "
          "features, that is the back. Answer with the render letter.")

def data_url(path):
    return "data:image/png;base64," + base64.b64encode(open(path, "rb").read()).decode()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bundle"); ap.add_argument("tpose")
    ap.add_argument("--skel", default=os.path.join(os.path.dirname(HERE), "skels", "mario-frames.skel"))
    ap.add_argument("--model", default="gpt-5.6-luna")
    ap.add_argument("--keep", default=None, help="directory to keep the two renders in")
    a = ap.parse_args()
    out = a.keep or tempfile.mkdtemp(prefix="facing-")
    os.makedirs(out, exist_ok=True)
    renders = {}
    for tag, yaw in (("A", 0), ("B", 180)):
        p = os.path.join(out, f"yaw{yaw}.png")
        subprocess.run([sys.executable, os.path.join(HERE, "preview_bundle.py"), a.bundle, a.skel, p,
                        "--yaw", str(yaw), "--size", "384"], check=True, capture_output=True)
        renders[tag] = p
    content = [{"type": "input_text", "text": PROMPT},
               {"type": "input_image", "image_url": data_url(a.tpose)},
               {"type": "input_image", "image_url": data_url(renders["A"])},
               {"type": "input_image", "image_url": data_url(renders["B"])}]
    r = http("https://api.openai.com/v1/responses", "POST",
             {"Authorization": f"Bearer {ENV['OPENAI_API_KEY']}"},
             {"model": a.model, "input": [{"role": "user", "content": content}],
              "reasoning": {"effort": "low"},
              "text": {"format": {"type": "json_schema", "name": "facing", "strict": True, "schema": SCHEMA}},
              "max_output_tokens": 300, "store": False})
    text = r.get("output_text") or "".join(p.get("text", "") for it in r.get("output", []) if it.get("type") == "message"
                                          for p in it.get("content", []) if p.get("type") == "output_text")
    ans = json.loads(text)
    print(json.dumps({"flipped": ans["front_render"] == "B", "front_render": ans["front_render"],
                      "confidence": ans["confidence"], "cost_usd": token_cost(a.model, r.get("usage")),
                      "renders": out}))

if __name__ == "__main__":
    main()
