"""
rpi/stream_server.py — MJPEG stream server (Raspberry Pi, headless)

Reads annotated frames from a thread-safe queue and streams them as MJPEG
over HTTP.  Windows client connects to http://kcg.local:<port>/video.

config.yaml (stream section):
    stream:
      port: 8080
      quality: 70    # JPEG quality 0-100
"""
import threading
import cv2
from flask import Flask, Response
from utils.logger import get_logger

logger = get_logger(__name__)


class StreamServer:
    """
    Flask-based MJPEG server.

    Frames are pushed into frame_queue by the tracker loop (via on_frame
    callback).  An internal encode thread pulls frames, compresses to JPEG,
    and stores the latest bytes under a lock.  The /video route generator
    yields multipart chunks to connected clients.

    Args:
        cfg:         Full config dict (reads cfg['stream']['port'] and ['quality']).
        frame_queue: queue.Queue instance shared with the tracker loop.
    """

    def __init__(self, cfg: dict, frame_queue) -> None:
        stream_cfg    = cfg.get("stream", {})
        self._port    = stream_cfg.get("port", 8080)
        self._quality = stream_cfg.get("quality", 70)
        self._queue   = frame_queue

        self._latest_jpeg = None
        self._lock        = threading.Lock()

        self._app = Flask(__name__)
        self._app.add_url_rule("/video", "video", self._video_feed)
        self._app.add_url_rule("/",      "index", self._index)

        encode_thread = threading.Thread(target=self._encode_loop, daemon=True)
        encode_thread.start()

    # ── Internal threads ──────────────────────────────────────────────────────

    def _encode_loop(self) -> None:
        """Pull frames from queue, compress to JPEG, store latest."""
        encode_params = [cv2.IMWRITE_JPEG_QUALITY, self._quality]
        while True:
            frame = self._queue.get()
            ok, buf = cv2.imencode(".jpg", frame, encode_params)
            if ok:
                with self._lock:
                    self._latest_jpeg = buf.tobytes()

    def _generate(self):
        """Generator that yields MJPEG chunks to HTTP clients."""
        while True:
            with self._lock:
                jpeg = self._latest_jpeg
            if jpeg:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
                )

    # ── Flask routes ──────────────────────────────────────────────────────────

    def _video_feed(self):
        return Response(
            self._generate(),
            mimetype="multipart/x-mixed-replace; boundary=frame",
        )

    def _index(self):
        return (
            "<html><body style='background:#000;margin:0'>"
            "<img src='/video' style='width:100%;height:100vh;object-fit:contain'>"
            "</body></html>"
        )

    # ── Entry point ───────────────────────────────────────────────────────────

    def run(self) -> None:
        """Start the Flask server (blocking — run in a background thread)."""
        logger.info("[STREAM] MJPEG server on http://0.0.0.0:%d/video", self._port)
        self._app.run(
            host="0.0.0.0",
            port=self._port,
            threaded=True,
            use_reloader=False,
        )
