#!/usr/bin/env python3
"""Does each character's t-pose depict the roster entry (name + CSV section)?
Catches the expander picking a namesake (Michelangelo -> turtle, Butterbean -> fairy).
--sweep -> artifacts/batch-1000/depiction-sweep.jsonl"""
import base64, csv, json, os, re, sys
sys.path.insert(0, "pipeline")
from gen import http, ENV, token_cost
SCHEMA = {"type": "object", "properties": {
    "matches": {"type": "boolean"}, "shows": {"type": "string"}, "confidence": {"type": "string", "enum": ["high", "medium", "low"]}},
    "required": ["matches", "shows", "confidence"], "additionalProperties": False}
d = lambda p: "data:image/png;base64," + base64.b64encode(open(p, "rb").read()).decode()
def check(name, section, tpose, model="gpt-5.6-luna"):
    prompt = (f"This low-poly toy model sheet was generated for the roster entry \"{name}\" in the category "
              f"\"{section}\". Does it depict THAT person or character (the one the category implies), rather than "
              f"a different namesake, a different franchise's character, or a generic figure? Likeness is stylised "
              f"and chibi, so judge by identity cues: era, outfit, hair, build, props, species. Say briefly what it shows.")
    r = http("https://api.openai.com/v1/responses", "POST", {"Authorization": f"Bearer {ENV['OPENAI_API_KEY']}"},
             {"model": model, "input": [{"role": "user", "content": [{"type": "input_text", "text": prompt},
                                                                     {"type": "input_image", "image_url": d(tpose)}]}],
              "reasoning": {"effort": "low"},
              "text": {"format": {"type": "json_schema", "name": "depiction", "strict": True, "schema": SCHEMA}},
              "max_output_tokens": 2000, "store": False})
    if r.get("status") == "incomplete":
        raise RuntimeError(f"model response incomplete ({r.get('incomplete_details')}) — no verdict")
    text = r.get("output_text") or "".join(p.get("text", "") for it in r.get("output", []) if it.get("type") == "message"
                                          for p in it.get("content", []) if p.get("type") == "output_text")
    out = json.loads(text); out["cost_usd"] = token_cost(model, r.get("usage")); return out
if __name__ == "__main__":
    slug = lambda n: re.sub(r"[^a-z0-9]", "", n.lower())[:16]
    rows = [r for r in csv.DictReader(open("config/seed-roster/seed-roster.csv")) if r["tier"].strip() in ("S", "A")]
    from concurrent.futures import ThreadPoolExecutor
    out = open("artifacts/batch-1000/depiction-sweep.jsonl", "a")
    def one(r):
        s = slug(r["name"]); p = f"play/ui/{s}/tpose.png"
        if not os.path.exists(p): return None
        try: v = check(r["name"], r["section"], p)
        except Exception as e: v = {"matches": None, "shows": "error " + str(e)[-100:]}
        v.update(slug=s, name=r["name"], section=r["section"]); return v
    with ThreadPoolExecutor(8) as ex:
        for v in ex.map(one, rows):
            if not v: continue
            out.write(json.dumps(v) + "\n"); out.flush()
            if v.get("matches") is not True: print(v["slug"], v.get("matches"), v.get("confidence", ""), "-", v.get("shows", "")[:90], flush=True)
    print("depiction sweep done", flush=True)
