"""
core/tracker.py — TelescopeAI Camera Tracker

Pipeline:
  1. Frame-difference motion detection (Scanning mode)
  2. CSRT lock once movement confirmed over threshold
  3. PID controller converts pixel error → mount rate (deg/sec)
  4. scope.move_axis() sends rate commands via TelescopeDriver ABC

Usage:
    from utils.config import load_config
    from hardware import driver_factory
    from camera import camera_factory
    from core.tracker import start_tracking

    cfg   = load_config()
    scope = driver_factory(cfg)
    cam   = camera_factory(cfg)
    scope.connect()
    scope.unpark()
    cam.open()
    start_tracking(scope, cam, cfg)
"""
import cv2
import math
from core.pid_controller import PIDController
from hardware.base import TelescopeDriver
from camera.base import CameraDriver
from utils.logger import get_logger

logger = get_logger(__name__)

MIN_CONTOUR_AREA = 500   # px² — noise filter, not in config (implementation detail)


def start_tracking(
    scope: TelescopeDriver,
    camera: CameraDriver,
    cfg: dict,
) -> None:
    """
    Run the tracking loop until the user presses 'q'.

    The camera and scope must already be opened/connected before calling.
    Releases neither — the caller is responsible for cleanup.

    Args:
        scope:  Connected TelescopeDriver (ASCOM / INDI / Mock).
        camera: Opened CameraDriver (OpenCV / ZWO / Mock).
        cfg:    Full config dict as returned by load_config().
    """
    tracking_cfg = cfg.get("tracking", {})
    pixel_scale  = tracking_cfg.get("pixel_scale", 0.094)          # deg/pixel
    move_thresh  = tracking_cfg.get("movement_threshold_px", 50)
    max_patience = tracking_cfg.get("patience_frames", 60)
    kp = tracking_cfg.get("pid_kp", 0.4)
    ki = tracking_cfg.get("pid_ki", 0.005)
    kd = tracking_cfg.get("pid_kd", 0.08)

    pid_az  = PIDController(kp=kp, ki=ki, kd=kd, output_limits=(-3.5, 3.5))
    pid_alt = PIDController(kp=kp, ki=ki, kd=kd, output_limits=(-3.5, 3.5))

    csrt_tracker     = None
    is_tracking      = False
    prev_gray        = None
    potential_target = None
    patience_counter = 0

    w, h = camera.width, camera.height
    frame_cx, frame_cy = w // 2, h // 2

    logger.info("[TRACKER] Started  %dx%d  pixel_scale=%.4f deg/px", w, h, pixel_scale)
    print("[TRACKER] Running. Press 'q' to stop, 'r' to reset.")

    try:
        while True:
            ret, frame = camera.read()
            if not ret:
                logger.error("[TRACKER] Camera read failed — stopping")
                break

            # frame dimensions may change on first real frame (e.g. OpenCV)
            h, w = frame.shape[:2]
            frame_cx, frame_cy = w // 2, h // 2

            # ==================== Tracking mode ====================
            if is_tracking:
                success, box = csrt_tracker.update(frame)

                if success:
                    patience_counter = max_patience
                    x, y, bw, bh = [int(v) for v in box]
                    obj_x = x + bw // 2
                    obj_y = y + bh // 2

                    # x error: positive = target is right of centre → Az positive
                    # y error: y grows downward, so flip sign → Alt positive = up
                    err_x_deg = (obj_x - frame_cx) * pixel_scale
                    err_y_deg = (frame_cy - obj_y) * pixel_scale

                    rate_az  = pid_az.update(err_x_deg)
                    rate_alt = pid_alt.update(err_y_deg)

                    try:
                        scope.move_axis(0, rate_az)
                        scope.move_axis(1, rate_alt)
                    except Exception as exc:
                        logger.warning("[TRACKER] Mount error: %s", exc)

                    _draw_tracking(frame, x, y, bw, bh, obj_x, obj_y,
                                   frame_cx, frame_cy, err_x_deg, err_y_deg,
                                   rate_az, rate_alt)
                else:
                    patience_counter -= 1
                    cv2.putText(frame, f"LOST... patience={patience_counter}",
                                (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 165, 255), 2)

                    if patience_counter <= 0:
                        _stop_mount(scope)
                        pid_az.reset()
                        pid_alt.reset()
                        is_tracking      = False
                        csrt_tracker     = None
                        prev_gray        = None
                        potential_target = None
                        logger.info("[TRACKER] Target permanently lost — rescanning")

            # ==================== Scanning mode ====================
            else:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                gray = cv2.GaussianBlur(gray, (21, 21), 0)

                if prev_gray is not None:
                    delta  = cv2.absdiff(prev_gray, gray)
                    thresh = cv2.threshold(delta, 25, 255, cv2.THRESH_BINARY)[1]
                    thresh = cv2.dilate(thresh, None, iterations=2)
                    contours, _ = cv2.findContours(
                        thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
                    )

                    valid = [c for c in contours if cv2.contourArea(c) > MIN_CONTOUR_AREA]
                    best  = max(valid, key=cv2.contourArea, default=None)

                    if best is not None:
                        x, y, bw, bh = cv2.boundingRect(best)
                        center = (x + bw // 2, y + bh // 2)
                        cv2.rectangle(frame, (x, y), (x + bw, y + bh), (255, 100, 0), 2)

                        if potential_target is not None:
                            dist = math.hypot(
                                center[0] - potential_target[0],
                                center[1] - potential_target[1],
                            )
                            if dist > move_thresh:
                                csrt_tracker = cv2.TrackerCSRT_create()
                                csrt_tracker.init(frame, (x, y, bw, bh))
                                is_tracking      = True
                                patience_counter = max_patience
                                logger.info("[TRACKER] Locked! movement=%.0fpx", dist)

                        potential_target = center
                    else:
                        potential_target = None
                        cv2.putText(frame, "Scanning...",
                                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 200), 2)

                prev_gray = gray

            # ==================== Crosshair overlay ====================
            cv2.line(frame, (frame_cx, 0),      (frame_cx, h), (80, 80, 80), 1)
            cv2.line(frame, (0, frame_cy),       (w, frame_cy), (80, 80, 80), 1)
            cv2.imshow("TelescopeAI Tracker", frame)

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            if key == ord("r"):
                _stop_mount(scope)
                pid_az.reset()
                pid_alt.reset()
                is_tracking      = False
                csrt_tracker     = None
                potential_target = None
                logger.info("[TRACKER] Manual reset")

    finally:
        _stop_mount(scope)
        cv2.destroyAllWindows()
        logger.info("[TRACKER] Stopped")


