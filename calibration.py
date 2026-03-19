#!/usr/bin/env python3
"""
calibration.py — TelescopeAI Calibration Wizard

Modes
-----
  pixel_scale   Auto-calibrate deg/pixel using phase correlation
                (moves mount, compares frames — no manual input needed)
  roll          Auto-calibrate camera rotation relative to mount Az axis
  align         Mount alignment on known GPS landmarks (1 or 2 points)
  full          Runs pixel_scale → roll → align in sequence

Usage
-----
  python calibration.py --mode full
  python calibration.py --mode pixel_scale
  python calibration.py --mode align --points 1

Results are written automatically to the [calibration] section of config.yaml
and also update [tracking].pixel_scale and [tracking].camera_roll_deg.
"""
import argparse
import math
import sys
import time
from datetime import datetime

import cv2
import numpy as np

from utils.config import load_config, save_config as _save_config
from utils.geometry import landmark_az_alt


def save_config(cfg: dict) -> None:
    _save_config(cfg)
    print("[OK] Results saved to config.yaml")


# ── hardware helpers ──────────────────────────────────────────────────────────

def connect_scope(driver: str):
    try:
        import win32com.client
        scope = win32com.client.Dispatch(driver)
        scope.Connected = True
        print(f"[OK] Mount connected ({driver})")
        return scope
    except Exception as exc:
        print(f"[ERROR] Cannot connect to mount: {exc}")
        return None


def open_camera(cfg: dict):
    cam = cfg["camera"]
    cap = cv2.VideoCapture(cam["index"], cv2.CAP_DSHOW)
    if not cap.isOpened():
        print("[ERROR] Camera not found.")
        return None
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  cam["width"])
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cam["height"])
    cap.set(cv2.CAP_PROP_EXPOSURE,     cam["exposure"])
    time.sleep(0.8)           # let AGC/AE settle
    return cap


def grab_gray(cap) -> np.ndarray:
    """Flush stale frames then return a fresh grayscale float32 image."""
    for _ in range(4):
        cap.read()
    ret, frame = cap.read()
    if not ret:
        raise RuntimeError("Camera read failed")
    return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32)


def stop_mount(scope) -> None:
    try:
        scope.MoveAxis(0, 0.0)
        scope.MoveAxis(1, 0.0)
    except Exception:
        pass


# ── visual helpers ────────────────────────────────────────────────────────────

def show_phase_result(gray1: np.ndarray, gray2: np.ndarray,
                      shift: tuple, title: str = "Phase Correlation") -> None:
    """Overlay before/after frames with a shift arrow.  Press Q to close."""
    h, w = gray1.shape
    overlay = np.zeros((h, w, 3), dtype=np.uint8)
    overlay[:, :, 0] = np.clip(gray1, 0, 255).astype(np.uint8)   # blue  = before
    overlay[:, :, 2] = np.clip(gray2, 0, 255).astype(np.uint8)   # red   = after
    cx, cy = w // 2, h // 2
    dx, dy = int(round(shift[0])), int(round(shift[1]))
    scale  = 5                                # amplify arrow for visibility
    cv2.arrowedLine(overlay,
                    (cx, cy),
                    (cx + dx * scale, cy + dy * scale),
                    (0, 255, 0), 2, tipLength=0.3)
    cv2.putText(overlay,
                f"shift: ({shift[0]:.2f}, {shift[1]:.2f}) px",
                (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 0), 2)
    cv2.putText(overlay,
                "Blue=before  Red=after  Green arrow=shift (x5)  Q=close",
                (10, h - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 180), 1)
    cv2.imshow(title, overlay)
    while cv2.waitKey(100) & 0xFF != ord("q"):
        pass
    cv2.destroyWindow(title)


# ── calibration modes ─────────────────────────────────────────────────────────

