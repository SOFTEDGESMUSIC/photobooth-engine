import subprocess
import time
import logging


def run_cmd(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def detect_camera():
    r = run_cmd(["gphoto2", "--auto-detect"])
    return "Canon EOS 5D Mark III" in r.stdout


def kill_gphoto():
    subprocess.run(["pkill", "-f", "gphoto2"], capture_output=True, text=True)


def wait_for_camera(retries=5, delay=1):
    for _ in range(retries):
        if detect_camera():
            return True
        time.sleep(delay)
    return False


def recover_camera(status_callback=None):
    """
    Attempt to recover the camera if gphoto fails or USB disconnects.
    """

    logging.warning("Attempting camera recovery")

    if status_callback:
        status_callback("recovering_camera")

    # kill stuck gphoto processes
    kill_gphoto()

    time.sleep(1)

    for attempt in range(5):

        if detect_camera():

            logging.info("Camera recovered")

            if status_callback:
                status_callback("camera_recovered")

            return True

        logging.warning("Camera still not detected, retry %s", attempt + 1)

        time.sleep(1)

    logging.error("Camera recovery failed")

    if status_callback:
        status_callback("camera_recovery_failed")

    return False


def capture_with_retry(filename, retries=2):

    for attempt in range(retries):

        cmd = [
            "gphoto2",
            "--capture-image-and-download",
            "--filename",
            filename
        ]

        r = run_cmd(cmd)

        if r.returncode == 0:
            return True

        logging.warning("Capture failed, retrying %s", attempt + 1)

        time.sleep(1)

    return False
