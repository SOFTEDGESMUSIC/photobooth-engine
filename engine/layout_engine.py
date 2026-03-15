#!/usr/bin/env python3

from pathlib import Path
from PIL import Image
import argparse

PRINT_WIDTH = 1240
PRINT_HEIGHT = 1860
PHOTO_COUNT = 4


def crop_to_ratio(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    src_w, src_h = img.size
    src_ratio = src_w / src_h
    target_ratio = target_w / target_h

    if src_ratio > target_ratio:
        # too wide
        new_w = int(src_h * target_ratio)
        left = (src_w - new_w) // 2
        return img.crop((left, 0, left + new_w, src_h))
    else:
        # too tall
        new_h = int(src_w / target_ratio)
        top = (src_h - new_h) // 2
        return img.crop((0, top, src_w, top + new_h))


def create_layout(jpg_files, print_path: Path, rotate_for_printer: bool = False):
    margin_x = 40
    margin_y = 40
    gap = 20

    cell_width = PRINT_WIDTH - (margin_x * 2)
    usable_height = PRINT_HEIGHT - (margin_y * 2) - (gap * (PHOTO_COUNT - 1))
    cell_height = usable_height // PHOTO_COUNT

    canvas = Image.new("RGB", (PRINT_WIDTH, PRINT_HEIGHT), (255, 255, 255))

    for i, jpg in enumerate(jpg_files):
        img = Image.open(jpg).convert("RGB")
        img = crop_to_ratio(img, 4, 5)
        img = img.resize((cell_width, cell_height), Image.LANCZOS)

        y = margin_y + i * (cell_height + gap)
        canvas.paste(img, (margin_x, y))

    if rotate_for_printer:
        canvas = canvas.transpose(Image.Transpose.ROTATE_90)

    print_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(
        print_path,
        "JPEG",
        quality=95,
        subsampling=0,
        dpi=(310, 310),
    )

    print(f"LAYOUT CREATED -> {print_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-dir")
    parser.add_argument("--job-name")
    parser.add_argument("--print-path", required=True)
    parser.add_argument("--jpg-files", nargs="+", required=True)
    parser.add_argument("--rotate-for-printer", action="store_true")
    args = parser.parse_args()

    jpg_files = args.jpg_files[:PHOTO_COUNT]
    create_layout(
        jpg_files=jpg_files,
        print_path=Path(args.print_path),
        rotate_for_printer=args.rotate_for_printer,
    )


if __name__ == "__main__":
    main()
