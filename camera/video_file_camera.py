"""
camera/video_file_camera.py — Video File Camera Backend

Reads frames from a local video file (MP4, AVI, etc.) and throttles
playback to the file's native FPS, so the tracker receives frames at
the same rate it would from a real camera.

Usage (via config.yaml):

    camera:
      backend: "video_file"
      video_path: "/home/kcg/sim_videos/drone.mp4"
      loop: true          # restart from beginning when file ends (default: true)
      fps_override: null  # force a specific FPS; null = use file's native FPS

Or directly:

    from camera.video_file_camera import VideoFileCamera
    cam = VideoFileCamera("/path/to/video.mp4", loop=True)
    cam.open()
    ret, frame = cam.read()
    cam.release()
"""
import time

import cv2

from camera.base import CameraDriver
from utils.logger import get_logger

logger = get_logger(__name__)


class VideoFileCamera(CameraDriver):
    """
    CameraDriver that reads frames from a video file at the file's native FPS.

    FPS throttling is applied inside read() so that the tracker loop
    receives frames at realistic intervals — identical to a real camera feed.

    Args:
        path:         Path to the video file (MP4, AVI, MOV, …).
        loop:         If True, rewind and restart when the file ends.
        fps_override: Force a specific FPS (float). None = use file's native FPS.
    """

    def __init__(self, path: str, loop: bool = True, fps_override: float | None = None) -> None:
        self._path = path
        self._loop = loop
        self._fps_override = fps_override
        self._cap: cv2.VideoCapture | None = None
        self._width = 0
        self._height = 0
        self._frame_interval = 0.0   # seconds between frames (set in open())
        self._next_frame_time = 0.0  # monotonic deadline for next frame

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def open(self) -> None:
        self._cap = cv2.VideoCapture(self._path)
        if not self._cap.isOpened():
            raise RuntimeError(f"[VIDEO_CAM] Cannot open video file: {self._path}")

        self._width  = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self._height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        native_fps = self._cap.get(cv2.CAP_PROP_FPS) or 25.0
        fps = self._fps_override if self._fps_override else native_fps
        self._frame_interval = 1.0 / fps
        self._next_frame_time = time.monotonic()

        total_frames = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration_s   = total_frames / fps if fps else 0

        logger.info(
            "[VIDEO_CAM] Opened '%s'  %dx%d  %.1f fps  %d frames (%.1fs)%s",
            self._path, self._width, self._height, fps,
            total_frames, duration_s,
            "  [loop]" if self._loop else "",
        )

    def release(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        logger.info("[VIDEO_CAM] Released")

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def is_opened(self) -> bool:
        return self._cap is not None and self._cap.isOpened()

    @property
    def width(self) -> int:
        return self._width

    @property
    def height(self) -> int:
        return self._height

    # ── Frame delivery ────────────────────────────────────────────────────────

    def read(self) -> tuple[bool, cv2.typing.MatLike | None]:
        """
        Return the next frame, sleeping until the correct wall-clock time
        so that playback matches the video's native FPS.

        Returns:
            (True, frame)  — BGR numpy array, uint8
            (False, None)  — end of file and loop=False
        """
        if self._cap is None:
            return False, None

        # Throttle to FPS
        now = time.monotonic()
        wait = self._next_frame_time - now
        if wait > 0:
            time.sleep(wait)
        self._next_frame_time = time.monotonic() + self._frame_interval

        ret, frame = self._cap.read()

        if not ret:
            if not self._loop:
                logger.info("[VIDEO_CAM] End of file — stopping")
                return False, None
            # Rewind
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = self._cap.read()
            if not ret:
                logger.error("[VIDEO_CAM] Rewind failed — cannot read first frame")
                return False, None
            logger.debug("[VIDEO_CAM] Looped back to start")

        return True, frame
