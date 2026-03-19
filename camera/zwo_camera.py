"""
camera/zwo_camera.py — ZWO ASI183MC Pro driver

Wraps the zwoasi Python bindings (pip install zwoasi).
The ZWO ASI SDK DLL/SO must be installed separately.

SDK download: https://astronomy-imaging-camera.com/software-drivers

Usage:
    from camera.zwo_camera import ZWOCamera
    cam = ZWOCamera(
        camera_index=0,
        width=640, height=480,
        exposure_us=10000,   # 10 ms
        gain=100,
        sdk_path="ASICamera2.dll",   # Windows; on Linux: "libASICamera2.so"
    )
    cam.open()
    ret, frame = cam.read()   # BGR numpy array
    cam.release()

Notes:
    - Frames from the ASI183MC are 16-bit RAW Bayer by default.
      This driver configures 8-bit RGB24 output for simplicity so the
      returned array is standard BGR uint8 — same as OpenCVCamera.
    - If you need full 12-bit precision for imaging, subclass and override
      open() to set ASI_IMG_RAW16, then handle conversion yourself.
"""
import numpy as np
from camera.base import CameraDriver
from utils.logger import get_logger

logger = get_logger(__name__)


class ZWOCamera(CameraDriver):
    """
    ZWO ASI183MC (and compatible ASI cameras) via the zwoasi package.

    Args:
        camera_index: Index of the ASI camera (0 = first detected).
        width:        ROI width in pixels.
        height:       ROI height in pixels.
        exposure_us:  Exposure time in microseconds.
        gain:         Analogue gain (0–570 for ASI183MC).
        sdk_path:     Path to the ASI SDK library.
    """

    def __init__(
        self,
        camera_index: int = 0,
        width: int = 640,
        height: int = 480,
        exposure_us: int = 10_000,
        gain: int = 100,
        sdk_path: str = "ASICamera2.dll",
    ) -> None:
        self._camera_index = camera_index
        self._width        = width
        self._height       = height
        self._exposure_us  = exposure_us
        self._gain         = gain
        self._sdk_path     = sdk_path
        self._camera       = None   # zwoasi.Camera instance

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def open(self) -> None:
        try:
            import zwoasi as asi
        except ImportError as exc:
            raise RuntimeError(
                "zwoasi package not installed. Run: pip install zwoasi"
            ) from exc

        logger.info("[ZWO] Initialising SDK from %s", self._sdk_path)
        asi.init(self._sdk_path)

        num_cameras = asi.get_num_cameras()
        if num_cameras == 0:
            raise RuntimeError("[ZWO] No ASI cameras detected")
        if self._camera_index >= num_cameras:
            raise RuntimeError(
                f"[ZWO] Camera index {self._camera_index} out of range "
                f"(detected: {num_cameras})"
            )

        camera = asi.Camera(self._camera_index)
        camera_info = camera.get_camera_property()
        logger.info("[ZWO] Connected: %s", camera_info["Name"])

        camera.set_control_value(asi.ASI_EXPOSURE,    self._exposure_us)
        camera.set_control_value(asi.ASI_GAIN,        self._gain)
        camera.set_control_value(asi.ASI_BANDWIDTHOVERLOAD, 40)

        # 8-bit RGB24 output — easy to use as BGR with OpenCV
        camera.set_roi(width=self._width, height=self._height,
                       image_type=asi.ASI_IMG_RGB24)
        camera.start_video_capture()

        self._camera = camera
        logger.info("[ZWO] Video capture started  %dx%d  exp=%dµs  gain=%d",
                    self._width, self._height, self._exposure_us, self._gain)

    def release(self) -> None:
        if self._camera is not None:
            try:
                self._camera.stop_video_capture()
                self._camera.close()
            except Exception as exc:
                logger.warning("[ZWO] Error during release: %s", exc)
            finally:
                self._camera = None
                logger.info("[ZWO] Camera released")

    @property
    def is_opened(self) -> bool:
        return self._camera is not None

    # ── Frame acquisition ─────────────────────────────────────────────────────

    def read(self) -> tuple[bool, np.ndarray]:
        if self._camera is None:
            return False, np.empty(0, dtype=np.uint8)
        try:
            # get_video_data returns a flat uint8 array for RGB24
            data = self._camera.get_video_data()
            # Reshape to (H, W, 3) and convert RGB → BGR for OpenCV compatibility
            frame_rgb = data.reshape((self._height, self._width, 3))
            frame_bgr = frame_rgb[:, :, ::-1].copy()
            return True, frame_bgr
        except Exception as exc:
            logger.warning("[ZWO] Frame grab failed: %s", exc)
            return False, np.empty(0, dtype=np.uint8)

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def width(self) -> int:
        return self._width

    @property
    def height(self) -> int:
        return self._height
