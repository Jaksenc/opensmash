#!/usr/bin/env python3
"""Tripo3D API front-end (v2 openapi) — alternative to Meshy.

Subcommands:
  upload <image.png>                      -> image_token
  img3d <image_token> [--faces 4000]      image_to_model -> task id
  rig <model_task_id>                     animate_rig -> task id
  status <task_id>                        poll task
  download <task_id> <out.glb>            fetch model/rigged glb

Key from TRIPO_API_KEY in .env next to this script.
"""
import argparse
import json
import os
import subprocess
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEY = next(line.split("=", 1)[1].strip() for line in open(os.path.join(ROOT, ".env"))
           if line.startswith("TRIPO_API_KEY="))
BASE = "https://api.tripo3d.ai/v2/openapi"


def http(url, body=None):
    req = urllib.request.Request(url, method="POST" if body else "GET")
    req.add_header("Authorization", f"Bearer {KEY}")
    data = None
    if body is not None:
        req.add_header("Content-Type", "application/json")
        data = json.dumps(body).encode()
    with urllib.request.urlopen(req, data, timeout=180) as r:
        return json.loads(r.read().decode())


def cmd_upload(a):
    out = subprocess.run(
        ["curl", "-s", f"{BASE}/upload", "-H", f"Authorization: Bearer {KEY}",
         "-F", f"file=@{a.image}"], capture_output=True, text=True)
    print(out.stdout)


def cmd_img3d(a):
    body = {"type": "image_to_model",
            "file": {"type": "png", "file_token": a.image_token},
            "face_limit": a.faces, "texture": True}
    if a.model:
        body["model_version"] = a.model
    print(json.dumps(http(f"{BASE}/task", body)))


def cmd_rig(a):
    body = {"type": "animate_rig", "original_model_task_id": a.task_id,
            "out_format": "glb"}
    print(json.dumps(http(f"{BASE}/task", body)))


def cmd_balance(a):
    """Credit balance. Bracketing a task with this is the only way to see
    what Tripo actually charged — task payloads carry no cost field."""
    print(json.dumps(http(f"{BASE}/user/balance")["data"]))


def cmd_status(a):
    d = http(f"{BASE}/task/{a.task_id}")["data"]
    print(json.dumps({k: d.get(k) for k in
                      ("task_id", "type", "status", "progress", "output")})[:600])


def cmd_download(a):
    d = http(f"{BASE}/task/{a.task_id}")["data"]
    out = d.get("output") or {}
    url = out.get("model") or out.get("pbr_model") or out.get("base_model") or out.get("rigged_model")
    if not url:
        print(json.dumps({"error": "no model url", "output_keys": list(out.keys()),
                          "status": d.get("status")}))
        sys.exit(1)
    req = urllib.request.Request(url, headers={"User-Agent": "curl/8.0"})
    with urllib.request.urlopen(req, timeout=600) as r, open(a.out, "wb") as f:
        f.write(r.read())
    print(json.dumps({"saved": a.out, "bytes": os.path.getsize(a.out)}))


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    u = sub.add_parser("upload"); u.add_argument("image"); u.set_defaults(fn=cmd_upload)
    i = sub.add_parser("img3d"); i.add_argument("image_token"); i.add_argument("--faces", type=int, default=4000); i.add_argument("--model", default="v3.0-20250812"); i.set_defaults(fn=cmd_img3d)
    r = sub.add_parser("rig"); r.add_argument("task_id"); r.set_defaults(fn=cmd_rig)
    s = sub.add_parser("status"); s.add_argument("task_id"); s.set_defaults(fn=cmd_status)
    d = sub.add_parser("download"); d.add_argument("task_id"); d.add_argument("out"); d.set_defaults(fn=cmd_download)
    b = sub.add_parser("balance"); b.set_defaults(fn=cmd_balance)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
