"""
hardware/ascom_driver.py — ASCOM Telescope Driver (Windows)

Implements TelescopeDriver using win32com.client, compatible with any
ASCOM-compliant mount (tested with Celestron CPWI / NexStar).

The win32com import is deferred until connect() so this file can be imported
on Linux/RPi without crashing (even though it will fail at runtime there).

Usage:
    from hardware.ascom_driver import ASCOMTelescopeDriver
    driver = ASCOMTelescopeDriver("ASCOM.CPWI.Telescope")
    driver.connect()
    driver.slew_to_altaz_async(az=180.0, alt=45.0)
    while driver.slewing:
        time.sleep(0.2)
    driver.disconnect()
"""
from utils.logger import get_logger
from hardware.base import TelescopeDriver

logger = get_logger(__name__)


class ASCOMTelescopeDriver(TelescopeDriver):
    """
    ASCOM telescope driver for Windows.

    Wraps a COM object obtained via win32com.client.Dispatch().
    All ASCOM property names are mapped to the TelescopeDriver ABC.
    """

    def __init__(self, prog_id: str) -> None:
        """
        Args:
            prog_id: ASCOM ProgID string, e.g. "ASCOM.CPWI.Telescope"
                     (found in the ASCOM Device Hub or telescope's ASCOM driver docs)
        """
        self._prog_id = prog_id
        self._com = None   # win32com COM object, set in connect()

    # ── Connection lifecycle ──────────────────────────────────────────────────

    def connect(self) -> None:
        """
        Dispatch the ASCOM COM object and set Connected = True.

        Raises:
            RuntimeError: if win32com is not available or the driver fails.
        """
        logger.info("[CONNECT] Dispatching ASCOM driver: %s", self._prog_id)
        try:
            import win32com.client
            self._com = win32com.client.Dispatch(self._prog_id)
            self._com.Connected = True
            logger.info("[CONNECT] OK — telescope connected via ASCOM")
        except ImportError:
            raise RuntimeError(
                "win32com not available.  Install pywin32 or use INDITelescopeDriver on Linux."
            )
        except Exception as exc:
            raise RuntimeError(f"[CONNECT] ASCOM connection failed: {exc}") from exc

    def disconnect(self) -> None:
        """Set Connected = False and release the COM object."""
        if self._com is not None:
            try:
                self._com.Connected = False
                logger.info("[DISCONNECT] ASCOM telescope disconnected")
            except Exception as exc:
                logger.warning("[DISCONNECT] Error during disconnect: %s", exc)
            finally:
                self._com = None

    @property
    def is_connected(self) -> bool:
        try:
            return self._com is not None and bool(self._com.Connected)
        except Exception:
            return False

    # ── State properties ──────────────────────────────────────────────────────

    @property
    def at_park(self) -> bool:
        return bool(self._com.AtPark)

    @property
    def slewing(self) -> bool:
        return bool(self._com.Slewing)

    @property
    def tracking(self) -> bool:
        return bool(self._com.Tracking)

    @tracking.setter
    def tracking(self, value: bool) -> None:
        logger.debug("[TRACKING] Set tracking = %s", value)
        self._com.Tracking = value

    @property
    def tracking_rate(self) -> int:
        return int(self._com.TrackingRate)

    @tracking_rate.setter
    def tracking_rate(self, rate: int) -> None:
        _names = {0: "Sidereal", 1: "Lunar", 2: "Solar"}
        logger.debug("[TRACKING_RATE] Set rate = %d (%s)", rate, _names.get(rate, "?"))
        try:
            self._com.TrackingRate = rate
        except Exception as exc:
            logger.warning("[TRACKING_RATE] Failed to set rate %d: %s", rate, exc)

    @property
    def azimuth(self) -> float:
        return float(self._com.Azimuth)

    @property
    def altitude(self) -> float:
        return float(self._com.Altitude)

    # ── Motion commands ───────────────────────────────────────────────────────

    def unpark(self) -> None:
        logger.info("[UNPARK] Unparking mount")
        try:
            self._com.Unpark()
        except Exception as exc:
            logger.warning("[UNPARK] Unpark call failed (may already be unparked): %s", exc)

    def slew_to_altaz_async(self, az: float, alt: float) -> None:
        logger.info("[SLEW] → Az=%.2f° Alt=%.2f° (async)", az, alt)
        self._com.SlewToAltAzAsync(float(az), float(alt))

    def move_axis(self, axis: int, rate: float) -> None:
        """
        Send a rate command to one axis.  Called every frame by the PID tracker.
        Logged at DEBUG level only (too noisy for INFO).
        """
        logger.debug("[MOVE_AXIS] axis=%d rate=%.4f deg/s", axis, rate)
        try:
            self._com.MoveAxis(axis, float(rate))
        except Exception as exc:
            logger.error("[MOVE_AXIS] Failed on axis %d: %s", axis, exc)

    def abort_slew(self) -> None:
        logger.info("[ABORT] AbortSlew called")
        try:
            self._com.AbortSlew()
        except Exception as exc:
            logger.warning("[ABORT] AbortSlew failed: %s", exc)

    def sync_to_altaz(self, az: float, alt: float) -> None:
        logger.info("[SYNC] SyncToAltAz Az=%.3f° Alt=%.3f°", az, alt)
        self._com.SyncToAltAz(float(az), float(alt))
