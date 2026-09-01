#!/usr/bin/env python3
"""Convert a generated GLB and capture it in BattleShip's item lab.

This is the short asset-iteration loop: one command converts the mesh, boots
a deterministic match with random items disabled, spawns the replacement bat
immediately, and captures a PNG. ``--mode hold`` tests the attachment grip;
``--mode ground`` tests the free item pose. ``--action attack`` taps A five
frames before capture to exercise the real held-item swing path.

Example:
  python3 pipeline/preview_item.py prop.glb artifacts/prop-preview \
    --axis y --roll 0 --length 420 --hold-point auto --mode hold
"""

import argparse
import os
import subprocess
import sys


PIPELINE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKSPACE_ROOT = os.path.dirname(PIPELINE_ROOT)
DEFAULT_BUILD = os.path.join(WORKSPACE_ROOT, "BattleShip", "build-us")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="one-mesh, one-primitive generated GLB")
    parser.add_argument("out_dir", help="directory for item.osb and preview PNG")
    parser.add_argument("--mode", choices=("ground", "hold"), default="hold")
    parser.add_argument("--action", choices=("idle", "attack"), default="idle")
    parser.add_argument("--axis", choices=("x", "y", "z"), default="y")
    parser.add_argument("--target-axis", choices=("x", "y", "z"), default="y")
    parser.add_argument("--roll", type=float, default=0.0,
                        help="degrees to rotate around the item length axis")
    parser.add_argument("--flip", action="store_true")
    parser.add_argument("--length", type=float, default=420.0)
    hold_group = parser.add_mutually_exclusive_group()
    hold_group.add_argument("--hold-point", choices=("auto", "base", "center", "tip"),
                            default="auto")
    hold_group.add_argument("--hold-position", type=float, nargs=3,
                            metavar=("X", "Y", "Z"))
    hold_group.add_argument("--pivot", choices=("base", "center", "tip"),
                            help="legacy alias for --hold-point")
    parser.add_argument("--hold-inset", type=float, default=0.06)
    parser.add_argument("--offset-x", type=float, default=0.0,
                        help="game-space X grip offset applied after scaling")
    parser.add_argument("--offset-y", type=float, default=0.0,
                        help="game-space Y grip offset applied after scaling")
    parser.add_argument("--offset-z", type=float, default=0.0,
                        help="game-space Z grip offset applied after scaling")
    parser.add_argument("--max-tris", type=int, default=2000)
    parser.add_argument("--shading", choices=("vertex", "textured-lit"), default="vertex")
    parser.add_argument("--texture-size", type=int, default=64)
    parser.add_argument("--frame", type=int, default=500,
                        help="absolute game frame to capture (500 is post-spawn)")
    parser.add_argument("--stage", type=int, default=6, help="stage kind; 6 is Dream Land")
    parser.add_argument("--build", default=os.environ.get("ITEM_PREVIEW_BUILD", DEFAULT_BUILD))
    parser.add_argument("--no-run", action="store_true", help="convert only")
    args = parser.parse_args()
    if args.action == "attack" and (args.mode != "hold" or args.frame < 6):
        parser.error("--action attack requires --mode hold and --frame >= 6")

    input_path = os.path.abspath(args.input)
    out_dir = os.path.abspath(args.out_dir)
    shots_dir = os.path.join(out_dir, "shots")
    bundle_path = os.path.join(out_dir, "item.osb")
    os.makedirs(shots_dir, exist_ok=True)

    convert_cmd = [
        sys.executable,
        os.path.join(PIPELINE_ROOT, "pipeline", "convert_item.py"),
        input_path,
        bundle_path,
        "--axis", args.axis,
        "--target-axis", args.target_axis,
        "--roll", str(args.roll),
        "--length", str(args.length),
        "--offset-x", str(args.offset_x),
        "--offset-y", str(args.offset_y),
        "--offset-z", str(args.offset_z),
        "--max-tris", str(args.max_tris),
        "--shading", args.shading,
        "--texture-size", str(args.texture_size),
    ]
    if args.hold_position is not None:
        convert_cmd += ["--hold-position", *[str(value) for value in args.hold_position]]
    elif args.pivot is not None:
        convert_cmd += ["--pivot", args.pivot]
    else:
        convert_cmd += ["--hold-point", args.hold_point,
                        "--hold-inset", str(args.hold_inset)]
    if args.flip:
        convert_cmd.append("--flip")
    subprocess.run(convert_cmd, check=True)

    if args.no_run:
        return

    executable = os.path.join(os.path.abspath(args.build), "BattleShip")
    if not os.path.isfile(executable):
        parser.error(f"BattleShip executable not found: {executable}")

    env = dict(os.environ)
    env.update({
        # Two human slots disable random items; ITEM_PREVIEW is the only item.
        "SSB64_BOOT_BATTLE": f"0,8,{args.stage},0",
        "SSB64_FORCE_ITEM_KIND": "8",
        "SSB64_ITEM_PREVIEW": args.mode,
        "SSB64_INJECT_ITEM_BAT": bundle_path,
        "SSB64_SCREENSHOT_FRAMES": str(args.frame),
        "SSB64_SCREENSHOT_DIR": shots_dir,
        "SSB64_MAX_FRAMES": str(args.frame + 20),
        "SSB64_MUTE": "1",
        "SSB64_LOG_CONSOLE": "1",
    })
    if args.action == "attack":
        pad_path = os.path.join(out_dir, "attack.pad")
        with open(pad_path, "w", encoding="utf-8") as pad_file:
            pad_file.write(
                "# Tap A shortly before the requested capture frame.\n"
                f"{args.frame - 5} {args.frame - 3} 8000 0 0\n"
            )
        env["SSB64_PAD_SCRIPT"] = pad_path
    result = subprocess.run(
        [executable], cwd=os.path.dirname(executable), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        check=True,
    )
    item_lines = [
        line for line in result.stdout.splitlines()
        if ("ITEMOSB:" in line) or ("ITEMLAB:" in line)
    ]
    if not any("ITEMLAB: spawned" in line for line in item_lines):
        raise RuntimeError("item lab did not report a successful spawn")

    shot_path = os.path.join(shots_dir, f"frame_{args.frame}.png")
    if not os.path.isfile(shot_path):
        raise RuntimeError(f"preview screenshot was not created: {shot_path}")
    for line in item_lines:
        print(line)
    print(f"preview: {shot_path} (action={args.action})")


if __name__ == "__main__":
    main()
