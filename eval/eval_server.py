#!/usr/bin/env python3
"""Serve the A/B rating UI and record ratings.

  python3 eval/eval_server.py [--port 8765] [--rater tom]

GET  /              rating UI
GET  /pairs.json    comparison schedule (technique ids stripped)
GET  /cells/...     clips and sheets
POST /rate          {"id": N, "choice": "left"|"right"|"tie", "ms": elapsed}
GET  /progress      rated ids for this rater
Ratings append to eval/ratings.jsonl (one JSON per line, with the hidden
left/right technique ids resolved server-side).
"""
import argparse
import json
import os
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
RATINGS = os.path.join(HERE, "ratings.jsonl")
RATER = "anon"


def rated_ids(rater):
    ids = set()
    if os.path.exists(RATINGS):
        for line in open(RATINGS):
            try:
                r = json.loads(line)
                if r.get("rater") == rater:
                    ids.add(r["id"])
            except Exception:
                pass
    return ids


class H(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=HERE, **k)

    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path == "/":
            self.path = "/ui/index.html"
        elif self.path.startswith("/pairs.json"):
            pairs = json.load(open(os.path.join(HERE, "pairs.json")))
            pub = [{"id": p["id"], "char": p["char"], "display": p["display"],
                    "left_clip": f"/cells/{p['char']}-{p['left']}/clip.mp4",
                    "right_clip": f"/cells/{p['char']}-{p['right']}/clip.mp4",
                    "left_sheet": f"/cells/{p['char']}-{p['left']}/sheet.png",
                    "right_sheet": f"/cells/{p['char']}-{p['right']}/sheet.png"} for p in pairs]
            return self._json(pub)
        elif self.path.startswith("/progress"):
            return self._json({"rated": sorted(rated_ids(RATER)), "rater": RATER})
        return super().do_GET()

    def do_POST(self):
        if self.path != "/rate":
            return self._json({"error": "nope"}, 404)
        n = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(n))
        pairs = {p["id"]: p for p in json.load(open(os.path.join(HERE, "pairs.json")))}
        p = pairs[body["id"]]
        rec = {"id": p["id"], "char": p["char"], "left": p["left"], "right": p["right"],
               "choice": body["choice"], "ms": body.get("ms"), "rater": RATER, "t": time.time()}
        with open(RATINGS, "a") as f:
            f.write(json.dumps(rec) + "\n")
        return self._json({"ok": True})


def main():
    global RATER
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--rater", default="tom")
    a = ap.parse_args()
    RATER = a.rater
    print(f"rating UI: http://localhost:{a.port}/  (rater={RATER})")
    ThreadingHTTPServer(("0.0.0.0", a.port), H).serve_forever()


if __name__ == "__main__":
    main()
