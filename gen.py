#!/usr/bin/env python3
"""OpenSmash generation pipeline — API front-ends.

Subcommands:
  text3d  <prompt> [--polycount N]      Meshy text-to-3D (preview mode) -> task id
  image   <prompt> <out.png> [--api openai|gemini]   T-pose sheet via image model
  img3d   <image.png> [--polycount N]   Meshy image-to-3D -> task id
  status  <task_id> [--kind text|image] Poll Meshy task
  download <task_id> <out.glb> [--kind text|image]   Fetch result GLB

Keys come from .env next to this script. State (task ids) is the caller's
problem — everything prints JSON to stdout.
"""
import argparse, base64, json, os, sys, time, urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))


def load_env():
    env = {}
    with open(os.path.join(ROOT, ".env")) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k] = v
    return env


ENV = load_env()


def http(url, method="GET", headers=None, body=None, timeout=180):
    req = urllib.request.Request(url, method=method)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, data, timeout=timeout) as r:
        return json.loads(r.read().decode())


MESHY = "https://api.meshy.ai/openapi"
MESHY_HDR = {"Authorization": f"Bearer {ENV['MESHY_API_KEY']}"}


def cmd_text3d(args):
    body = {
        "mode": "preview",
        "prompt": args.prompt,
        "art_style": "realistic",
        "topology": "triangle",
        "target_polycount": args.polycount,
        "should_remesh": True,
    }
    out = http(f"{MESHY}/v2/text-to-3d", "POST", MESHY_HDR, body)
    print(json.dumps(out))


def cmd_img3d(args):
    with open(args.image, "rb") as f:
        data_uri = "data:image/png;base64," + base64.b64encode(f.read()).decode()
    body = {
        "image_url": data_uri,
        "topology": "triangle",
        "target_polycount": args.polycount,
        "should_remesh": True,
        "should_texture": True,
        "enable_pbr": False,
    }
    out = http(f"{MESHY}/v1/image-to-3d", "POST", MESHY_HDR, body)
    print(json.dumps(out))


def meshy_task_url(task_id, kind):
    return (f"{MESHY}/v2/text-to-3d/{task_id}" if kind == "text"
            else f"{MESHY}/v1/image-to-3d/{task_id}")


def cmd_status(args):
    out = http(meshy_task_url(args.task_id, args.kind), "GET", MESHY_HDR)
    print(json.dumps({k: out.get(k) for k in
                      ("id", "status", "progress", "task_error", "model_urls", "thumbnail_url")}))


def cmd_download(args):
    out = http(meshy_task_url(args.task_id, args.kind), "GET", MESHY_HDR)
    url = (out.get("model_urls") or {}).get("glb")
    if not url:
        print(json.dumps({"error": "no glb url", "status": out.get("status")}))
        sys.exit(1)
    urllib.request.urlretrieve(url, args.out)
    print(json.dumps({"saved": args.out, "bytes": os.path.getsize(args.out)}))


def cmd_rig(args):
    with open(args.glb, "rb") as f:
        data_uri = ("data:model/gltf-binary;base64,"
                    + base64.b64encode(f.read()).decode())
    body = {"model_url": data_uri, "height_meters": args.height}
    out = http(f"{MESHY}/v1/rigging", "POST", MESHY_HDR, body, timeout=300)
    print(json.dumps(out))


def cmd_rigstatus(args):
    out = http(f"{MESHY}/v1/rigging/{args.task_id}", "GET", MESHY_HDR)
    print(json.dumps({k: out.get(k) for k in
                      ("id", "status", "progress", "task_error", "result")}))


def cmd_rigdownload(args):
    out = http(f"{MESHY}/v1/rigging/{args.task_id}", "GET", MESHY_HDR)
    url = (out.get("result") or {}).get("rigged_character_glb_url")
    if not url:
        print(json.dumps({"error": "no rigged glb url", "status": out.get("status")}))
        sys.exit(1)
    urllib.request.urlretrieve(url, args.out)
    print(json.dumps({"saved": args.out, "bytes": os.path.getsize(args.out)}))


def cmd_image(args):
    if args.api == "openai":
        out = http("https://api.openai.com/v1/images/generations", "POST",
                   {"Authorization": f"Bearer {ENV['OPENAI_API_KEY']}"},
                   {"model": args.model, "prompt": args.prompt, "size": "1024x1024"},
                   timeout=300)
        item = out["data"][0]
        if "b64_json" in item:
            png = base64.b64decode(item["b64_json"])
        else:
            png = urllib.request.urlopen(item["url"]).read()
    else:  # gemini
        out = http(
            f"https://generativelanguage.googleapis.com/v1beta/models/{args.model}:generateContent",
            "POST", {"x-goog-api-key": ENV["GEMINI_API_KEY"]},
            {"contents": [{"parts": [{"text": args.prompt}]}],
             "generationConfig": {"responseModalities": ["IMAGE"]}},
            timeout=300)
        parts = out["candidates"][0]["content"]["parts"]
        blob = next(p for p in parts if "inlineData" in p)["inlineData"]["data"]
        png = base64.b64decode(blob)
    with open(args.out, "wb") as f:
        f.write(png)
    print(json.dumps({"saved": args.out, "bytes": len(png)}))


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("text3d"); t.add_argument("prompt"); t.add_argument("--polycount", type=int, default=10000); t.set_defaults(fn=cmd_text3d)
    i = sub.add_parser("img3d"); i.add_argument("image"); i.add_argument("--polycount", type=int, default=10000); i.set_defaults(fn=cmd_img3d)
    s = sub.add_parser("status"); s.add_argument("task_id"); s.add_argument("--kind", default="text"); s.set_defaults(fn=cmd_status)
    d = sub.add_parser("download"); d.add_argument("task_id"); d.add_argument("out"); d.add_argument("--kind", default="text"); d.set_defaults(fn=cmd_download)
    m = sub.add_parser("image"); m.add_argument("prompt"); m.add_argument("out"); m.add_argument("--api", default="openai"); m.add_argument("--model", default="gpt-image-2"); m.set_defaults(fn=cmd_image)
    r = sub.add_parser("rig"); r.add_argument("glb"); r.add_argument("--height", type=float, default=1.7); r.set_defaults(fn=cmd_rig)
    rs = sub.add_parser("rigstatus"); rs.add_argument("task_id"); rs.set_defaults(fn=cmd_rigstatus)
    rd = sub.add_parser("rigdownload"); rd.add_argument("task_id"); rd.add_argument("out"); rd.set_defaults(fn=cmd_rigdownload)

    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