# ── Internal helpers ───────────────────────────────────────────────────────────

def _stop_mount(scope: TelescopeDriver) -> None:
    """Stop both axes safely — called in finally blocks."""
    try:
        scope.move_axis(0, 0.0)
        scope.move_axis(1, 0.0)
    except Exception:
        pass


def _draw_tracking(
    frame,
    x: int, y: int, bw: int, bh: int,
    obj_x: int, obj_y: int,
    frame_cx: int, frame_cy: int,
    err_x_deg: float, err_y_deg: float,
    rate_az: float, rate_alt: float,
) -> None:
    """Draw bounding box, target dot, error line, and HUD text."""
    cv2.rectangle(frame, (x, y), (x + bw, y + bh), (0, 255, 0), 2)
    cv2.circle(frame, (obj_x, obj_y), 4, (0, 0, 255), -1)
    cv2.line(frame, (frame_cx, frame_cy), (obj_x, obj_y), (0, 255, 255), 1)
    err_as_x = int(err_x_deg * 3600)
    err_as_y = int(err_y_deg * 3600)
    cv2.putText(frame, f"LOCKED  err=({err_as_x}\", {err_as_y}\")",
                (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    cv2.putText(frame, f"Rate Az={rate_az:.2f}  Alt={rate_alt:.2f} deg/s",
                (10, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 220, 0), 1)
