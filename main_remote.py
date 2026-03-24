"""
main_remote.py — TelescopeAI remote viewer for Windows

Connects to the MJPEG stream from the Raspberry Pi and displays it
locally with cv2.imshow.

Usage:
    python main_remote.py
    python main_remote.py --host 192.168.1.50   # override hostname

Keyboard:
    q — quit

config.yaml:
    rpi:
      host: "kcg.local"   # hostname or IP of the Raspberry Pi
    stream:
      port: 8080
"""
import argparse
import urllib.request

import cv2
import numpy as np

from utils.config import load_config
from utils.logger import setup_logging, get_logger

cfg = load_config()
setup_logging(cfg)
logger = get_logger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="TelescopeAI remote viewer")
    parser.add_argument("--host", default=None,
                        help="RPi hostname or IP (overrides config rpi.host)")
    args = parser.parse_args()

    host = args.host or cfg.get("rpi", {}).get("host", "kcg.local")
    port = cfg.get("stream", {}).get("port", 8080)
    url  = f"http://{host}:{port}/video"

    logger.info("[REMOTE] Connecting to %s", url)
    print(f"Connecting to {url}  —  press 'q' to quit")

    try:
        stream = urllib.request.urlopen(url, timeout=10)
    except Exception as exc:
        logger.error("[REMOTE] Cannot connect: %s", exc)
        print(f"ERROR: Cannot connect to {url}\n  {exc}")
        return

    buf = b""
    try:
        while True:
            buf += stream.read(4096)

            # Find JPEG boundaries
            start = buf.find(b"\xff\xd8")   # JPEG SOI
            end   = buf.find(b"\xff\xd9")   # JPEG EOI
            if start != -1 and end != -1 and end > start:
                jpg   = buf[start : end + 2]
                buf   = buf[end + 2:]
                frame = cv2.imdecode(
                    np.frombuffer(jpg, dtype=np.uint8),
                    cv2.IMREAD_COLOR,
                )
                if frame is not None:
                    cv2.imshow("TelescopeAI — Remote", frame)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    except KeyboardInterrupt:
        pass
    finally:
        cv2.destroyAllWindows()
        logger.info("[REMOTE] Disconnected")


if __name__ == "__main__":
    main()
