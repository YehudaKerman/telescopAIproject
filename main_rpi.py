"""
main_rpi.py — TelescopeAI entry point for Raspberry Pi (headless)

Runs the full tracking pipeline locally:
    ZWO camera → tracker → PID → indiserver → Celestron mount
    Annotated frames → Flask MJPEG stream → Windows viewer

Prerequisites:
    # Start INDI server (in a separate terminal or systemd service):
    indiserver -v indi_celestron_gps      # adjust driver name as needed

    # Run this script:
    .venv/bin/python main_rpi.py

config.yaml settings for RPi (edit before running):
    mount.backend:  "indi"
    camera.backend: "zwo"
    camera.sdk_path: "/usr/lib/libASICamera2.so"
    indi.host:      "localhost"
    stream.port:    8080
"""
import queue
import signal
import threading

from utils.config import load_config
from utils.logger import setup_logging, get_logger
from hardware import driver_factory
from camera import camera_factory
from core.tracker import start_tracking
from rpi.stream_server import StreamServer

cfg = load_config()
setup_logging(cfg)
logger = get_logger(__name__)

_stop_event = threading.Event()


def _handle_signal(sig, frame):
    logger.info("[RPi] Signal %d received — stopping", sig)
    _stop_event.set()


def main() -> None:
    signal.signal(signal.SIGINT,  _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    frame_queue = queue.Queue(maxsize=2)

    # Start MJPEG stream server in background
    server = StreamServer(cfg, frame_queue)
    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()

    scope = driver_factory(cfg)
    cam   = camera_factory(cfg)

    try:
        logger.info("[RPi] Connecting hardware...")
        scope.connect()
        scope.unpark()
        cam.open()
        logger.info("[RPi] Hardware ready. Starting tracker (headless)...")

        def push_frame(frame):
            if not frame_queue.full():
                frame_queue.put_nowait(frame)

        start_tracking(
            scope, cam, cfg,
            on_frame=push_frame,
            headless=True,
            stop_event=_stop_event,
        )

    except KeyboardInterrupt:
        logger.info("[RPi] Keyboard interrupt")
    finally:
        logger.info("[RPi] Releasing hardware...")
        try:
            cam.release()
        except Exception:
            pass
        try:
            scope.disconnect()
        except Exception:
            pass
        logger.info("[RPi] Shutdown complete")


if __name__ == "__main__":
    main()
