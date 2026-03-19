"""
core/session.py — TelescopeSession

High-level context manager that owns the scope + camera lifecycle.
Use this in main.py and scripts so connect/disconnect never leak.

Usage:
    from utils.config import load_config
    from core.session import TelescopeSession

    cfg = load_config()
    with TelescopeSession(cfg) as session:
        session.slew_to("North", az=0.0, alt=10.0)
        session.start_tracking()

Or manually (for interactive scripts):
    session = TelescopeSession(cfg)
    session.open()
    ...
    session.close()
"""
import time
import threading
from hardware import driver_factory
from hardware.base import TelescopeDriver
from camera import camera_factory
from camera.base import CameraDriver
from utils.logger import get_logger

logger = get_logger(__name__)

MIN_SAFE_ALTITUDE = 10.0   # degrees — never slew below this


class TelescopeSession:
    """
    Owns a TelescopeDriver + CameraDriver pair and provides
    safe, high-level operations on top of them.

    Args:
        cfg: Full config dict as returned by load_config().
    """

    def __init__(self, cfg: dict) -> None:
        self._cfg    = cfg
        self.scope:  TelescopeDriver = driver_factory(cfg)
        self.camera: CameraDriver    = camera_factory(cfg)

    # ── Context manager ───────────────────────────────────────────────────────

    def __enter__(self) -> "TelescopeSession":
        self.open()
        return self

    def __exit__(self, *_) -> None:
        self.close()

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def open(self) -> None:
        """Connect scope and open camera."""
        logger.info("[SESSION] Opening scope (%s) ...",
                    self._cfg.get("mount", {}).get("backend", "?"))
        self.scope.connect()
        if self.scope.at_park:
            self.scope.unpark()

        logger.info("[SESSION] Opening camera (%s) ...",
                    self._cfg.get("camera", {}).get("backend", "?"))
        self.camera.open()
        logger.info("[SESSION] Ready")

    def close(self) -> None:
        """Stop mount, release camera, disconnect scope."""
        logger.info("[SESSION] Closing...")
        try:
            self.scope.abort_slew()
        except Exception:
            pass
        try:
            self.camera.release()
        except Exception:
            pass
        try:
            self.scope.disconnect()
        except Exception:
            pass
        logger.info("[SESSION] Closed")

    # ── Safe slew ─────────────────────────────────────────────────────────────

    def slew_to(
        self,
        name: str,
        az: float,
        alt: float,
        allow_abort: bool = True,
    ) -> bool:
        """
        Slew to (az, alt) with altitude safety check.

        Prints a countdown and lets the user type 'stop' + Enter to abort.

        Args:
            name:        Human-readable target name for log messages.
            az:          Target azimuth in degrees.
            alt:         Target altitude in degrees.
            allow_abort: If True, a background thread listens for 'stop'.

        Returns:
            True if the mount arrived, False if aborted or error.
        """
        if alt < MIN_SAFE_ALTITUDE:
            logger.error("[SESSION] Slew to %s aborted — Alt=%.1f° < min %.1f°",
                         name, alt, MIN_SAFE_ALTITUDE)
            print(f"ERROR: Alt={alt:.1f}° is below safe limit ({MIN_SAFE_ALTITUDE}°). Aborted.")
            return False

        logger.info("[SESSION] Slewing to %s  Az=%.2f  Alt=%.2f", name, az, alt)
        print(f"\n>>> Moving to {name} (Az: {az:.2f}, Alt: {alt:.2f})...")

        try:
            if not self.scope.tracking:
                self.scope.tracking = True
            self.scope.slew_to_altaz_async(az, alt)
            time.sleep(1.0)

            stop_flag: list[bool] = []

            if allow_abort:
                def _listen():
                    print("   [Type 'stop' + Enter to ABORT, or wait for arrival]")
                    if input().strip().lower() == "stop":
                        stop_flag.append(True)

                t = threading.Thread(target=_listen, daemon=True)
                t.start()

            while self.scope.slewing:
                if stop_flag:
                    print("\n!!! STOP COMMAND RECEIVED !!!")
                    self.scope.abort_slew()
                    logger.warning("[SESSION] Slew to %s aborted by user", name)
                    return False
                time.sleep(0.2)

            logger.info("[SESSION] Arrived at %s", name)
            print(f"\n[✓] Reached {name}.")
            print("(Press Enter to continue...)")
            return True

        except Exception as exc:
            logger.error("[SESSION] Slew error: %s", exc)
            print(f"Error during movement: {exc}")
            try:
                self.scope.abort_slew()
            except Exception:
                pass
            return False

    # ── Tracking ──────────────────────────────────────────────────────────────

    def start_tracking(self) -> None:
        """
        Hand off to the camera tracker loop.
        Blocks until the user presses 'q' in the video window.
        """
        from core.tracker import start_tracking as _track
        logger.info("[SESSION] Starting camera tracker")
        _track(self.scope, self.camera, self._cfg)
