#!/usr/bin/env python3
"""Generate novel, perfectly periodic stone tiles in the Smash 64 CSS style.

The generator never copies source pixels. It learns only the reference tile's
palette, histogram, and structural statistics, builds candidates from periodic
Fourier fields, then keeps the closest-scoring candidate.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REFERENCE = ROOT / "stone-tile-investigation/source-stone-tile.png"
DEFAULT_OUTPUT = Path(__file__).resolve().parent / "generated"
DEFAULT_PALETTE = np.array([0, 8, 16, 24, 33, 41, 49, 57], dtype=np.uint8)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=64, help="master seed")
    parser.add_argument(
        "--candidates",
        type=int,
        default=128,
        help="deterministic candidates to rank against the reference",
    )
    parser.add_argument("--width", type=int, default=64)
    parser.add_argument("--height", type=int, default=32)
    parser.add_argument("--scale", type=int, default=8, help="preview pixel scale")
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--name", default="procedural-stone")
    return parser.parse_args()


def load_grayscale(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
    if not np.array_equal(rgb[:, :, 0], rgb[:, :, 1]) or not np.array_equal(
        rgb[:, :, 1], rgb[:, :, 2]
    ):
        raise ValueError(f"reference must be grayscale: {path}")
    return rgb[:, :, 0]


def palette_model(reference: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    palette, counts = np.unique(reference, return_counts=True)
    probabilities = counts.astype(np.float64) / counts.sum()
    return palette.astype(np.uint8), probabilities


def periodic_noise(
    rng: np.random.Generator,
    height: int,
    width: int,
    cutoff_x: float,
    cutoff_y: float,
) -> np.ndarray:
    """Return seamless anisotropic noise synthesized directly on a torus."""
    white = rng.normal(size=(height, width))
    spectrum = np.fft.fft2(white)
    frequency_x = np.fft.fftfreq(width)[None, :]
    frequency_y = np.fft.fftfreq(height)[:, None]
    low_pass = np.exp(
        -0.5
        * (
            (frequency_x / cutoff_x) ** 2
            + (frequency_y / cutoff_y) ** 2
        )
    )
    noise = np.fft.ifft2(spectrum * low_pass).real
    return (noise - noise.mean()) / (noise.std() + 1e-12)


def histogram_quantize(
    field: np.ndarray,
    palette: np.ndarray,
    probabilities: np.ndarray,
) -> np.ndarray:
    """Quantize while preserving the source palette distribution exactly."""
    flat = field.ravel()
    order = np.argsort(flat, kind="stable")
    indices = np.empty(flat.size, dtype=np.uint8)
    counts = np.floor(probabilities * flat.size).astype(int)
    remainder = flat.size - int(counts.sum())
    # Put rounding residue into the dominant midtone, as the source does.
    counts[int(np.argmax(probabilities))] += remainder

    start = 0
    for palette_index, count in enumerate(counts):
        indices[order[start : start + count]] = palette_index
        start += count
    return palette[indices.reshape(field.shape)]


def periodic_chisels(
    rng: np.random.Generator,
    height: int,
    width: int,
) -> tuple[np.ndarray, int]:
    """Build a few broad, beveled cuts that wrap across both tile axes."""
    x = np.arange(width, dtype=np.float64)[None, :]
    y = np.arange(height, dtype=np.float64)[:, None]
    output = np.zeros((height, width), dtype=np.float64)
    stroke_count = int(rng.integers(6, 10))
    for _ in range(stroke_count):
        center_x = rng.uniform(0, width)
        center_y = rng.uniform(0, height)
        radius_x = rng.uniform(5.0, 12.0) * (width / 64)
        radius_y = rng.uniform(1.2, 2.8) * (height / 32)
        slope = rng.uniform(-0.05, 0.05)
        depth = rng.uniform(0.7, 1.45)
        dx = (x - center_x + width * 1.5) % width - width / 2
        local_center_y = center_y + slope * dx
        dy = (y - local_center_y + height * 1.5) % height - height / 2
        shape = (np.abs(dx) / radius_x) ** 4 + (dy / radius_y) ** 2
        mask = shape < 1
        output[mask] -= depth * (0.58 + 0.42 * (1 - shape[mask]))
    return output, stroke_count


def periodic_plates(
    rng: np.random.Generator,
    height: int,
    width: int,
) -> tuple[np.ndarray, int]:
    """Build broad, nearly horizontal stone faces on the same torus."""
    x = np.arange(width, dtype=np.float64)[None, :]
    y = np.arange(height, dtype=np.float64)[:, None]
    output = np.zeros((height, width), dtype=np.float64)
    plate_count = int(rng.integers(4, 8))
    for _ in range(plate_count):
        center_x = rng.uniform(0, width)
        center_y = rng.uniform(0, height)
        radius_x = rng.uniform(7.0, 17.0) * (width / 64)
        radius_y = rng.uniform(2.5, 6.0) * (height / 32)
        slope = rng.uniform(-0.045, 0.045)
        raised = rng.uniform(0.55, 1.15)
        dx = (x - center_x + width * 1.5) % width - width / 2
        local_center_y = center_y + slope * dx
        dy = (y - local_center_y + height * 1.5) % height - height / 2
        shape = (np.abs(dx) / radius_x) ** 4 + (np.abs(dy) / radius_y) ** 4
        mask = shape < 1
        output[mask] += raised * (0.46 + 0.54 * (1 - shape[mask]))
    return output, plate_count


def generate_candidate(
    seed: int,
    width: int,
    height: int,
    palette: np.ndarray,
    probabilities: np.ndarray,
) -> tuple[np.ndarray, dict[str, float]]:
    """Generate one novel tile from periodic fields and directional lighting."""
    rng = np.random.default_rng(seed)

    broad = periodic_noise(
        rng,
        height,
        width,
        rng.uniform(0.018, 0.032),
        rng.uniform(0.040, 0.070),
    )
    strata = periodic_noise(
        rng,
        height,
        width,
        rng.uniform(0.030, 0.055),
        rng.uniform(0.130, 0.220),
    )
    detail = periodic_noise(
        rng,
        height,
        width,
        rng.uniform(0.100, 0.170),
        rng.uniform(0.220, 0.340),
    )
    warp = periodic_noise(
        rng,
        height,
        width,
        rng.uniform(0.015, 0.028),
        rng.uniform(0.045, 0.080),
    )
    chisels, chisel_count = periodic_chisels(rng, height, width)
    plates, plate_count = periodic_plates(rng, height, width)

    y = np.arange(height, dtype=np.float64)[:, None]
    course_size = rng.uniform(8.0, 12.0) * (height / 32)
    fine_course_size = rng.uniform(5.5, 7.5) * (height / 32)
    bands = np.sin(2 * np.pi * (y / course_size + rng.uniform(0.08, 0.15) * warp))
    bands += rng.uniform(0.18, 0.32) * np.sin(
        2
        * np.pi
        * (y / fine_course_size + rng.uniform(0.03, 0.08) * warp + rng.uniform(0, 2))
    )

    detail_weight = rng.uniform(0.12, 0.20)
    chisel_weight = rng.uniform(0.80, 1.10)
    plate_weight = rng.uniform(0.65, 0.90)
    field = (
        rng.uniform(0.06, 0.12) * broad
        + rng.uniform(0.12, 0.22) * strata
        + detail_weight * detail
        + chisel_weight * chisels
        + plate_weight * plates
        + rng.uniform(0.03, 0.08) * bands
    )

    # A top-biased relief pass produces the source tile's thin ledges and
    # deep undercuts. np.roll is periodic, so no edge receives special cases.
    light_y = rng.uniform(4.50, 6.50)
    light_x = rng.uniform(0.04, 0.11)
    shaded = field.copy()
    shaded += light_y * (
        np.roll(field, 1, axis=0) - np.roll(field, -1, axis=0)
    )
    shaded += light_x * (
        np.roll(field, 1, axis=1) - np.roll(field, -1, axis=1)
    )

    tile = histogram_quantize(shaded, palette, probabilities)
    parameters = {
        "course_size": float(course_size),
        "fine_course_size": float(fine_course_size),
        "detail_weight": float(detail_weight),
        "chisel_count": float(chisel_count),
        "chisel_weight": float(chisel_weight),
        "plate_count": float(plate_count),
        "plate_weight": float(plate_weight),
        "light_y": float(light_y),
        "light_x": float(light_x),
    }
    return tile, parameters


def mean_run_length(array: np.ndarray, transpose: bool = False) -> float:
    lines = array.T if transpose else array
    lengths: list[int] = []
    for line in lines:
        start = 0
        for index in range(1, len(line) + 1):
            if index == len(line) or line[index] != line[start]:
                lengths.append(index - start)
                start = index
    return float(np.mean(lengths))


def neighbor_correlation(array: np.ndarray, axis: int) -> float:
    left = array.astype(np.float64).ravel()
    right = np.roll(array, -1, axis=axis).astype(np.float64).ravel()
    if left.std() == 0 or right.std() == 0:
        return 0.0
    return float(np.corrcoef(left, right)[0, 1])


def texture_metrics(array: np.ndarray, palette: np.ndarray) -> dict[str, Any]:
    values = array.astype(np.float64)
    dx = np.abs(np.diff(values, axis=1))
    dy = np.abs(np.diff(values, axis=0))
    wrap_x = np.abs(values[:, 0] - values[:, -1])
    wrap_y = np.abs(values[0] - values[-1])
    histogram = {
        str(int(tone)): float(np.mean(array == tone)) for tone in palette
    }
    return {
        "mean": float(values.mean()),
        "std": float(values.std()),
        "dark_fraction": float(np.mean(values <= 16)),
        "highlight_fraction": float(np.mean(values >= 33)),
        "horizontal_transition_mean": float(dx.mean()),
        "vertical_transition_mean": float(dy.mean()),
        "horizontal_transition_nonzero": float(np.mean(dx > 0)),
        "vertical_transition_nonzero": float(np.mean(dy > 0)),
        "horizontal_transition_strong": float(np.mean(dx >= 16)),
        "vertical_transition_strong": float(np.mean(dy >= 16)),
        "row_run_mean": mean_run_length(array),
        "column_run_mean": mean_run_length(array, transpose=True),
        "horizontal_neighbor_correlation": neighbor_correlation(array, 1),
        "vertical_neighbor_correlation": neighbor_correlation(array, 0),
        "wrap_x_transition_mean": float(wrap_x.mean()),
        "wrap_y_transition_mean": float(wrap_y.mean()),
        "histogram": histogram,
    }


def similarity_unit(value: float, target: float, scale: float) -> float:
    return math.exp(-abs(value - target) / max(scale, 1e-9))


def style_similarity(
    candidate: dict[str, Any],
    reference: dict[str, Any],
    palette: np.ndarray,
) -> tuple[float, dict[str, float]]:
    specifications = {
        "mean": (1.0, 3.0),
        "std": (1.0, 3.0),
        "dark_fraction": (1.0, 0.06),
        "highlight_fraction": (1.0, 0.05),
        "horizontal_transition_mean": (2.0, 1.8),
        "vertical_transition_mean": (2.0, 3.0),
        "horizontal_transition_nonzero": (1.5, 0.10),
        "vertical_transition_nonzero": (1.5, 0.10),
        "horizontal_transition_strong": (1.5, 0.07),
        "vertical_transition_strong": (1.5, 0.09),
        "row_run_mean": (1.5, 0.75),
        "column_run_mean": (1.5, 0.40),
        "horizontal_neighbor_correlation": (1.0, 0.12),
        "vertical_neighbor_correlation": (1.0, 0.12),
    }
    parts: dict[str, float] = {}
    weighted_sum = 0.0
    weight_sum = 0.0
    for name, (weight, scale) in specifications.items():
        part = similarity_unit(candidate[name], reference[name], scale)
        parts[name] = 100 * part
        weighted_sum += weight * part
        weight_sum += weight

    candidate_hist = np.array(
        [candidate["histogram"].get(str(int(tone)), 0.0) for tone in palette]
    )
    reference_hist = np.array(
        [reference["histogram"].get(str(int(tone)), 0.0) for tone in palette]
    )
    histogram_score = max(0.0, 1.0 - 0.5 * float(np.abs(candidate_hist - reference_hist).sum()))
    parts["palette_histogram"] = 100 * histogram_score
    weighted_sum += 3.0 * histogram_score
    weight_sum += 3.0
    return 100 * weighted_sum / weight_sum, parts


def seam_quality(array: np.ndarray) -> tuple[float, dict[str, float | bool]]:
    values = array.astype(np.float64)
    internal_x = np.abs(np.diff(values, axis=1)).mean(axis=0)
    internal_y = np.abs(np.diff(values, axis=0)).mean(axis=1)
    boundary_x = float(np.abs(values[:, 0] - values[:, -1]).mean())
    boundary_y = float(np.abs(values[0] - values[-1]).mean())
    limit_x = float(np.quantile(internal_x, 0.95)) + 1.0
    limit_y = float(np.quantile(internal_y, 0.95)) + 1.0

    def axis_score(boundary: float, limit: float) -> float:
        if boundary <= limit:
            return 1.0
        return max(0.0, 1.0 - (boundary - limit) / max(limit, 1.0))

    score_x = axis_score(boundary_x, limit_x)
    score_y = axis_score(boundary_y, limit_y)
    score = 100 * math.sqrt(score_x * score_y)
    four_up = np.tile(array, (2, 2))
    height, width = array.shape
    quadrants_exact = bool(
        np.array_equal(four_up[:height, :width], array)
        and np.array_equal(four_up[:height, width:], array)
        and np.array_equal(four_up[height:, :width], array)
        and np.array_equal(four_up[height:, width:], array)
    )
    return score, {
        "periodic_generation": True,
        "four_up_quadrants_exact": quadrants_exact,
        "boundary_x_transition_mean": boundary_x,
        "boundary_y_transition_mean": boundary_y,
        "internal_x_p95_transition_mean": limit_x - 1.0,
        "internal_y_p95_transition_mean": limit_y - 1.0,
        "perceptual_seam_score_percent": score,
    }


def svg_for_tile(tile: np.ndarray) -> str:
    height, width = tile.shape
    values, counts = np.unique(tile, return_counts=True)
    background = int(values[int(np.argmax(counts))])
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" shape-rendering="crispEdges">',
        "  <!-- Procedural toroidal stone; every path is an integer pixel run. -->",
        f'  <rect width="{width}" height="{height}" fill="#{background:02x}{background:02x}{background:02x}"/>',
    ]
    for tone in values:
        tone_int = int(tone)
        if tone_int == background:
            continue
        commands: list[str] = []
        for y, row in enumerate(tile):
            x = 0
            while x < width:
                if int(row[x]) != tone_int:
                    x += 1
                    continue
                start = x
                while x < width and int(row[x]) == tone_int:
                    x += 1
                run = x - start
                commands.append(f"M{start} {y}h{run}v1h-{run}z")
        color = f"#{tone_int:02x}{tone_int:02x}{tone_int:02x}"
        lines.append(f'  <path fill="{color}" d="{"".join(commands)}"/>')
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def save_outputs(
    tile: np.ndarray,
    reference: np.ndarray,
    output_dir: Path,
    name: str,
    scale: int,
    report: dict[str, Any],
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    native = Image.fromarray(tile, mode="L").convert("RGB")
    native_path = output_dir / f"{name}.png"
    svg_path = output_dir / f"{name}.svg"
    preview_path = output_dir / f"{name}-{scale}x.png"
    four_up_path = output_dir / f"{name}-4up.png"
    comparison_path = output_dir / f"{name}-style-comparison.png"
    report_path = output_dir / f"{name}-report.json"

    native.save(native_path)
    svg_path.write_text(svg_for_tile(tile))
    native.resize((native.width * scale, native.height * scale), Image.Resampling.NEAREST).save(
        preview_path
    )
    four_up_native = Image.fromarray(np.tile(tile, (2, 2)), mode="L").convert("RGB")
    four_up_native.resize(
        (four_up_native.width * scale, four_up_native.height * scale),
        Image.Resampling.NEAREST,
    ).save(four_up_path)

    reference_image = Image.fromarray(reference, mode="L").convert("RGB").resize(
        (reference.shape[1] * scale, reference.shape[0] * scale),
        Image.Resampling.NEAREST,
    )
    generated_image = native.resize(reference_image.size, Image.Resampling.NEAREST)
    header = 34
    gap = 12
    sheet = Image.new(
        "RGB",
        (reference_image.width * 2 + gap, reference_image.height + header),
        "#101214",
    )
    draw = ImageDraw.Draw(sheet)
    draw.text((8, 10), "SOURCE STYLE", fill="#d7dadc")
    draw.text((reference_image.width + gap + 8, 10), "PROCEDURAL", fill="#d7dadc")
    sheet.paste(reference_image, (0, header))
    sheet.paste(generated_image, (reference_image.width + gap, header))
    sheet.save(comparison_path)

    outputs = {
        "native_png": str(native_path),
        "svg": str(svg_path),
        "preview": str(preview_path),
        "four_up": str(four_up_path),
        "style_comparison": str(comparison_path),
        "report": str(report_path),
    }
    report["outputs"] = outputs
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    return outputs


def main() -> None:
    args = parse_args()
    if args.width < 16 or args.height < 16:
        raise ValueError("width and height must both be at least 16 pixels")
    if args.candidates < 1:
        raise ValueError("--candidates must be positive")

    reference = load_grayscale(args.reference)
    palette, probabilities = palette_model(reference)
    reference_metrics = texture_metrics(reference, palette)

    seed_sequences = np.random.SeedSequence(args.seed).spawn(args.candidates)
    best: tuple[float, int, np.ndarray, dict[str, float], dict[str, Any], dict[str, float], float, dict[str, Any]] | None = None
    for sequence in seed_sequences:
        candidate_seed = int(sequence.generate_state(1, dtype=np.uint64)[0])
        tile, parameters = generate_candidate(
            candidate_seed,
            args.width,
            args.height,
            palette,
            probabilities,
        )
        metrics = texture_metrics(tile, palette)
        style_score, style_parts = style_similarity(metrics, reference_metrics, palette)
        seam_score, seam = seam_quality(tile)
        rank_score = style_score * 0.92 + seam_score * 0.08
        candidate = (
            rank_score,
            candidate_seed,
            tile,
            parameters,
            metrics,
            style_parts,
            style_score,
            seam,
        )
        if best is None or candidate[0] > best[0]:
            best = candidate

    assert best is not None
    rank_score, selected_seed, tile, parameters, metrics, style_parts, style_score, seam = best
    report: dict[str, Any] = {
        "generator": "periodic Fourier relief with wrapped chisel fields",
        "master_seed": args.seed,
        "selected_seed": selected_seed,
        "candidates_ranked": args.candidates,
        "width": args.width,
        "height": args.height,
        "palette": [int(value) for value in palette],
        "source_pixels_copied": False,
        "style_similarity_percent": style_score,
        "ranking_score_percent": rank_score,
        "style_components_percent": style_parts,
        "seam": seam,
        "parameters": parameters,
        "reference_metrics": reference_metrics,
        "generated_metrics": metrics,
    }
    outputs = save_outputs(
        tile,
        reference,
        args.output_dir,
        args.name,
        args.scale,
        report,
    )
    print(json.dumps({**report, "outputs": outputs}, indent=2))


if __name__ == "__main__":
    main()
