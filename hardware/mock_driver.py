"""
hardware/mock_driver.py — Mock Telescope Driver (for testing)

Simulates a telescope mount without any hardware.  All motion commands are
recorded in call-history lists so unit tests can assert exact behaviour.

Usage:
    from hardware.mock_driver import MockTelescopeDriver
    driver = MockTelescopeDriver()
    driver.connect()
    driver.slew_to_altaz_async(az=90.0, alt=30.0)
    # Simulate arrival in test code:
    driver._slewing = False
    assert driver.azimuth == 90.0

Test inspection:
    driver.move_axis_calls   # list of (axis, rate) tuples
    driver.slew_calls        # list of (az, alt) tuples
    driver.reset()           # clear history between test cases
"""
from utils.logger import get_logger
from hardware.base import TelescopeDriver

logger = get_logger(__name__)


class MockTelescopeDriver(TelescopeDriver):
    """
    In-memory telescope driver for unit tests and CI.

    No hardware, no imports, no side effects.
    All state is exposed as plain attributes for easy inspection and mutation.
    """

    def __init__(self) -> None:
        self._connected      = False
        self._at_park        = True
        self._slewing        = False
        self._tracking       = False
        self._tracking_rate  = 0
        self._azimuth        = 0.0
        self._altitude       = 0.0

        # Call history — inspect these in tests
        self.move_axis_calls: list[tuple[int, float]] = []
        self.slew_calls:      list[tuple[float, float]] = []
        self.abort_calls:     int = 0
        self.sync_calls:      list[tuple[float, float]] = []

    # ── Connection lifecycle ──────────────────────────────────────────────────

    def connect(self) -> None:
        logger.info("[MOCK] connect() called — no hardware")
        self._connected = True

    def disconnect(self) -> None:
        logger.info("[MOCK] disconnect() called")
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    # ── State properties ──────────────────────────────────────────────────────

    @property
    def at_park(self) -> bool:
        return self._at_park

    @property
    def slewing(self) -> bool:
        return self._slewing

    @property
    def tracking(self) -> bool:
        return self._tracking

    @tracking.setter
    def tracking(self, value: bool) -> None:
        logger.debug("[MOCK] tracking = %s", value)
        self._tracking = value

    @property
    def tracking_rate(self) -> int:
        return self._tracking_rate

    @tracking_rate.setter
    def tracking_rate(self, rate: int) -> None:
        logger.debug("[MOCK] tracking_rate = %d", rate)
        self._tracking_rate = rate

    @property
    def azimuth(self) -> float:
        return self._azimuth

    @property
    def altitude(self) -> float:
        return self._altitude

    # ── Motion commands ───────────────────────────────────────────────────────

    def unpark(self) -> None:
        logger.debug("[MOCK] unpark()")
        self._at_park = False

    def slew_to_altaz_async(self, az: float, alt: float) -> None:
        logger.info("[MOCK] slew_to_altaz_async(az=%.2f, alt=%.2f)", az, alt)
        self.slew_calls.append((az, alt))
        self._slewing  = True
        self._azimuth  = az    # jump immediately (mock doesn't animate)
        self._altitude = alt

    def move_axis(self, axis: int, rate: float) -> None:
        logger.debug("[MOCK] move_axis(axis=%d, rate=%.4f)", axis, rate)
        self.move_axis_calls.append((axis, rate))
        # Stop slew if both axes are commanded to 0
        if rate == 0.0 and all(r == 0.0 for _, r in self.move_axis_calls[-2:]):
            self._slewing = False

    def abort_slew(self) -> None:
        logger.info("[MOCK] abort_slew()")
        self.abort_calls += 1
        self._slewing = False

    def sync_to_altaz(self, az: float, alt: float) -> None:
        logger.info("[MOCK] sync_to_altaz(az=%.3f, alt=%.3f)", az, alt)
        self.sync_calls.append((az, alt))
        self._azimuth  = az
        self._altitude = alt

    # ── Test helpers ──────────────────────────────────────────────────────────

    def reset(self) -> None:
        """Clear call history between test cases."""
        self.move_axis_calls.clear()
        self.slew_calls.clear()
        self.sync_calls.clear()
        self.abort_calls = 0

    def simulate_arrival(self) -> None:
        """Mark the current slew as complete (call from test thread)."""
        self._slewing = False
