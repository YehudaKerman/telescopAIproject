"""
camera/opencv_camera.py — OpenCV webcam / USB camera driver

Works on Windows (CAP_DSHOW) and Linux (CAP_V4L2).
The backend is selected automatically based on the platform.

Usage:
    from camera.opencv_camera import OpenCVCamera
    cam = OpenCVCamera(index=0, width=640, height=480, exposure=-6)
    cam.open()
    ret, frame = cam.read()          # BGR numpy array
    cam.release()
"""
import sys
import cv2
import numpy as np
from camera.base import CameraDriver
from utils.logger import get_logger

logger = get_logger(__name__)

# CAP_DSHOW on Windows avoids the slow MSMF backend
_BACKEND = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_V4L2


class OpenCVCamera(CameraDriver):
    """
    Thin wrapper around cv2.VideoCapture.

    Args:
        index:    Device index (0 = first camera).
        width:    Requested frame width in pixels.
        height:   Requested frame height in pixels.
        exposure: cv2.CAP_PROP_EXPOSURE value (negative = short, e.g. -6).
                  Set to None to leave at camera default.
    """

    def __init__(
        self,
        index: int = 0,
        width: int = 640,
        height: int = 480,
        exposure: int | None = -6,
    ) -> None:
        self._index    = index
        self._width    = width
        self._height   = height
        self._exposure = exposure
        self._cap: cv2.VideoCapture | None = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def open(self) -> None:
        logger.info("[OpenCV] Opening camera index=%d (%dx%d)", self._index, self._width, self._height)
        cap = cv2.VideoCapture(self._index, _BACKEND)
        if not cap.isOpened():
            raise RuntimeError(f"[OpenCV] Camera index {self._index} could not be opened")

        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  self._width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._height)
        if self._exposure is not None:
            cap.set(cv2.CAP_PROP_EXPOSURE, self._exposure)

        self._cap = cap
        logger.info("[OpenCV] Camera opened  actual=%dx%d",
                    int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                    int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))

    def release(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None
            logger.info("[OpenCV] Camera released")

    @property
    def is_opened(self) -> bool:
        return self._cap is not None and self._cap.isOpened()

    # ── Frame acquisition ─────────────────────────────────────────────────────

    def read(self) -> tuple[bool, np.ndarray]:
        if self._cap is None:
            return False, np.empty(0, dtype=np.uint8)
        ret, frame = self._cap.read()
        if not ret:
            logger.warning("[OpenCV] Frame grab failed")
        return ret, frame

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def width(self) -> int:
        if self._cap and self._cap.isOpened():
            return int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        return self._width

    @property
    def height(self) -> int:
        if self._cap and self._cap.isOpened():
            return int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        return self._height
