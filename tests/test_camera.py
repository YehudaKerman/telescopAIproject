"""
tests/test_camera.py — Unit tests for the camera abstraction layer

All tests use MockCamera — no physical camera required.
Run with: pytest tests/test_camera.py -v
"""
import numpy as np
import pytest
from camera.mock_camera import MockCamera
from camera import camera_factory


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def cam() -> MockCamera:
    c = MockCamera(width=640, height=480)
    c.open()
    return c


# ── Lifecycle ─────────────────────────────────────────────────────────────────

def test_open_sets_is_opened():
    c = MockCamera()
    assert not c.is_opened
    c.open()
    assert c.is_opened
    c.release()
    assert not c.is_opened


def test_release_is_safe_when_not_opened():
    c = MockCamera()
    c.release()   # must not raise


# ── Frame delivery ────────────────────────────────────────────────────────────

def test_read_returns_bgr_frame(cam):
    ret, frame = cam.read()
    assert ret is True
    assert isinstance(frame, np.ndarray)
    assert frame.dtype == np.uint8
    assert frame.shape == (480, 640, 3)


def test_read_increments_frame_count(cam):
    for i in range(5):
        cam.read()
    assert cam.frame_count == 5


def test_read_fails_when_not_opened():
    c = MockCamera()
    ret, frame = c.read()
    assert ret is False


# ── Dot motion ────────────────────────────────────────────────────────────────

def test_dot_position_changes_over_time(cam):
    pos0 = cam.dot_position()
    for _ in range(20):
        cam.read()
    pos1 = cam.dot_position()
    assert pos0 != pos1   # dot must have moved


def test_dot_stays_within_frame(cam):
    for _ in range(200):
        x, y = cam.dot_position()
        cam.read()
        assert 0 <= x < cam.width
        assert 0 <= y < cam.height


# ── Properties ───────────────────────────────────────────────────────────────

def test_width_height(cam):
    assert cam.width  == 640
    assert cam.height == 480


# ── Reset ────────────────────────────────────────────────────────────────────

def test_reset_returns_frame_count_to_zero(cam):
    for _ in range(10):
        cam.read()
    cam.reset()
    assert cam.frame_count == 0


# ── camera_factory ────────────────────────────────────────────────────────────

def test_camera_factory_mock():
    from utils.config import load_config
    cfg = load_config()
    cfg["camera"]["backend"] = "mock"
    c = camera_factory(cfg)
    c.open()
    ret, frame = c.read()
    assert ret is True
    assert frame.shape[2] == 3
    c.release()


def test_camera_factory_unknown_raises():
    from utils.config import load_config
    cfg = load_config()
    cfg["camera"]["backend"] = "ufo"
    with pytest.raises(ValueError, match="ufo"):
        camera_factory(cfg)