def calibrate_pixel_scale_and_roll(scope, cfg: dict) -> dict | None:
    """
    Single-move calibration: move MOVE_DEG in Az, capture before/after frames,
    use phase correlation to measure pixel shift.

    Returns dict with keys: pixel_scale, camera_roll_deg

    pixel_scale (deg/px):
        move_deg / hypot(dx, dy)

    camera_roll_deg:
        angle between mount Az axis and camera X-axis.
        Ideally 0° (or 180° depending on mount orientation).
        Used in tracker.py to decouple Az/Alt errors.
    """
    MOVE_DEG  = cfg["mount"]["calibration_move_deg"]
    RATE      = cfg["mount"]["move_rate_deg_per_sec"]
    MOVE_SEC  = MOVE_DEG / RATE
    MIN_SHIFT = 8.0   # pixels — reject measurement if shift is too small

    print("\n=== PIXEL SCALE + CAMERA ROLL ===")
    print(f"Will move {MOVE_DEG}° in Az at {RATE} deg/s ({MOVE_SEC:.1f}s).")
    print("Scene must have texture: buildings, trees, fence — NOT open sky.")
    input("Press Enter when ready...")

    cap = open_camera(cfg)
    if cap is None:
        return None

    results = {}
    try:
        # Frame BEFORE
        gray1 = grab_gray(cap)
        print(f"Frame 1 captured ({int(gray1.shape[1])}×{int(gray1.shape[0])} px)")

        # Move mount in Az
        print(f"Moving {MOVE_DEG}° Az...")
        scope.MoveAxis(0, float(RATE))
        time.sleep(MOVE_SEC)
        scope.MoveAxis(0, 0.0)
        time.sleep(0.6)   # mechanical settle

        # Frame AFTER
        gray2 = grab_gray(cap)

        # Phase correlation (Hann window reduces edge artifacts)
        hann  = cv2.createHanningWindow((gray1.shape[1], gray1.shape[0]), cv2.CV_32F)
        shift, response = cv2.phaseCorrelate(gray1, gray2, hann)
        dx, dy = shift
        pixel_shift = math.hypot(dx, dy)

        print(f"Phase correlation: dx={dx:.2f}px  dy={dy:.2f}px  "
              f"shift={pixel_shift:.2f}px  confidence={response:.4f}")

        if response < 0.005:
            print("[WARN] Very low confidence.  "
                  "Ensure the scene has high-contrast texture.")

        if pixel_shift < MIN_SHIFT:
            print(f"[ERROR] Shift {pixel_shift:.1f}px < {MIN_SHIFT}px minimum.  "
                  "Increase calibration_move_deg or check scene.")
            return None

        # pixel_scale
        pixel_scale = MOVE_DEG / pixel_shift

        # Camera roll: Az+ should shift image in -X (scene moves right).
        # Measured angle of shift vector; ideally ~180° (opposite to mount move).
        raw_roll = math.degrees(math.atan2(dy, dx))
        # Normalise to [-90, +90]: how many degrees the camera is rotated
        # relative to mount Az axis.
        camera_roll = raw_roll
        if camera_roll > 90:
            camera_roll -= 180
        elif camera_roll < -90:
            camera_roll += 180

        print()
        print(f"  pixel_scale   = {pixel_scale:.6f} deg/px  "
              f"({pixel_scale * 3600:.2f} arcsec/px)")
        print(f"  camera_roll   = {camera_roll:+.2f}°")
        if abs(camera_roll) < 2:
            print("  Roll: excellent alignment")
        elif abs(camera_roll) < 10:
            print("  Roll: minor — corrected in software")
        else:
            print("  Roll: large — consider physically rotating camera on telescope")

        # Visual confirmation
        show_phase_result(gray1, gray2, shift, "Pixel Scale — Phase Correlation")

        results["pixel_scale"]     = round(pixel_scale, 7)
        results["camera_roll_deg"] = round(camera_roll, 3)

    finally:
        cap.release()
        cv2.destroyAllWindows()

    return results or None


