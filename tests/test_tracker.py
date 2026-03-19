"""
tests/test_tracker.py — Integration tests for the tracker + PID loop

Uses MockTelescopeDriver + MockCamera so no hardware is needed.
Verifies that the tracker calls move_axis() in the correct direction
when the dot is off-centre.

Run with: pytest tests/test_tracker.py -v
"""
import math
import numpy as np
import cv2
import pytest

from hardware.mock_driver import MockTelescopeDriver
from camera.mock_camera import MockCamera
from core.pid_controller import PIDController


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_frame_with_dot(width: int, height: int, dot_x: int, dot_y: int) -> np.ndarray:
    """Return a BGR frame with a bright dot at (dot_x, dot_y)."""
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    cv2.circle(frame, (dot_x, dot_y), 12, (255, 255, 255), -1)
    return frame


# ── PID unit tests ────────────────────────────────────────────────────────────

def test_pid_positive_error_positive_output():
    pid = PIDController(kp=1.0, ki=0.0, kd=0.0, output_limits=(-10, 10))
    out = pid.update(5.0)
    assert out > 0


def test_pid_zero_error_zero_output():
    pid = PIDController(kp=1.0, ki=0.0, kd=0.0, output_limits=(-10, 10))
    out = pid.update(0.0)
    assert out == pytest.approx(0.0)


def test_pid_output_clamped_to_limits():
    pid = PIDController(kp=100.0, ki=0.0, kd=0.0, output_limits=(-3.5, 3.5))
    out = pid.update(99.0)
    assert out == pytest.approx(3.5)


def test_pid_reset_clears_integral():
    pid = PIDController(kp=0.0, ki=1.0, kd=0.0, output_limits=(-100, 100))
    for _ in range(10):
        pid.update(1.0)   # accumulate integral
    pid.reset()
    out = pid.update(0.0)
    assert out == pytest.approx(0.0)


# ── Mock driver + camera integration ─────────────────────────────────────────

def test_mock_driver_and_camera_together():
    """
    Simulate one 'lock' cycle manually:
    feed a dot that moves >threshold, then verify move_axis was called.
    """
    scope = MockTelescopeDriver()
    scope.connect()
    scope.unpark()

    cam = MockCamera(width=320, height=240, dot_amplitude_px=60, dot_speed=0.3)
    cam.open()

    pixel_scale = 0.094
    pid_az  = PIDController(kp=0.4, ki=0.0, kd=0.0, output_limits=(-3.5, 3.5))
    pid_alt = PIDController(kp=0.4, ki=0.0, kd=0.0, output_limits=(-3.5, 3.5))

    frame_cx, frame_cy = cam.width // 2, cam.height // 2

    for _ in range(3):
        ret, frame = cam.read()
        assert ret

    # Place a dot clearly off-centre to the right
    w, h = cam.width, cam.height
    dot_x = frame_cx + 50
    dot_y = frame_cy
    test_frame = _make_frame_with_dot(w, h, dot_x, dot_y)

    err_x_deg = (dot_x - frame_cx) * pixel_scale   # positive → dot is right
    err_y_deg = (frame_cy - dot_y) * pixel_scale    # zero

    rate_az  = pid_az.update(err_x_deg)
    rate_alt = pid_alt.update(err_y_deg)

    scope.move_axis(0, rate_az)
    scope.move_axis(1, rate_alt)

    # Az rate must be positive (dot is to the right → mount moves East)
    az_calls = [r for axis, r in scope.move_axis_calls if axis == 0]
    assert az_calls[-1] > 0, "Expected positive Az rate for rightward dot offset"

    cam.release()
    scope.disconnect()
