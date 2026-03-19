"""
camera/mock_camera.py — Synthetic frame generator for PID / tracker testing

Generates BGR frames containing a bright dot that moves sinusoidally,
simulating a star or target drifting across the field of view.
No hardware required.

Usage:
    from camera.mock_camera import MockCamera
    cam = MockCamera(width=640, height=480, dot_amplitude_px=80, dot_speed=0.05)
    cam.open()
    ret, frame = cam.read()   # BGR numpy array with a glowing dot
    cam.release()

Test inspection:
    cam.frame_count          # total frames delivered
    cam.dot_position()       # current (x, y) pixel coords of the dot
    cam.reset()              # reset frame counter and dot position
"""
import math
import numpy as np
from camera.base import CameraDriver
from utils.logger import get_logger

logger = get_logger(__name__)


class MockCamera(CameraDriver):
    """
    Synthetic camera that produces frames with a moving bright dot.

    The dot follows a Lissajous path so it exercises both Az and Alt axes
    independently, which is useful for validating PID tracking.

    Args:
        width:            Frame width in pixels.
        height:           Frame height in pixels.
        dot_amplitude_px: Maximum displacement from centre (pixels).
        dot_speed:        Phase increment per frame (radians).
                          Higher = faster drift.
        dot_radius:       Radius of the synthetic dot (pixels).
        noise_level:      0–255, additive Gaussian noise intensity.
    """

    def __init__(
        self,
        width: int = 640,
        height: int = 480,
        dot_amplitude_px: int = 80,
        dot_speed: float = 0.05,
        dot_radius: int = 8,
        noise_level: int = 15,
    ) -> None:
        self._width           = width
        self._height          = height
        self._amplitude       = dot_amplitude_px
        self._speed           = dot_speed
        self._dot_radius      = dot_radius
        self._noise_level     = noise_level
        self._opened          = False
        self.frame_count      = 0

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def open(self) -> None:
        self._opened    = True
        self.frame_count = 0
        logger.info("[MOCK CAM] opened  %dx%d  amp=%dpx  speed=%.3f",
                    self._width, self._height, self._amplitude, self._speed)

    def release(self) -> None:
        self._opened = False
        logger.info("[MOCK CAM] released  (delivered %d frames)", self.frame_count)

    @property
    def is_opened(self) -> bool:
        return self._opened

    # ── Frame acquisition ─────────────────────────────────────────────────────

    def read(self) -> tuple[bool, np.ndarray]:
        if not self._opened:
            return False, np.empty(0, dtype=np.uint8)

        phase = self.frame_count * self._speed
        cx = self._width  // 2 + int(self._amplitude * math.sin(phase))
        cy = self._height // 2 + int(self._amplitude * math.sin(phase * 1.3 + 1.0))

        # Dark background with optional noise
        frame = np.zeros((self._height, self._width, 3), dtype=np.uint8)
        if self._noise_level > 0:
            noise = np.random.randint(0, self._noise_level,
                                      (self._height, self._width, 3), dtype=np.uint8)
            frame = noise

        # Draw glowing dot using radial brightness falloff
        r = self._dot_radius
        y0, y1 = max(0, cy - r), min(self._height, cy + r + 1)
        x0, x1 = max(0, cx - r), min(self._width,  cx + r + 1)
        for y in range(y0, y1):
            for x in range(x0, x1):
                dist = math.hypot(x - cx, y - cy)
                if dist <= r:
                    brightness = int(255 * (1.0 - dist / r) ** 2)
                    frame[y, x] = [brightness, brightness, 255]  # BGR white-ish dot

        self.frame_count += 1
        return True, frame

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def width(self) -> int:
        return self._width

    @property
    def height(self) -> int:
        return self._height

    # ── Test helpers ──────────────────────────────────────────────────────────

    def dot_position(self) -> tuple[int, int]:
        """Return the (x, y) pixel position of the dot in the *next* frame."""
        phase = self.frame_count * self._speed
        x = self._width  // 2 + int(self._amplitude * math.sin(phase))
        y = self._height // 2 + int(self._amplitude * math.sin(phase * 1.3 + 1.0))
        return x, y

    def reset(self) -> None:
        """Reset frame counter — dot returns to near-centre."""
        self.frame_count = 0