def calibrate_alignment(scope, cfg: dict, n_points: int) -> dict | None:
    """
    Mount alignment on n_points known GPS landmarks.

    n_points=1  — quick single sync (SyncToAltAz on one landmark)
    n_points=2  — two-point alignment; measures mean Az/Alt offset and reports
                  potential level and North-pointing errors.

    Writes: az_offset_deg, alt_offset_deg
    Calls SyncToAltAz on the last chosen landmark.
    """
    obs       = cfg["location"]
    landmarks = cfg.get("landmarks", [])

    if not landmarks:
        print("[ERROR] No landmarks in config.yaml.  "
              "Run: python find_landmarks.py --add")
        return None

    print(f"\n=== MOUNT ALIGNMENT ({n_points}-point) ===")
    print(f"{'#':>2}  {'Name':30s}  {'Az':>7}  {'Alt':>7}  {'Dist':>8}")
    print("-" * 62)
    rows = []
    for i, lm in enumerate(landmarks):
        az, alt, dist = landmark_az_alt(obs, lm)
        rows.append((az, alt, dist))
        print(f"{i+1:>2}. {lm['name']:30s}  {az:7.2f}°  {alt:+7.2f}°  {dist/1000:6.2f}km")

    measurements = []

    for pt in range(n_points):
        print(f"\n--- Point {pt + 1} of {n_points} ---")
        choice = int(input(f"Enter landmark number (1-{len(landmarks)}): ")) - 1
        if not 0 <= choice < len(landmarks):
            print("Invalid choice.")
            return None

        lm               = landmarks[choice]
        az_calc, alt_calc, dist = landmark_az_alt(obs, lm)

        print(f"\nTarget: '{lm['name']}'")
        print(f"  Az  = {az_calc:.3f}°   (0=N  90=E  180=S  270=W)")
        print(f"  Alt = {alt_calc:+.3f}°  (includes atmospheric refraction)")
        print(f"  Dist= {dist / 1000:.2f} km")
        print()
        print("  Physically centre this target in the eyepiece / camera frame.")
        input("  Press Enter when centred...")

        az_mount  = scope.Azimuth
        alt_mount = scope.Altitude

        az_err  = az_calc  - az_mount
        alt_err = alt_calc - alt_mount
        measurements.append({
            "name":     lm["name"],
            "az_calc":  az_calc,
            "alt_calc": alt_calc,
            "az_mount":  az_mount,
            "alt_mount": alt_mount,
        })

        print(f"  Mount reads:   Az={az_mount:.3f}°  Alt={alt_mount:.3f}°")
        print(f"  Calculated:    Az={az_calc:.3f}°   Alt={alt_calc:.3f}°")
        print(f"  Point error:   Az={az_err:+.3f}°  Alt={alt_err:+.3f}°")

    # Mean offsets
    n   = len(measurements)
    az_offset  = sum(m["az_calc"]  - m["az_mount"]  for m in measurements) / n
    alt_offset = sum(m["alt_calc"] - m["alt_mount"] for m in measurements) / n

    print()
    print("=== ALIGNMENT RESULT ===")
    print(f"  Az offset  (mean): {az_offset:+.3f}°")
    print(f"  Alt offset (mean): {alt_offset:+.3f}°")

    if abs(az_offset) > 5:
        print("  [WARN] Large Az offset — mount may not be parked pointing "
              "true North at startup.")
    if abs(alt_offset) > 2:
        print("  [WARN] Large Alt offset — check mount level with a spirit level.")
    if abs(az_offset) <= 1 and abs(alt_offset) <= 0.5:
        print("  [OK] Excellent alignment.")

    # Sync on last point
    last = measurements[-1]
    scope.SyncToAltAz(last["az_calc"], last["alt_calc"])
    print(f"\n[OK] SyncToAltAz({last['az_calc']:.3f}°, {last['alt_calc']:.3f}°) sent.")

    return {"az_offset_deg": round(az_offset, 4),
            "alt_offset_deg": round(alt_offset, 4)}


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="TelescopeAI Calibration Wizard")
    parser.add_argument(
        "--mode",
        choices=["pixel_scale", "roll", "align", "full"],
        default="full",
        help="Calibration mode (default: full)",
    )
    parser.add_argument(
        "--points",
        type=int,
        default=2,
        choices=[1, 2],
        help="Number of alignment landmarks (default: 2)",
    )
    args = parser.parse_args()

    cfg   = load_config()
    scope = connect_scope(cfg["mount"]["driver"])
    if scope is None:
        sys.exit(1)

    results: dict = {}

    try:
        # ── pixel scale + roll ────────────────────────────────────────────────
        if args.mode in ("pixel_scale", "roll", "full"):
            r = calibrate_pixel_scale_and_roll(scope, cfg)
            if r:
                if args.mode in ("pixel_scale", "full"):
                    results["pixel_scale"] = r["pixel_scale"]
                if args.mode in ("roll", "full"):
                    results["camera_roll_deg"] = r["camera_roll_deg"]

        # ── mount alignment ───────────────────────────────────────────────────
        if args.mode in ("align", "full"):
            r = calibrate_alignment(scope, cfg, n_points=args.points)
            if r:
                results.update(r)

    finally:
        stop_mount(scope)

    # ── persist results ───────────────────────────────────────────────────────
    if not results:
        print("\n[WARN] No results to save.")
        return

    if "calibration" not in cfg or cfg["calibration"] is None:
        cfg["calibration"] = {}

    cfg["calibration"].update(results)
    cfg["calibration"]["calibrated_at"] = datetime.now().isoformat(timespec="minutes")
    cfg["calibration"]["method"]        = args.mode

    # Mirror into tracking section so tracker.py picks them up immediately
    if "pixel_scale" in results:
        cfg["tracking"]["pixel_scale"] = results["pixel_scale"]
    if "camera_roll_deg" in results:
        cfg["tracking"]["camera_roll_deg"] = results["camera_roll_deg"]

    save_config(cfg)

    print("\n=== CALIBRATION SUMMARY ===")
    for k, v in results.items():
        print(f"  {k}: {v}")
    print()
    print("Next step: python main.py")


if __name__ == "__main__":
    main()
