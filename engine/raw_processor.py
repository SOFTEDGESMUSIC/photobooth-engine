#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List

import numpy as np
import rawpy
from PIL import Image, ImageEnhance


def load_style(style_path: Path) -> dict:
    with open(style_path, "r", encoding="utf-8") as f:
        return json.load(f)


def apply_temperature(image: np.ndarray, temperature: float) -> np.ndarray:
    """
    Very simple temperature adjustment around 5600K baseline.
    Higher temp = warmer, lower temp = cooler.
    """
    baseline = 5600.0
    shift = (temperature - baseline) / 2000.0

    img = image.astype(np.float32)

    # warm = boost red, reduce blue
    img[..., 0] *= (1.0 + 0.15 * shift)   # red
    img[..., 2] *= (1.0 - 0.15 * shift)   # blue

    return np.clip(img, 0, 255).astype(np.uint8)


def apply_hue(image: Image.Image, hue_degrees: float) -> Image.Image:
    if abs(hue_degrees) < 1e-6:
        return image

    hsv = image.convert("HSV")
    arr = np.array(hsv, dtype=np.uint8)

    # hue channel is 0-255, so convert degrees to that scale
    shift = int((hue_degrees / 360.0) * 255) % 255
    arr[..., 0] = (arr[..., 0].astype(np.int16) + shift) % 255

    return Image.fromarray(arr, mode="HSV").convert("RGB")

def process_raw_file(raw_path: Path, jpg_path: Path, style: dict) -> None:
    exposure = float(style.get("exposure", 0.0))
    contrast = float(style.get("contrast", 1.0))
    brightness = float(style.get("brightness", 1.0))
    saturation = float(style.get("saturation", 1.0))
    temperature = float(style.get("temperature", 5600))
    hue = float(style.get("hue", 0.0))
    jpeg_quality = int(style.get("jpeg_quality", 95))

    with rawpy.imread(str(raw_path)) as raw:
        rgb = raw.postprocess(
            use_camera_wb=True,
            output_bps=8,
            exp_shift=(2.0 ** exposure),
            gamma=(1, 1),
            no_auto_scale=False,
        )
    rgb = apply_temperature(rgb, temperature)

    image = Image.fromarray(rgb)

    if abs(brightness - 1.0) > 1e-6:
        image = ImageEnhance.Brightness(image).enhance(brightness)

    if abs(contrast - 1.0) > 1e-6:
        image = ImageEnhance.Contrast(image).enhance(contrast)

    if abs(saturation - 1.0) > 1e-6:
        image = ImageEnhance.Color(image).enhance(saturation)

    if abs(hue) > 1e-6:
        image = apply_hue(image, hue)

    jpg_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(jpg_path, format="JPEG", quality=jpeg_quality, optimize=True)


def raw_to_jpg_name(raw_file: Path) -> str:
    return raw_file.stem + ".jpg"


def process_batch(job_dir: Path, raw_files: List[Path]) -> List[Path]:
    style_path = job_dir / "config" / "style.json"
    jpg_dir = job_dir / "jpg"

    style = load_style(style_path)
    output_files: List[Path] = []

    for raw_file in raw_files:
        jpg_file = jpg_dir / raw_to_jpg_name(raw_file)
        process_raw_file(raw_file, jpg_file, style)
        output_files.append(jpg_file)

    return output_files


def main() -> int:
    parser = argparse.ArgumentParser(description="Process RAW CR2 files to JPG using style.json")
    parser.add_argument("--job-dir", required=True, help="Path to job directory")
    parser.add_argument("--raw-files", nargs="+", required=True, help="One or more RAW files to process")
    args = parser.parse_args()

    job_dir = Path(args.job_dir).expanduser().resolve()
    raw_files = [Path(f).expanduser().resolve() for f in args.raw_files]

    output_files = process_batch(job_dir, raw_files)

    print("Processed JPGs:")
    for f in output_files:
        print(f"  {f}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
