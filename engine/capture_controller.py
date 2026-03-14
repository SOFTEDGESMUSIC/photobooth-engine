#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import logging
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

RETRY_CAMERA_SECONDS = 5
SHOTS_PER_SEQUENCE = 4

ABORT_REQUESTED = False


class CaptureError(Exception):
    pass


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def setup_logging(log_file: Path) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout),
        ],
    )


def signal_handler(signum, frame) -> None:
    global ABORT_REQUESTED
    ABORT_REQUESTED = True
    logging.warning("Abort requested via signal %s", signum)


def run_cmd(cmd: List[str], check: bool = True) -> subprocess.CompletedProcess:
    logging.info("RUN: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.stdout.strip():
        logging.info("STDOUT: %s", result.stdout.strip())
    if result.stderr.strip():
        logging.info("STDERR: %s", result.stderr.strip())
    if check and result.returncode != 0:
        raise CaptureError(f"Command failed ({result.returncode}): {' '.join(cmd)}")
    return result


def ensure_job_structure(job_dir: Path) -> dict[str, Path]:
    paths = {
        "raw": job_dir / "raw",
        "jpg": job_dir / "jpg",
        "prints": job_dir / "prints",
        "overlay": job_dir / "overlay",
        "config": job_dir / "config",
        "logs": job_dir / "logs",
        "counter": job_dir / "config" / "capture_counter.txt",
        "print_counter": job_dir / "config" / "print_counter.txt",
        "status": job_dir / "status.json",
        "controller_log": job_dir / "logs" / "capture_controller.log",
    }

    for key in ("raw", "jpg", "prints", "overlay", "config", "logs"):
        paths[key].mkdir(parents=True, exist_ok=True)

    if not paths["counter"].exists():
        paths["counter"].write_text("0\n", encoding="utf-8")

    if not paths["print_counter"].exists():
        paths["print_counter"].write_text("0\n", encoding="utf-8")

    return paths


def read_int_file(path: Path, default: int = 0) -> int:
    if not path.exists():
        return default
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except ValueError:
        return default


def write_int_file(path: Path, value: int) -> None:
    path.write_text(f"{value}\n", encoding="utf-8")


def sequence_width(seq_num: int) -> int:
    return 3 if seq_num <= 999 else 4


def build_capture_name(job_name: str, seq_num: int) -> str:
    width = sequence_width(seq_num)
    return f"{job_name}_{seq_num:0{width}d}"


def build_print_name(job_name: str, seq_num: int) -> str:
    width = sequence_width(seq_num)
    return f"{job_name}_PRINT_{seq_num:0{width}d}.jpg"


def led_hook(hook_cmd: Optional[str], state: str) -> None:
    if hook_cmd:
        try:
            run_cmd([hook_cmd, state], check=True)
        except Exception as exc:
            logging.warning("LED hook failed for state '%s': %s", state, exc)
    else:
        logging.info("LED STATE: %s", state)


def update_status(
    status_file: Path,
    *,
    job_name: str,
    engine_state: str,
    camera_state: str,
    printer_state: str = "unknown",
    current_phase: str = "",
    sequence_active: bool = False,
    manual_mode: bool = False,
    current_shot_in_sequence: int = 0,
    shots_per_sequence: int = SHOTS_PER_SEQUENCE,
    last_capture_number: int = 0,
    last_print_number: int = 0,
    last_successful_stage: str = "",
    last_error: Optional[str] = None,
    last_error_time: Optional[str] = None,
    last_capture_file: Optional[str] = None,
    last_print_file: Optional[str] = None,
    job_dir: Optional[Path] = None,
) -> None:
    payload = {
        "job_name": job_name,
        "engine_state": engine_state,
        "camera_state": camera_state,
        "printer_state": printer_state,
        "current_phase": current_phase,
        "sequence_active": sequence_active,
        "manual_mode": manual_mode,
        "current_shot_in_sequence": current_shot_in_sequence,
        "shots_per_sequence": shots_per_sequence,
        "last_capture_number": last_capture_number,
        "last_print_number": last_print_number,
        "last_successful_stage": last_successful_stage,
        "last_error": last_error,
        "last_error_time": last_error_time,
        "last_capture_file": last_capture_file,
        "last_print_file": last_print_file,
        "job_dir": str(job_dir) if job_dir else None,
        "updated_at": utc_now_iso(),
    }
    status_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def detect_camera_once() -> bool:
    result = run_cmd(["gphoto2", "--auto-detect"], check=True)
    return "Canon EOS 5D Mark III" in result.stdout


def wait_for_camera(status_file: Path, job_name: str, job_dir: Path, retries: int = RETRY_CAMERA_SECONDS) -> bool:
    for attempt in range(1, retries + 1):
        update_status(
            status_file,
            job_name=job_name,
            engine_state="arming",
            camera_state="not_detected",
            current_phase=f"camera_detect_retry_{attempt}",
            sequence_active=False,
            job_dir=job_dir,
        )
        if detect_camera_once():
            update_status(
                status_file,
                job_name=job_name,
                engine_state="idle",
                camera_state="connected",
                current_phase="camera_detected",
                sequence_active=False,
                last_successful_stage="camera_detected",
                job_dir=job_dir,
            )
            return True
        time.sleep(1)
    return False


def capture_one(raw_dir: Path, filename_stem: str) -> Path:
    raw_path = raw_dir / f"{filename_stem}.CR2"
    cmd = [
        "gphoto2",
        "--capture-image-and-download",
        "--filename",
        str(raw_path),
    ]
    run_cmd(cmd, check=True)

    if raw_path.exists():
        return raw_path

    alt = raw_dir / f"{filename_stem}.cr2"
    if alt.exists():
        return alt

    raise CaptureError(f"Capture reported success but file not found: {raw_path}")


def remove_partial_files(files: List[Path]) -> None:
    for f in files:
        try:
            if f.exists():
                f.unlink()
                logging.info("Deleted partial file: %s", f)
        except Exception as exc:
            logging.warning("Failed to delete partial file %s: %s", f, exc)


def first_shot_led_sequence(hook_cmd: Optional[str]) -> None:
    led_hook(hook_cmd, "on")
    time.sleep(1.0)

    for _ in range(2):
        led_hook(hook_cmd, "on")
        time.sleep(0.5)
        led_hook(hook_cmd, "off")
        time.sleep(0.5)

    led_hook(hook_cmd, "on")
    time.sleep(1.0)


def subsequent_shot_led_sequence(hook_cmd: Optional[str]) -> None:
    led_hook(hook_cmd, "off")
    time.sleep(1.0)

    for _ in range(2):
        led_hook(hook_cmd, "on")
        time.sleep(0.5)
        led_hook(hook_cmd, "off")
        time.sleep(0.5)

    led_hook(hook_cmd, "on")
    time.sleep(1.0)


def get_last_n_raw_files(job_dir: Path, count: int) -> List[Path]:
    raw_dir = job_dir / "raw"
    raw_files = sorted(raw_dir.glob("*.CR2"))
    if len(raw_files) < count:
        raw_files = sorted(raw_dir.glob("*.cr2"))
    return raw_files[-count:]


def run_raw_processor(job_dir: Path, raw_files: List[Path]) -> None:
    cmd = [
        "python3",
        str(Path.home() / "photobooth/engine/raw_processor.py"),
        "--job-dir",
        str(job_dir),
        "--raw-files",
        *[str(f) for f in raw_files],
    ]
    run_cmd(cmd, check=True)


def run_layout_engine(job_dir: Path, job_name: str, status_file: Path, last_capture_number: int) -> None:
    print_counter_file = job_dir / "config" / "print_counter.txt"
    print_counter = read_int_file(print_counter_file, default=0) + 1
    write_int_file(print_counter_file, print_counter)

    print_name = build_print_name(job_name, print_counter)
    print_path = job_dir / "prints" / print_name

    update_status(
        status_file,
        job_name=job_name,
        engine_state="layout",
        camera_state="connected",
        current_phase="building_layout",
        sequence_active=True,
        last_capture_number=last_capture_number,
        last_print_number=print_counter,
        last_successful_stage="raw_processed",
        last_print_file=str(print_path),
        job_dir=job_dir,
    )

    logging.info("LAYOUT ENGINE WOULD RUN HERE -> %s", print_path)

    update_status(
        status_file,
        job_name=job_name,
        engine_state="printing",
        camera_state="connected",
        current_phase="sending_to_printer",
        sequence_active=True,
        last_capture_number=last_capture_number,
        last_print_number=print_counter,
        last_successful_stage="layout_built",
        last_print_file=str(print_path),
        job_dir=job_dir,
    )

    logging.info("PRINT WOULD BE SENT HERE -> %s", print_path)

    update_status(
        status_file,
        job_name=job_name,
        engine_state="complete",
        camera_state="connected",
        printer_state="ready",
        current_phase="sequence_complete",
        sequence_active=False,
        last_capture_number=last_capture_number,
        last_print_number=print_counter,
        last_successful_stage="print_sent",
        last_print_file=str(print_path),
        job_dir=job_dir,
    )


def run_sequence(job_dir: Path, job_name: str, hook_cmd: Optional[str], manual: bool = False) -> List[Path]:
    global ABORT_REQUESTED

    paths = ensure_job_structure(job_dir)
    setup_logging(paths["controller_log"])

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    counter = read_int_file(paths["counter"], default=0)
    print_counter = read_int_file(paths["print_counter"], default=0)

    update_status(
        paths["status"],
        job_name=job_name,
        engine_state="arming",
        camera_state="unknown",
        current_phase="starting",
        sequence_active=not manual,
        manual_mode=manual,
        last_capture_number=counter,
        last_print_number=print_counter,
        job_dir=job_dir,
    )

    if not wait_for_camera(paths["status"], job_name, job_dir):
        update_status(
            paths["status"],
            job_name=job_name,
            engine_state="error",
            camera_state="not_detected",
            current_phase="camera_not_detected",
            sequence_active=False,
            manual_mode=manual,
            last_capture_number=counter,
            last_print_number=print_counter,
            last_successful_stage="start_failed",
            last_error="Camera not detected. Check power and USB.",
            last_error_time=utc_now_iso(),
            job_dir=job_dir,
        )
        raise CaptureError("Camera not detected. Check power and USB.")

    captured_files: List[Path] = []

    try:
        if manual:
            next_num = counter + 1
            stem = build_capture_name(job_name, next_num)

            update_status(
                paths["status"],
                job_name=job_name,
                engine_state="capturing",
                camera_state="connected",
                current_phase="manual_capture",
                sequence_active=False,
                manual_mode=True,
                current_shot_in_sequence=1,
                last_capture_number=counter,
                last_print_number=print_counter,
                job_dir=job_dir,
            )

            raw_file = capture_one(paths["raw"], stem)
            led_hook(hook_cmd, "off")

            counter = next_num
            write_int_file(paths["counter"], counter)
            captured_files.append(raw_file)

            update_status(
                paths["status"],
                job_name=job_name,
                engine_state="idle",
                camera_state="connected",
                current_phase="manual_capture_complete",
                sequence_active=False,
                manual_mode=True,
                current_shot_in_sequence=0,
                last_capture_number=counter,
                last_print_number=print_counter,
                last_successful_stage="manual_capture_complete",
                last_capture_file=str(raw_file),
                job_dir=job_dir,
            )

            if counter % 4 == 0:
                batch_raw_files = get_last_n_raw_files(job_dir, 4)

                update_status(
                    paths["status"],
                    job_name=job_name,
                    engine_state="processing",
                    camera_state="connected",
                    current_phase="processing_raw",
                    sequence_active=True,
                    manual_mode=True,
                    current_shot_in_sequence=0,
                    last_capture_number=counter,
                    last_print_number=print_counter,
                    last_successful_stage="manual_capture_complete",
                    job_dir=job_dir,
                )
                run_raw_processor(job_dir, batch_raw_files)
                run_layout_engine(job_dir, job_name, paths["status"], counter)

            return captured_files

        for shot_index in range(1, SHOTS_PER_SEQUENCE + 1):
            if ABORT_REQUESTED:
                raise CaptureError("Sequence aborted.")

            update_status(
                paths["status"],
                job_name=job_name,
                engine_state="capturing",
                camera_state="connected",
                current_phase=f"shot_{shot_index}_countdown",
                sequence_active=True,
                manual_mode=False,
                current_shot_in_sequence=shot_index,
                last_capture_number=counter,
                last_print_number=print_counter,
                last_successful_stage=f"shot_{shot_index-1}_captured" if shot_index > 1 else "camera_detected",
                job_dir=job_dir,
            )

            if shot_index == 1:
                first_shot_led_sequence(hook_cmd)
            else:
                subsequent_shot_led_sequence(hook_cmd)

            if ABORT_REQUESTED:
                raise CaptureError("Sequence aborted before capture.")

            next_num = counter + 1
            stem = build_capture_name(job_name, next_num)

            update_status(
                paths["status"],
                job_name=job_name,
                engine_state="capturing",
                camera_state="connected",
                current_phase=f"shot_{shot_index}_capture",
                sequence_active=True,
                manual_mode=False,
                current_shot_in_sequence=shot_index,
                last_capture_number=counter,
                last_print_number=print_counter,
                job_dir=job_dir,
            )

            raw_file = capture_one(paths["raw"], stem)
            led_hook(hook_cmd, "off")

            counter = next_num
            write_int_file(paths["counter"], counter)
            captured_files.append(raw_file)

            update_status(
                paths["status"],
                job_name=job_name,
                engine_state="capturing",
                camera_state="connected",
                current_phase=f"shot_{shot_index}_complete",
                sequence_active=True,
                manual_mode=False,
                current_shot_in_sequence=shot_index,
                last_capture_number=counter,
                last_print_number=print_counter,
                last_successful_stage=f"shot_{shot_index}_captured",
                last_capture_file=str(raw_file),
                job_dir=job_dir,
            )

        update_status(
            paths["status"],
            job_name=job_name,
            engine_state="processing",
            camera_state="connected",
            current_phase="processing_raw",
            sequence_active=True,
            manual_mode=False,
            current_shot_in_sequence=0,
            last_capture_number=counter,
            last_print_number=print_counter,
            last_successful_stage="shot_4_captured",
            job_dir=job_dir,
        )

        run_raw_processor(job_dir, captured_files)
        run_layout_engine(job_dir, job_name, paths["status"], counter)
        return captured_files

    except Exception as exc:
        logging.error("Capture sequence failed: %s", exc)
        remove_partial_files(captured_files)

        update_status(
            paths["status"],
            job_name=job_name,
            engine_state="error",
            camera_state="connected" if detect_camera_once() else "not_detected",
            current_phase="capture_error",
            sequence_active=False,
            manual_mode=manual,
            current_shot_in_sequence=0,
            last_capture_number=counter,
            last_print_number=print_counter,
            last_successful_stage="error",
            last_error=str(exc),
            last_error_time=utc_now_iso(),
            job_dir=job_dir,
        )
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="Timed photobooth capture controller")
    parser.add_argument("--job-dir", required=True, help="Full path to job folder")
    parser.add_argument("--job-name", required=True, help="Job name prefix, e.g. 260314_BIRTHDAYPARTY")
    parser.add_argument("--manual", action="store_true", help="Capture one manual test shot")
    parser.add_argument("--led-hook", default=None, help="Optional executable called with LED state")
    args = parser.parse_args()

    job_dir = Path(args.job_dir).expanduser().resolve()

    try:
        captured = run_sequence(
            job_dir=job_dir,
            job_name=args.job_name,
            hook_cmd=args.led_hook,
            manual=args.manual,
        )
        print("\nCapture sequence succeeded:")
        for f in captured:
            print(f"  {f}")
        return 0
    except Exception as exc:
        print(f"\nCapture sequence failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
