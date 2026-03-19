"""
camera/__init__.py — Camera backend factory

Selects and constructs the correct CameraDriver based on config.yaml.

    camera:
      backend: "opencv"   # "opencv" | "zwo" | "mock"
      index: 0
      exposure: -6
      width: 640
      height: 480

Usage:
    from utils.config import load_config
    from camera import camera_factory
    cfg = load_config()
    cam = camera_factory(cfg)
    cam.open()
"""
from camera.base import CameraDriver


def camera_factory(cfg: dict) -> CameraDriver:
    """
    Instantiate the camera driver specified in cfg['camera']['backend'].

    Args:
        cfg: Full config dict as returned by load_config().

    Returns:
        An unopened CameraDriver instance.

    Raises:
        ValueError: if cfg['camera']['backend'] is not recognised.
    """
    camera_cfg = cfg.get("camera", {})
    backend    = camera_cfg.get("backend", "opencv").lower()

    if backend == "opencv":
        from camera.opencv_camera import OpenCVCamera
        return OpenCVCamera(
            index=camera_cfg.get("index", 0),
            width=camera_cfg.get("width", 640),
            height=camera_cfg.get("height", 480),
            exposure=camera_cfg.get("exposure", -6),
        )

    if backend == "zwo":
        from camera.zwo_camera import ZWOCamera
        return ZWOCamera(
            camera_index=camera_cfg.get("index", 0),
            width=camera_cfg.get("width", 640),
            height=camera_cfg.get("height", 480),
            exposure_us=camera_cfg.get("exposure_us", 10_000),
            gain=camera_cfg.get("gain", 100),
            sdk_path=camera_cfg.get("sdk_path", "ASICamera2.dll"),
        )

    if backend == "mock":
        from camera.mock_camera import MockCamera
        return MockCamera(
            width=camera_cfg.get("width", 640),
            height=camera_cfg.get("height", 480),
        )

    raise ValueError(
        f"Unknown camera backend '{backend}'. "
        "Valid options: 'opencv', 'zwo', 'mock'."
    )


__all__ = ["CameraDriver", "camera_factory"]
