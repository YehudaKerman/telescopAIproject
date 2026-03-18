"""
tracker.py — TelescopeAI Camera Tracker

Pipeline:
  1. Frame-difference motion detection (Scanning mode)
  2. CSRT lock once movement confirmed over threshold
  3. PID controller converts pixel error -> mount rate (deg/sec)
  4. scope.MoveAxis() sends rate commands to ASCOM telescope

Call: tracker.start_tracking(scope)
"""
import cv2
import math
import time
from pid_controller import PIDController
from utils.config import load_config

# --- טעינת קונפיגורציה ---
_cfg = load_config()
_tracking = _cfg['tracking']
_camera = _cfg['camera']

PIXEL_SCALE = _tracking['pixel_scale']          # deg/pixel
MOVEMENT_THRESHOLD = _tracking['movement_threshold_px']  # פיקסלים — תנועה מינימלית לנעילה
MAX_PATIENCE = _tracking['patience_frames']      # פריימים לפני ויתור על יעד שאבד
MIN_CONTOUR_AREA = 500                           # פיקסלים² — סינון רעש (לא ב-config)
CAMERA_INDEX = _camera['index']
CAMERA_EXPOSURE = _camera['exposure']
CAMERA_WIDTH = _camera['width']
CAMERA_HEIGHT = _camera['height']

_PID_KP = _tracking['pid_kp']
_PID_KI = _tracking['pid_ki']
_PID_KD = _tracking['pid_kd']


def start_tracking(scope, pixel_scale: float = PIXEL_SCALE):
    """
    מפעיל עקיבת מצלמה ומסובב את הטלסקופ לשמור על היעד במרכז.

    Args:
        scope: אובייקט ASCOM telescope (win32com.client.Dispatch)
        pixel_scale: יחס המרה deg/pixel (תלוי בעדשה וחיישן)
    """
    pid_az  = PIDController(kp=_PID_KP, ki=_PID_KI, kd=_PID_KD, output_limits=(-3.5, 3.5))
    pid_alt = PIDController(kp=_PID_KP, ki=_PID_KI, kd=_PID_KD, output_limits=(-3.5, 3.5))

    cap = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_DSHOW)
    if not cap.isOpened():
        print("[TRACKER] ERROR: Camera not found.")
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
    cap.set(cv2.CAP_PROP_EXPOSURE, CAMERA_EXPOSURE)

    csrt_tracker = None
    is_tracking = False
    prev_gray = None
    potential_target = None
    patience_counter = 0

    print("[TRACKER] Started. Press 'q' on the video window to stop, 'r' to reset.")

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                print("[TRACKER] Camera read failed.")
                break

            h, w = frame.shape[:2]
            frame_cx, frame_cy = w // 2, h // 2

            # ==================== מצב עקיבה ====================
            if is_tracking:
                success, box = csrt_tracker.update(frame)

                if success:
                    patience_counter = MAX_PATIENCE
                    x, y, bw, bh = [int(v) for v in box]
                    obj_x = x + bw // 2
                    obj_y = y + bh // 2

                    # חישוב שגיאה בדרגות
                    # ציר x: חיובי = יעד ימינה → Az חיובי
                    # ציר y: y גדל כלפי מטה, לכן הופך סימן → Alt חיובי
                    err_x_deg = (obj_x - frame_cx) * pixel_scale
                    err_y_deg = (frame_cy - obj_y) * pixel_scale

                    rate_az  = pid_az.update(err_x_deg)
                    rate_alt = pid_alt.update(err_y_deg)

                    try:
                        scope.MoveAxis(0, rate_az)
                        scope.MoveAxis(1, rate_alt)
                    except Exception as e:
                        print(f"[TRACKER] Mount error: {e}")

                    # ציור
                    cv2.rectangle(frame, (x, y), (x + bw, y + bh), (0, 255, 0), 2)
                    cv2.circle(frame, (obj_x, obj_y), 4, (0, 0, 255), -1)
                    cv2.line(frame, (frame_cx, frame_cy), (obj_x, obj_y), (0, 255, 255), 1)
                    err_as_x = int(err_x_deg * 3600)
                    err_as_y = int(err_y_deg * 3600)
                    cv2.putText(frame, f"LOCKED  err=({err_as_x}\", {err_as_y}\")",
                                (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                    cv2.putText(frame, f"Rate Az={rate_az:.2f} Alt={rate_alt:.2f} deg/s",
                                (10, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 220, 0), 1)

                else:
                    patience_counter -= 1
                    cv2.putText(frame, f"LOST... patience={patience_counter}",
                                (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 165, 255), 2)

                    if patience_counter <= 0:
                        _stop_mount(scope)
                        pid_az.reset()
                        pid_alt.reset()
                        is_tracking = False
                        csrt_tracker = None
                        prev_gray = None
                        potential_target = None
                        print("[TRACKER] Target permanently lost. Rescanning...")

            # ==================== מצב סריקה ====================
            else:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                gray = cv2.GaussianBlur(gray, (21, 21), 0)

                if prev_gray is not None:
                    delta = cv2.absdiff(prev_gray, gray)
                    thresh = cv2.threshold(delta, 25, 255, cv2.THRESH_BINARY)[1]
                    thresh = cv2.dilate(thresh, None, iterations=2)
                    contours, _ = cv2.findContours(
                        thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
                    )

                    valid = [c for c in contours if cv2.contourArea(c) > MIN_CONTOUR_AREA]
                    best = max(valid, key=cv2.contourArea, default=None)

                    if best is not None:
                        x, y, bw, bh = cv2.boundingRect(best)
                        center = (x + bw // 2, y + bh // 2)

                        if potential_target is not None:
                            dist = math.hypot(
                                center[0] - potential_target[0],
                                center[1] - potential_target[1]
                            )
                            cv2.rectangle(frame, (x, y), (x + bw, y + bh), (255, 100, 0), 2)

                            if dist > MOVEMENT_THRESHOLD:
                                csrt_tracker = cv2.TrackerCSRT_create()
                                csrt_tracker.init(frame, (x, y, bw, bh))
                                is_tracking = True
                                patience_counter = MAX_PATIENCE
                                print(f"[TRACKER] Locked! movement={dist:.0f}px")

                        potential_target = center
                    else:
                        potential_target = None
                        cv2.putText(frame, "Scanning...",
                                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 200), 2)

                prev_gray = gray

            # ==================== ציור כללי ====================
            cv2.line(frame, (frame_cx, 0), (frame_cx, h), (80, 80, 80), 1)
            cv2.line(frame, (0, frame_cy), (w, frame_cy), (80, 80, 80), 1)
            cv2.imshow("TelescopeAI Tracker", frame)

            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            if key == ord('r'):
                _stop_mount(scope)
                pid_az.reset()
                pid_alt.reset()
                is_tracking = False
                csrt_tracker = None
                potential_target = None
                print("[TRACKER] Manual reset.")

    finally:
        _stop_mount(scope)
        cap.release()
        cv2.destroyAllWindows()
        print("[TRACKER] Stopped.")


def _stop_mount(scope):
    """עצור את שני צירי המנוע בצורה בטוחה."""
    try:
        scope.MoveAxis(0, 0)
        scope.MoveAxis(1, 0)
    except Exception:
        pass
