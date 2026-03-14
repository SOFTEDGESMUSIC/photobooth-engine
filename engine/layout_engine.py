#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path
from typing import List
from PIL import Image


W, H = 1200, 1800          # 4x6" @ 300 dpi
MX, MY = 30, 100           # side / top margins
GAP = 20
COLS, ROWS = 2, 2
CELL_W = (W - 2 * MX - GAP) // COLS
CELL_H = int(CELL_W * 5 / 4)


def open_image_safely(path: Path) -> Image.Image:
    return Image.open(path).convert("RGB")


def find_overlay(job_dir: Path) -> Path | None:
    overlay_dir = job_dir / "overlay"
    if not overlay_dir.exists():
        return None

    pngs = sorted(overlay_dir.glob("*.png"))
    return pngs[0] if pngs else None


def build_layout(job_dir: Path, job_name: str, jpg_files: List[Path], print_path: Path) -> Path:
    if len(jpg_files) != 4:
        raise ValueError(f"Layout engine requires exactly 4 JPG files, got {len(jpg_files)}")

    canvas = Image.new("RGB", (W, H), "white")

    for idx, img_path in enumerate(jpg_files):
        with open_image_safely(img_path) as img:
            img = img.resize((CELL_W, CELL_H))

        col = idx % COLS
        row = idx // COLS
        x = MX + col * (CELL_W + GAP)
        y = MY + row * (CELL_H + GAP)
        canvas.paste(img, (x, y))

    overlay_path = find_overlay(job_dir)
    if overlay_path:
        with Image.open(overlay_path).convert("RGBA") as ov:
            canvas = canvas.convert("RGBA")
            ov = ov.resize(canvas.size)
            canvas.alpha_composite(ov)
            canvas = canvas.convert("RGB")

    print_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(print_path, quality=95, dpi=(300, 300), optimize=True)

    return print_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Build 4-up 4x6 layout from 4 JPGs")
    parser.add_argument("--job-dir", required=True, help="Path to job directory")
    parser.add_argument("--job-name", required=True, help="Job name, e.g. 260314_BIRTHDAYPARTY")
    parser.add_argument("--print-path", required=True, help="Output print JPG path")
    parser.add_argument("--jpg-files", nargs=4, required=True, help="Exactly 4 JPG input files")
    args = parser.parse_args()

    job_dir = Path(args.job_dir).expanduser().resolve()
    print_path = Path(args.print_path).expanduser().resolve()
    jpg_files = [Path(p).expanduser().resolve() for p in args.jpg_files]

    out = build_layout(job_dir, args.job_name, jpg_files, print_path)
    print(f"Layout created: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
