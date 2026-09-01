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
import argparse, base64, json, os, sys, time, urllib.error, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_env():
    env = dict(os.environ)
    env_path = os.path.join(ROOT, ".env")
    if not os.path.isfile(env_path):
        return env
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env.setdefault(k, v)
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
    try:
        with urllib.request.urlopen(req, data, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        raise RuntimeError(f"HTTP {e.code} from {url}: {detail}") from e


# --- cost accounting --------------------------------------------------
# $ per 1M tokens as (text_in, image_in, output). Image models bill the
# generated image as OUTPUT tokens, so there is no fixed per-image price:
# gpt-image-2's default quality="auto" picks a tier per prompt (196 output
# tokens for a flat emblem, 439 for a T-pose sheet). Gemini bills thinking
# tokens as output. Rates checked 2026-08-26 against the published tables.
PRICES = {
    "gpt-5.6-luna":          (0.20,  0.20,   1.20),
    "gpt-image-2":            (5.00,  8.00,  30.00),
    "gpt-image-1.5":          (5.00,  8.00,  32.00),
    "gpt-image-1":            (5.00, 10.00,  40.00),
    "gpt-image-1-mini":       (2.00,  2.50,   8.00),
    "gemini-3.7-flash":       (0.75,  0.75,   3.75),
    "gemini-2.5-flash-image": (0.30,  0.30,  30.00),
    "gemini-3.1-flash-image": (0.50,  0.50,  60.00),
    "gemini-3-pro-image":     (2.00,  2.00, 120.00),
}
MODEL_ALIASES = {"gemini-flash-latest": "gemini-3.7-flash"}


def normalize_usage(usage):
    """(text_in, image_in, output) from an OpenAI or a Gemini usage blob."""
    if not usage:
        return 0, 0, 0
    if "input_tokens" in usage:                                    # OpenAI
        d = usage.get("input_tokens_details") or {}
        return (d.get("text_tokens", usage.get("input_tokens", 0)),
                d.get("image_tokens", 0), usage.get("output_tokens", 0))
    img = sum(p.get("tokenCount", 0)                               # Gemini
              for p in (usage.get("promptTokensDetails") or [])
              if p.get("modality") == "IMAGE")
    return (max(0, usage.get("promptTokenCount", 0) - img), img,
            usage.get("candidatesTokenCount", 0)
            + usage.get("thoughtsTokenCount", 0))


def token_cost(model, usage):
    """USD for one call, or None when we have no published rate to apply."""
    rate = PRICES.get(MODEL_ALIASES.get(model, model))
    if not rate or not usage:
        return None   # unknown model or no usage reported -> a gap, not $0
    t, i, o = normalize_usage(usage)
    return (t * rate[0] + i * rate[1] + o * rate[2]) / 1e6


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


def _refs(args):
    refs = list(getattr(args, "ref", None) or [])
    return [r for r in refs if r]


def _mime(path):
    p = path.lower()
    if p.endswith(".jpg") or p.endswith(".jpeg"):
        return "image/jpeg"
    if p.endswith(".webp"):
        return "image/webp"
    return "image/png"


def cmd_image(args):
    refs = _refs(args)
    if args.api == "openai":
        if refs:
            # images/edits with reference photos (multipart)
            import uuid
            boundary = uuid.uuid4().hex
            body = b""
            def field(name, value):
                return (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n").encode()
            body += field("model", args.model)
            body += field("prompt", args.prompt)
            body += field("size", "1024x1024")
            for r in refs:
                with open(r, "rb") as rf:
                    data = rf.read()
                body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"image[]\"; "
                         f"filename=\"{os.path.basename(r)}\"\r\nContent-Type: {_mime(r)}\r\n\r\n").encode()
                body += data + b"\r\n"
            body += f"--{boundary}--\r\n".encode()
            req = urllib.request.Request(
                "https://api.openai.com/v1/images/edits", body,
                {"Authorization": f"Bearer {ENV['OPENAI_API_KEY']}",
                 "Content-Type": f"multipart/form-data; boundary={boundary}"})
            try:
                with urllib.request.urlopen(req, timeout=300) as resp:
                    out = json.loads(resp.read())
            except urllib.error.HTTPError as e:
                detail = e.read().decode(errors="replace")
                raise RuntimeError(
                    f"HTTP {e.code} from images/edits: {detail}"
                ) from e
        else:
            out = http("https://api.openai.com/v1/images/generations", "POST",
                       {"Authorization": f"Bearer {ENV['OPENAI_API_KEY']}"},
                       {"model": args.model, "prompt": args.prompt, "size": "1024x1024"},
                       timeout=300)
        usage = out.get("usage")
        item = out["data"][0]
        if "b64_json" in item:
            png = base64.b64decode(item["b64_json"])
        else:
            png = urllib.request.urlopen(item["url"]).read()
    else:  # gemini
        parts = [{"text": args.prompt}]
        for r in refs:
            with open(r, "rb") as rf:
                parts.append({"inlineData": {"mimeType": _mime(r),
                              "data": base64.b64encode(rf.read()).decode()}})
        out = http(
            f"https://generativelanguage.googleapis.com/v1beta/models/{args.model}:generateContent",
            "POST", {"x-goog-api-key": ENV["GEMINI_API_KEY"]},
            {"contents": [{"parts": parts}],
             "generationConfig": {"responseModalities": ["IMAGE"]}},
            timeout=300)
        usage = out.get("usageMetadata")
        parts = out["candidates"][0]["content"]["parts"]
        blob = next(p for p in parts if "inlineData" in p)["inlineData"]["data"]
        png = base64.b64decode(blob)
    with open(args.out, "wb") as f:
        f.write(png)
    print(json.dumps({"saved": args.out, "bytes": len(png), "model": args.model,
                      "usage": usage, "cost_usd": token_cost(args.model, usage)}))


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("text3d"); t.add_argument("prompt"); t.add_argument("--polycount", type=int, default=10000); t.set_defaults(fn=cmd_text3d)
    i = sub.add_parser("img3d"); i.add_argument("image"); i.add_argument("--polycount", type=int, default=10000); i.set_defaults(fn=cmd_img3d)
    s = sub.add_parser("status"); s.add_argument("task_id"); s.add_argument("--kind", default="text"); s.set_defaults(fn=cmd_status)
    d = sub.add_parser("download"); d.add_argument("task_id"); d.add_argument("out"); d.add_argument("--kind", default="text"); d.set_defaults(fn=cmd_download)
    m = sub.add_parser("image"); m.add_argument("prompt"); m.add_argument("out"); m.add_argument("--api", default="openai"); m.add_argument("--model", default="gpt-image-2"); m.add_argument("--ref", action="append", default=None); m.set_defaults(fn=cmd_image)
    r = sub.add_parser("rig"); r.add_argument("glb"); r.add_argument("--height", type=float, default=1.7); r.set_defaults(fn=cmd_rig)
    rs = sub.add_parser("rigstatus"); rs.add_argument("task_id"); rs.set_defaults(fn=cmd_rigstatus)
    rd = sub.add_parser("rigdownload"); rd.add_argument("task_id"); rd.add_argument("out"); rd.set_defaults(fn=cmd_rigdownload)

    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
