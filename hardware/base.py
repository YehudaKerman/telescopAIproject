"""
hardware/base.py — TelescopeDriver Abstract Base Class

Every telescope backend (ASCOM, INDI, Mock) must implement this interface.
Code in main.py, tracker.py, and calibration.py should only use these methods
— never call win32com or PyIndi APIs directly.

Axis convention (used in move_axis):
    axis 0 = Azimuth / Right Ascension
    axis 1 = Altitude / Declination
    positive rate = East (Az) or North (Alt)
    negative rate = West (Az) or South (Alt)
    rate unit = degrees per second

Usage:
    from hardware.ascom_driver import ASCOMTelescopeDriver
    driver = ASCOMTelescopeDriver("ASCOM.CPWI.Telescope")
    driver.connect()
    if driver.at_park:
        driver.unpark()
    driver.slew_to_altaz_async(az=180.0, alt=45.0)
    while driver.slewing:
        time.sleep(0.2)
    driver.disconnect()
"""
from abc import ABC, abstractmethod


class TelescopeDriver(ABC):
    """
    Platform-agnostic interface for an Alt-Az telescope mount.

    Concrete implementations: ASCOMTelescopeDriver, INDITelescopeDriver,
    MockTelescopeDriver.
    """

    # ── Connection lifecycle ──────────────────────────────────────────────────

    @abstractmethod
    def connect(self) -> None:
        """
        Open a connection to the mount hardware.

        Raises:
            RuntimeError: if the connection fails (driver not found, COM error,
                          INDI server unreachable, etc.)
        """

    @abstractmethod
    def disconnect(self) -> None:
        """
        Close the connection and free resources.
        Safe to call even if not connected (should be a no-op).
        """

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """True if the mount is currently connected."""

    # ── State properties ──────────────────────────────────────────────────────

    @property
    @abstractmethod
    def at_park(self) -> bool:
        """True if the mount is in its parked (home) position."""

    @property
    @abstractmethod
    def slewing(self) -> bool:
        """True if a GoTo slew is currently in progress."""

    @property
    @abstractmethod
    def tracking(self) -> bool:
        """True if the mount is actively tracking (sidereal/lunar/solar)."""

    @tracking.setter
    @abstractmethod
    def tracking(self, value: bool) -> None:
        """Enable or disable tracking."""

    @property
    @abstractmethod
    def tracking_rate(self) -> int:
        """
        Current tracking rate.
            0 = Sidereal  (stars, planets)
            1 = Lunar     (Moon)
            2 = Solar     (Sun — use with caution!)
        """

    @tracking_rate.setter
    @abstractmethod
    def tracking_rate(self, rate: int) -> None:
        """Set tracking rate (0=Sidereal, 1=Lunar, 2=Solar)."""

    @property
    @abstractmethod
    def azimuth(self) -> float:
        """Current mount azimuth in degrees (0=North, 90=East, clockwise)."""

    @property
    @abstractmethod
    def altitude(self) -> float:
        """Current mount altitude in degrees (0=horizon, 90=zenith)."""

    # ── Motion commands ───────────────────────────────────────────────────────

    @abstractmethod
    def unpark(self) -> None:
        """
        Release the mount from its parked position.
        Safe to call if already unparked (no-op).
        """

    @abstractmethod
    def slew_to_altaz_async(self, az: float, alt: float) -> None:
        """
        Begin a non-blocking GoTo slew to the given Az/Alt position.
        Poll driver.slewing to check completion.

        Args:
            az:  Target azimuth in degrees (0=North, 90=East)
            alt: Target altitude in degrees (0=horizon, 90=zenith)
        """

    @abstractmethod
    def move_axis(self, axis: int, rate: float) -> None:
        """
        Command a continuous slew rate on one axis.
        Call with rate=0 to stop.  Used by the PID tracker.

        Args:
            axis: 0 = Azimuth/RA,  1 = Altitude/Dec
            rate: Speed in degrees/second.
                  Positive = East (axis 0) or North (axis 1)
                  Negative = West (axis 0) or South (axis 1)
        """

    @abstractmethod
    def abort_slew(self) -> None:
        """
        Immediately stop all mount motion.
        Safe to call at any time (e.g. in finally blocks or signal handlers).
        """

    @abstractmethod
    def sync_to_altaz(self, az: float, alt: float) -> None:
        """
        Perform a one-star sync: tell the mount that its current position
        IS the given Az/Alt.  Used during landmark-based calibration.

        Args:
            az:  Known azimuth in degrees
            alt: Known altitude in degrees
        """
