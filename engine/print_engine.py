#!/usr/bin/env python3

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def run_cmd(cmd):
    print("RUN:", " ".join(cmd))
    subprocess.run(cmd, check=True)


def send_to_printer(print_file: Path, printer: str | None = None):

    if not print_file.exists():
        raise RuntimeError(f"Print file does not exist: {print_file}")

    cmd = ["lp"]

    if printer:
        cmd += ["-d", printer]

    cmd.append(str(print_file))

    run_cmd(cmd)

    print(f"PRINT JOB SUBMITTED: {print_file}")


def main():

    parser = argparse.ArgumentParser(description="Photobooth print engine")

    parser.add_argument(
        "--print-file",
        required=True,
        help="Layout JPG to print",
    )

    parser.add_argument(
        "--printer",
        required=False,
        help="Optional printer name",
    )

    args = parser.parse_args()

    print_file = Path(args.print_file).resolve()

    send_to_printer(print_file, args.printer)


if __name__ == "__main__":
    raise SystemExit(main())