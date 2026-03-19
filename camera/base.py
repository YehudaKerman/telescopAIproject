"""
camera/base.py — CameraDriver Abstract Base Class

Every camera backend (OpenCV, ZWO ASI, Mock) must implement this interface.
Code in tracker.py and calibration.py should only call these methods
— never touch cv2.VideoCapture or ZWO SDK objects directly.

Frame format:
    read() always returns a BGR numpy array (H x W x 3, dtype=uint8),
    matching OpenCV's native format.  If the camera delivers monochrome
    or raw Bayer frames, the driver is responsible for converting.

Usage:
    from camera.opencv_camera import OpenCVCamera
    cam = OpenCVCamera(index=0, width=640, height=480, exposure=-6)
    cam.open()
    ret, frame = cam.read()
    cam.release()
"""
from abc import ABC, abstractmethod
import numpy as np


class CameraDriver(ABC):
    """
    Platform-agnostic interface for a video/imaging camera.

    Concrete implementations: OpenCVCamera, ZWOCamera, MockCamera.
    """

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    @abstractmethod
    def open(self) -> None:
        """
        Open / initialise the camera hardware.

        Raises:
            RuntimeError: if the camera cannot be opened (device not found,
                          driver error, etc.)
        """

    @abstractmethod
    def release(self) -> None:
        """
        Release the camera and free resources.
        Safe to call even if not opened (should be a no-op).
        """

    @property
    @abstractmethod
    def is_opened(self) -> bool:
        """True if the camera is currently open and ready to deliver frames."""

    # ── Frame acquisition ─────────────────────────────────────────────────────

    @abstractmethod
    def read(self) -> tuple[bool, np.ndarray]:
        """
        Grab the next frame.

        Returns:
            (success, frame) where:
                success: False if the frame could not be read
                frame:   BGR numpy array shape (H, W, 3), dtype uint8
                         (undefined / empty array when success is False)
        """

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    @abstractmethod
    def width(self) -> int:
        """Frame width in pixels."""

    @property
    @abstractmethod
    def height(self) -> int:
        """Frame height in pixels."""
