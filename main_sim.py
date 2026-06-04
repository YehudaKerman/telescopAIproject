"""
main_sim.py — TelescopeAI Simulation Mode (Raspberry Pi)

Runs the full tracking pipeline on a pre-recorded video file instead of
real hardware.  Everything else is identical to main_rpi.py:
  - Frames stream over MJPEG to Windows (main_remote.py)
  - SimulatedDriver integrates PID rate commands over time
  - An orange crosshair overlaid on each frame shows where the telescope
    is currently pointing — it should converge on the tracked object if
    the tracker is working correctly

Overlay legend:
  ── grey crosshair  → frame centre (fixed reference)
  ◎  orange circle   → current telescope pointing (moves with mount commands)
  □  green box       → CSRT tracker lock on target
  ●  red dot         → target centre
  ──  cyan line      → error vector (target → frame centre)

Prerequisites on RPi:
    # Copy a video file to the RPi first, e.g.:
    scp drone.mp4 kcg@kcg.local:/home/kcg/sim_videos/

    # Edit config.yaml (simulation section), then:
    .venv/bin/python main_sim.py

config.yaml settings:
    camera:
      backend: "video_file"
      video_path: "/home/kcg/sim_videos/drone.mp4"
      loop: true
      fps_override: null    # null = use file's native FPS

    mount:
      backend: "simulated"

    stream:
      port: 8080            # same port as main_rpi.py — view with main_remote.py
"""
import queue
import signal
import threading

import cv2

from camera import camera_factory
from core.tracker import start_tracking
from hardware.simulated_driver import SimulatedDriver
from rpi.stream_server import StreamServer
from utils.config import load_config
from utils.logger import get_logger, setup_logging

cfg = load_config()
setup_logging(cfg)
logger = get_logger(__name__)

_stop_event = threading.Event()

# Orange colour used for all telescope-pointing overlays
_SCOPE_COLOUR = (0, 140, 255)


def _handle_signal(sig, _frame):
    logger.info("[SIM] Signal %d — stopping", sig)
    _stop_event.set()


def _draw_scope_crosshair(frame, cx: int, cy: int) -> None:
    """Draw the telescope pointing crosshair at (cx, cy)."""
    h, w = frame.shape[:2]
    # Clamp so the crosshair stays inside the frame
    cx = max(25, min(w - 25, cx))
    cy = max(25, min(h - 25, cy))

    arm = 22
    cv2.line(frame, (cx - arm, cy), (cx + arm, cy), _SCOPE_COLOUR, 2)
    cv2.line(frame, (cx, cy - arm), (cx, cy + arm), _SCOPE_COLOUR, 2)
    cv2.circle(frame, (cx, cy), 15, _SCOPE_COLOUR, 1)
    cv2.circle(frame, (cx, cy), 3,  _SCOPE_COLOUR, -1)


def main() -> None:
    signal.signal(signal.SIGINT,  _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    # --- Hardware setup ---
    # mount.backend is forced to "simulated" regardless of config.yaml
    driver = SimulatedDriver()

    # Camera reads from video file (config: camera.backend = "video_file")
    cam = camera_factory(cfg)

    pixel_scale = cfg.get("tracking", {}).get("pixel_scale", 0.094)

    # --- MJPEG stream server ---
    frame_queue  = queue.Queue(maxsize=2)
    server       = StreamServer(cfg, frame_queue)
    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()

    stream_port = cfg.get("stream", {}).get("port", 8080)
    rpi_host    = cfg.get("rpi", {}).get("host", "kcg.local")
    logger.info("[SIM] MJPEG stream: http://%s:%d/stream", rpi_host, stream_port)

    try:
        logger.info("[SIM] Connecting simulated mount...")
        driver.connect()
        driver.unpark()
        cam.open()
        logger.info("[SIM] Ready. Starting simulation tracker (headless)...")

        def push_frame(frame) -> None:
            """
            Called by tracker on every annotated frame.
            Adds the telescope pointing crosshair before pushing to stream.
            """
            h, w = frame.shape[:2]
            dx, dy = driver.get_pixel_offset(pixel_scale)
            scope_cx = w // 2 + dx
            scope_cy = h // 2 + dy

            _draw_scope_crosshair(frame, scope_cx, scope_cy)

            # HUD: pointing offset in degrees and arcseconds
            az_off, alt_off = driver.get_offset_deg()
            az_as  = az_off  * 3600
            alt_as = alt_off * 3600
            cv2.putText(
                frame,
                f"SCOPE  Az={az_as:+.0f}\"  Alt={alt_as:+.0f}\"",
                (10, frame.shape[0] - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, _SCOPE_COLOUR, 1,
            )

            if not frame_queue.full():
                frame_queue.put_nowait(frame)

        start_tracking(
            driver, cam, cfg,
            on_frame=push_frame,
            headless=True,
            stop_event=_stop_event,
        )

    except KeyboardInterrupt:
        logger.info("[SIM] Keyboard interrupt")
    finally:
        logger.info("[SIM] Releasing resources...")
        try:
            cam.release()
        except Exception:
            pass
        try:
            driver.disconnect()
        except Exception:
            pass
        logger.info("[SIM] Done. Total move_axis calls: %d", len(driver.move_axis_calls))


if __name__ == "__main__":
    main()
