#!/usr/bin/env python3
"""Grade final displayed glyph rasterization against a source crop.

The score is intentionally independent of the glyph's exact scale and color.
It isolates the largest interior neutral glyph, measures its antialias transition
width and framebuffer-frequency energy, then compares those style signatures.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image


def neutral_mask(rgb: np.ndarray) -> np.ndarray:
    red, green, blue = (rgb[..., index] for index in range(3))
    luminance = rgb.mean(axis=2)
    return (
        (luminance > 38)
        & (np.abs(red - green) < 42)
        & (blue > red * 0.45)
    )


def components(mask: np.ndarray) -> list[list[tuple[int, int]]]:
    height, width = mask.shape
    seen = np.zeros_like(mask, dtype=bool)
    found: list[list[tuple[int, int]]] = []
    for start_y, start_x in zip(*np.where(mask)):
        if seen[start_y, start_x]:
            continue
        queue = deque([(int(start_y), int(start_x))])
        seen[start_y, start_x] = True
        points: list[tuple[int, int]] = []
        while queue:
            y, x = queue.popleft()
            points.append((y, x))
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ny, nx = y + dy, x + dx
                if (
                    0 <= ny < height
                    and 0 <= nx < width
                    and mask[ny, nx]
                    and not seen[ny, nx]
                ):
                    seen[ny, nx] = True
                    queue.append((ny, nx))
        found.append(points)
    return found


def isolate_glyph(path: Path) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    rgb = np.asarray(Image.open(path).convert("RGB"), dtype=np.float64)
    height, width = rgb.shape[:2]
    mask = neutral_mask(rgb)
    mask[:, : min(12, width)] = False

    candidates = []
    for points in components(mask):
        if len(points) < 200:
            continue
        ys = [point[0] for point in points]
        xs = [point[1] for point in points]
        box = (min(xs), min(ys), max(xs) + 1, max(ys) + 1)
        box_width = box[2] - box[0]
        box_height = box[3] - box[1]
        if box[2] >= width - 1 or box_height < height * 0.35:
            continue
        aspect = box_width / box_height
        if not 0.45 <= aspect <= 1.05:
            continue
        candidates.append((len(points), box))

    if not candidates:
        raise ValueError(f"could not isolate an interior glyph in {path}")

    _, (x0, y0, x1, y1) = max(candidates)
    pad = 4
    x0, y0 = max(0, x0 - pad), max(0, y0 - pad)
    x1, y1 = min(width, x1 + pad), min(height, y1 + pad)
    return rgb[y0:y1, x0:x1], (x0, y0, x1, y1)


def style_metrics(rgb: np.ndarray) -> dict[str, float]:
    red, green, blue = (rgb[..., index] for index in range(3))
    luminance = rgb.mean(axis=2)
    chroma = np.maximum.reduce((red, green, blue)) - np.minimum.reduce((red, green, blue))
    neutrality = np.clip(1 - chroma / 95, 0, 1)
    floor = float(np.percentile(luminance, 10))
    neutral_values = luminance[neutrality > 0.5]
    ceiling = float(np.percentile(neutral_values, 98))
    ink = np.clip((luminance - floor) / max(ceiling - floor, 1e-6), 0, 1)
    ink *= np.sqrt(neutrality)

    high = ink > 0.68
    low = ink > 0.12
    eroded = high.copy()
    eroded[1:-1, 1:-1] &= (
        high[:-2, 1:-1]
        & high[2:, 1:-1]
        & high[1:-1, :-2]
        & high[1:-1, 2:]
    )
    perimeter = max(int(np.count_nonzero(high & ~eroded)), 1)
    edge_width = float((np.count_nonzero(low) - np.count_nonzero(high)) / perimeter)

    grad_x = np.diff(ink, axis=1)
    grad_y = np.diff(ink, axis=0)
    gradients = np.concatenate((np.abs(grad_x).ravel(), np.abs(grad_y).ravel()))
    laplacian = np.zeros_like(ink)
    laplacian[1:-1, 1:-1] = (
        4 * ink[1:-1, 1:-1]
        - ink[:-2, 1:-1]
        - ink[2:, 1:-1]
        - ink[1:-1, :-2]
        - ink[1:-1, 2:]
    )

    return {
        "width": float(rgb.shape[1]),
        "height": float(rgb.shape[0]),
        "edge_width": edge_width,
        "gradient_p98": float(np.percentile(gradients, 98)),
        "laplacian_rms": float(np.sqrt(np.mean(laplacian**2))),
        "transition_fraction": float(np.mean((ink > 0.08) & (ink < 0.92))),
    }


WEIGHTS = {
    "width": 0.05,
    "height": 0.05,
    "edge_width": 0.25,
    "gradient_p98": 0.20,
    "laplacian_rms": 0.35,
    "transition_fraction": 0.10,
}


def similarity(source: float, replica: float) -> float:
    if source <= 0 or replica <= 0:
        return float(source == replica)
    return math.exp(-2.3 * abs(math.log(replica / source)))


def grade(source_path: Path, replica_path: Path) -> dict[str, object]:
    source_rgb, source_box = isolate_glyph(source_path)
    replica_rgb, replica_box = isolate_glyph(replica_path)
    source = style_metrics(source_rgb)
    replica = style_metrics(replica_rgb)
    metric_scores = {
        name: 100 * similarity(source[name], replica[name]) for name in WEIGHTS
    }
    score = sum(metric_scores[name] * weight for name, weight in WEIGHTS.items())
    return {
        "score": score,
        "source_box": source_box,
        "replica_box": replica_box,
        "source": source,
        "replica": replica,
        "metric_scores": metric_scores,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("replica", type=Path)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--minimum", type=float, default=95.0)
    args = parser.parse_args()
    result = grade(args.source, args.replica)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"pixel-style score: {result['score']:.3f}%")
        for name in WEIGHTS:
            source = result["source"][name]
            replica = result["replica"][name]
            score = result["metric_scores"][name]
            print(f"{name:20} source={source:9.5f} replica={replica:9.5f} match={score:7.3f}%")
    if result["score"] < args.minimum:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
