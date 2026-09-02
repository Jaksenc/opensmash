#!/usr/bin/env python3
"""Mesh-sanity check: is the converted model a coherent figure that matches its
t-pose, or a collapsed/shredded mesh (Daft Punk's first Tripo rig)?
  mesh_check.py <tpose.png> <render.png>  -> JSON {"broken": bool, "issue": ..., "confidence": ...}
Reuses the facing sweep's yaw renders when run as a sweep (--sweep)."""
import base64, json, os, sys
sys.path.insert(0, "pipeline")
from gen import http, ENV, token_cost
SCHEMA = {"type": "object", "properties": {
    "verdict": {"type": "string", "enum": ["ok", "minor_defects", "broken"]},
    "issue": {"type": "string"}, "confidence": {"type": "string", "enum": ["high", "medium", "low"]}},
    "required": ["verdict", "issue", "confidence"], "additionalProperties": False}
PROMPT = ("Image 1 is a character's reference model sheet. Image 2 is a software render of that character's "
          "converted low-poly game mesh (low detail and a different pose or viewing angle are normal; the "
          "texture is coarse; the view may even show the character's back). Judge only whether the MESH is "
          "structurally intact: 'ok' if the body, head and limbs are recognisably the same figure; "
          "'minor_defects' for small tears, a stretched hand or a thin spike; 'broken' if the head or body "
          "is a collapsed/crumpled blob, limbs are missing, the figure is shredded into fragments, or it "
          "does not resemble the reference figure at all. Check explicitly: are two arms and two legs present "
          "(hidden by the pose is fine, absent is not)? Is the head roughly the reference's proportion, or a "
          "crumpled oversized lump? Are the torso and clothing continuous surfaces, or jagged fragments? "
          "Jagged fragments plus a missing limb is 'broken', not minor. One short phrase in 'issue'.")
d = lambda p: "data:image/png;base64," + base64.b64encode(open(p, "rb").read()).decode()
def check(tpose, render, model="gpt-5.6-luna"):
    r = http("https://api.openai.com/v1/responses", "POST", {"Authorization": f"Bearer {ENV['OPENAI_API_KEY']}"},
             {"model": model, "input": [{"role": "user", "content": [
                 {"type": "input_text", "text": PROMPT}, {"type": "input_image", "image_url": d(tpose)},
                 {"type": "input_image", "image_url": d(render)}]}],
              "reasoning": {"effort": "medium"},
              "text": {"format": {"type": "json_schema", "name": "mesh", "strict": True, "schema": SCHEMA}},
              "max_output_tokens": 2000, "store": False})
    if r.get("status") == "incomplete":
        raise RuntimeError(f"model response incomplete ({r.get('incomplete_details')}) — no verdict")
    text = r.get("output_text") or "".join(p.get("text", "") for it in r.get("output", []) if it.get("type") == "message"
                                          for p in it.get("content", []) if p.get("type") == "output_text")
    out = json.loads(text); out["cost_usd"] = token_cost(model, r.get("usage")); return out
if __name__ == "__main__":
    if sys.argv[1] == "--sweep":
        from concurrent.futures import ThreadPoolExecutor
        rows = [json.loads(l) for l in open("artifacts/batch-1000/facing-sweep.jsonl")]
        rows = [r for r in rows if r.get("renders") and os.path.exists(os.path.join(r["renders"], "yaw0.png"))]
        out = open("artifacts/batch-1000/mesh-sweep.jsonl", "a")
        def one(r):
            s = r["slug"]
            try:
                v = check(f"play/ui/{s}/tpose.png", os.path.join(r["renders"], "yaw180.png" if r.get("flipped") else "yaw0.png"))
            except Exception as e:
                v = {"verdict": "error", "issue": str(e)[-120:]}
            v["slug"] = s; return v
        with ThreadPoolExecutor(8) as ex:
            for v in ex.map(one, rows):
                out.write(json.dumps(v) + "\n"); out.flush()
                if v["verdict"] != "ok": print(v["slug"], v["verdict"], v.get("confidence", ""), "-", v.get("issue", "")[:80], flush=True)
        print("mesh sweep done", flush=True)
    else:
        print(json.dumps(check(sys.argv[1], sys.argv[2])))
