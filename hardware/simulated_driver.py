"""
hardware/simulated_driver.py — Simulated Telescope Mount

Replaces the real ASCOM/INDI mount during video-based simulation.
Integrates move_axis() rate commands over real wall-clock time to
accumulate a pointing offset, which can be queried as a pixel offset
for visual overlay in main_sim.py.

Mental model:
    - Telescope starts pointing at frame centre (offset = 0, 0).
    - Tracker sends move_axis(0, +rate_az) → telescope moves right.
    - get_pixel_offset() returns (dx, dy) so main_sim can draw a crosshair
      that represents where the telescope is now pointing.
    - Goal of the simulation: crosshair converges on the tracked object.

Axis convention (matches ASCOM / INDI drivers):
    axis 0 = Az   positive rate → telescope moves right  (dx > 0)
    axis 1 = Alt  positive rate → telescope moves up     (dy < 0, screen-inverted)
"""
import threading
import time

from hardware.base import TelescopeDriver
from utils.logger import get_logger

logger = get_logger(__name__)


class SimulatedDriver(TelescopeDriver):
    """
    Physics-aware mount simulator.

    Thread-safe: move_axis() is typically called from the tracker thread
    while get_pixel_offset() is called from the streaming/overlay thread.
    """

    def __init__(self) -> None:
        self._connected       = False
        self._at_park         = True
        self._tracking        = False
        self._tracking_rate   = 0
        self._azimuth         = 0.0
        self._altitude        = 0.0

        # Accumulated pointing offset from start position (degrees)
        self._az_offset_deg   = 0.0
        self._alt_offset_deg  = 0.0

        # Current commanded rates (degrees/second)
        self._az_rate         = 0.0
        self._alt_rate        = 0.0

        self._last_tick: float | None = None
        self._lock = threading.Lock()

        # Call history for logging / tests
        self.move_axis_calls: list[tuple[int, float]] = []

    # ── Connection lifecycle ──────────────────────────────────────────────────

    def connect(self) -> None:
        self._connected = True
        self._last_tick = time.monotonic()
        logger.info("[SIM] connect() — simulated mount ready")

    def disconnect(self) -> None:
        self._connected = False
        logger.info("[SIM] disconnect()")

    @property
    def is_connected(self) -> bool:
        return self._connected

    # ── State properties ──────────────────────────────────────────────────────

    @property
    def at_park(self) -> bool:
        return self._at_park

    @property
    def slewing(self) -> bool:
        return False   # simulated mount never "slews" — just moves

    @property
    def tracking(self) -> bool:
        return self._tracking

    @tracking.setter
    def tracking(self, value: bool) -> None:
        self._tracking = value

    @property
    def tracking_rate(self) -> int:
        return self._tracking_rate

    @tracking_rate.setter
    def tracking_rate(self, rate: int) -> None:
        self._tracking_rate = rate

    @property
    def azimuth(self) -> float:
        return self._azimuth

    @property
    def altitude(self) -> float:
        return self._altitude

    # ── Motion commands ───────────────────────────────────────────────────────

    def unpark(self) -> None:
        self._at_park = False
        logger.debug("[SIM] unpark()")

    def slew_to_altaz_async(self, az: float, alt: float) -> None:
        # Not meaningful in simulation — log and ignore
        logger.debug("[SIM] slew_to_altaz_async(%.2f, %.2f) — ignored in sim mode", az, alt)

    def move_axis(self, axis: int, rate: float) -> None:
        """
        Record a rate command and integrate elapsed time into the offset.

        Called by the tracker thread on every frame (typically 20–30 Hz).
        """
        with self._lock:
            now = time.monotonic()

            # Integrate the previous rates over the elapsed interval
            if self._last_tick is not None:
                dt = now - self._last_tick
                self._az_offset_deg  += self._az_rate  * dt
                self._alt_offset_deg += self._alt_rate * dt

            self._last_tick = now

            if axis == 0:
                self._az_rate = rate
            elif axis == 1:
                self._alt_rate = rate

            self.move_axis_calls.append((axis, rate))

            logger.debug(
                "[SIM] move_axis(axis=%d, rate=%+.4f)  offset=(Az %+.4f°, Alt %+.4f°)",
                axis, rate, self._az_offset_deg, self._alt_offset_deg,
            )

    def abort_slew(self) -> None:
        with self._lock:
            self._az_rate  = 0.0
            self._alt_rate = 0.0

    def sync_to_altaz(self, az: float, alt: float) -> None:
        self._azimuth  = az
        self._altitude = alt

    # ── Simulation query interface ────────────────────────────────────────────

    def get_pixel_offset(self, pixel_scale: float) -> tuple[int, int]:
        """
        Current telescope pointing expressed as pixel offset from frame centre.

        Also accounts for rates that are still active (integrates up to now).

        Args:
            pixel_scale: degrees per pixel (tracking.pixel_scale from config).

        Returns:
            (dx, dy) where:
                dx > 0  → telescope has moved right of start position
                dy > 0  → telescope has moved down  (screen Y is inverted vs Alt)
        """
        with self._lock:
            now = time.monotonic()
            dt  = (now - self._last_tick) if self._last_tick is not None else 0.0
            az_off  = self._az_offset_deg  + self._az_rate  * dt
            alt_off = self._alt_offset_deg + self._alt_rate * dt

        dx = int(az_off  / pixel_scale)
        dy = -int(alt_off / pixel_scale)   # Alt positive = up, screen Y positive = down
        return dx, dy

    def get_offset_deg(self) -> tuple[float, float]:
        """Returns (az_offset_deg, alt_offset_deg) for HUD text display."""
        with self._lock:
            return self._az_offset_deg, self._alt_offset_deg

    def reset_offset(self) -> None:
        """Reset telescope pointing to frame centre (offset = 0, 0)."""
        with self._lock:
            self._az_offset_deg  = 0.0
            self._alt_offset_deg = 0.0
            self._az_rate        = 0.0
            self._alt_rate       = 0.0
            self._last_tick      = time.monotonic()
        logger.info("[SIM] Pointing reset to frame centre")
