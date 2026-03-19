"""
hardware/indi_driver.py — INDI Telescope Driver (Raspberry Pi / Linux)

Implements TelescopeDriver using pyindi-client (PyIndi), the Python binding
for the INDI (Instrument-Neutral Distributed Interface) protocol.

INDI runs as a server process (indiserver) that manages device drivers.
This client connects to the server via TCP, sends property commands, and
reads back device state.

Prerequisites on Raspberry Pi:
    sudo apt install indi-bin libindi-dev
    pip install pyindi-client

INDI server startup example (on RPi):
    indiserver -v indi_celestron_gps    # for Celestron NexStar
    indiserver -v indi_eqmod            # for EQMod-compatible mounts

config.yaml (set mount.backend = "indi"):
    indi:
      host: "localhost"          # or RPi IP address
      port: 7624
      device_name: "Telescope Simulator"   # must match indiserver output

INDI property mapping:
    connect()               → CONNECTION switch → CONNECT
    slew_to_altaz_async()   → HORIZONTAL_COORD (AZ, ALT)
    move_axis(0, rate)      → TELESCOPE_MOTION_WE + TELESCOPE_MOTION_RATE
    move_axis(1, rate)      → TELESCOPE_MOTION_NS + TELESCOPE_MOTION_RATE
    abort_slew()            → TELESCOPE_ABORT_MOTION switch → ABORT
    unpark()                → TELESCOPE_PARK switch → UNPARK
    tracking setter         → TELESCOPE_TRACK_STATE
    tracking_rate setter    → TELESCOPE_TRACK_MODE
    sync_to_altaz()         → ON_COORD_SET=SYNC then HORIZONTAL_COORD
    slewing (poll)          → compare HORIZONTAL_COORD vs. target; Δ > 0.05°
"""
import threading
import time
from utils.logger import get_logger
from hardware.base import TelescopeDriver

logger = get_logger(__name__)

_SLEW_THRESHOLD_DEG = 0.05   # degrees — below this, consider slew complete
_PROP_TIMEOUT_SEC   = 5.0    # seconds to wait for INDI property to appear
_POLL_INTERVAL      = 0.1    # seconds between status polls


class INDITelescopeDriver(TelescopeDriver):
    """
    INDI telescope driver for Raspberry Pi / Linux.

    Inherits from PyIndi.BaseClient (set up in connect()) and from
    TelescopeDriver ABC.  The INDI client model is event-driven, but this
    implementation uses synchronous polling for simplicity and reliability.

    All INDI property reads poll the device at call time.
    All INDI property writes are sent immediately and logged.
    """

    def __init__(self, host: str, port: int, device_name: str) -> None:
        """
        Args:
            host:        Hostname or IP of the INDI server (e.g. "localhost" or "192.168.1.50")
            port:        INDI server TCP port (default: 7624)
            device_name: INDI device name as shown by indiserver (e.g. "Telescope Simulator")
        """
        self._host        = host
        self._port        = port
        self._device_name = device_name
        self._client      = None   # PyIndi.BaseClient instance, set in connect()
        self._device      = None   # INDI device handle
        self._connected   = False

        # Track the target position for slewing-poll
        self._target_az:  float | None = None
        self._target_alt: float | None = None

    # ── Connection lifecycle ──────────────────────────────────────────────────

    def connect(self) -> None:
        """
        Connect to the INDI server and enable the telescope device.

        Raises:
            RuntimeError: if PyIndi is not installed, server is unreachable,
                          or the device is not found within _PROP_TIMEOUT_SEC.
        """
        logger.info("[CONNECT] Connecting to INDI server %s:%d", self._host, self._port)
        try:
            import PyIndi
        except ImportError:
            raise RuntimeError(
                "PyIndi not installed.  Run: pip install pyindi-client\n"
                "Also requires: sudo apt install indi-bin libindi-dev"
            )

        # Build a minimal BaseClient subclass inline
        class _Client(PyIndi.BaseClient):
            def newDevice(self, d):       pass
            def newProperty(self, p):     pass
            def removeProperty(self, p):  pass
            def newBLOB(self, bp):        pass
            def newSwitch(self, svp):     pass
            def newNumber(self, nvp):     pass
            def newText(self, tvp):       pass
            def newLight(self, lvp):      pass
            def newMessage(self, d, m):   pass
            def serverConnected(self):    pass
            def serverDisconnected(self, code): pass

        client = _Client()
        client.setServer(self._host, self._port)

        if not client.connectServer():
            raise RuntimeError(
                f"[CONNECT] Cannot reach INDI server at {self._host}:{self._port}. "
                "Is indiserver running?"
            )
        logger.info("[CONNECT] INDI server reachable. Looking for device '%s'...", self._device_name)

        # Wait for device to appear
        deadline = time.monotonic() + _PROP_TIMEOUT_SEC
        device = None
        while time.monotonic() < deadline:
            device = client.getDevice(self._device_name)
            if device:
                break
            time.sleep(0.2)

        if device is None:
            raise RuntimeError(
                f"[CONNECT] Device '{self._device_name}' not found after {_PROP_TIMEOUT_SEC}s. "
                "Check indiserver output and device_name in config.yaml."
            )

        # Send CONNECTION switch → CONNECT
        conn_prop = self._wait_for_property(client, device, "CONNECTION", _PROP_TIMEOUT_SEC)
        if conn_prop is None:
            raise RuntimeError("[CONNECT] CONNECTION property not found on device.")

        conn_prop[0].s = 1  # CONNECT ON
        conn_prop[1].s = 0  # DISCONNECT OFF
        client.sendNewSwitch(conn_prop)
        time.sleep(0.5)

        self._client    = client
        self._device    = device
        self._connected = True
        logger.info("[CONNECT] OK — INDI device '%s' connected", self._device_name)

    def disconnect(self) -> None:
        """Send DISCONNECT switch and close client."""
        if self._client is not None:
            logger.info("[DISCONNECT] Disconnecting from INDI server")
            try:
                self._client.disconnectServer()
            except Exception as exc:
                logger.warning("[DISCONNECT] Error: %s", exc)
            finally:
                self._client    = None
                self._device    = None
                self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _wait_for_property(self, client, device, name: str, timeout: float):
        """Poll until an INDI property appears on the device, or timeout."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            prop = device.getSwitch(name)
            if prop:
                return prop
            prop = device.getNumber(name)
            if prop:
                return prop
            time.sleep(0.1)
        logger.warning("[INDI] Property '%s' not found after %.1fs", name, timeout)
        return None

    def _get_number(self, prop_name: str, element_name: str) -> float | None:
        """Read a numeric INDI property element."""
        prop = self._device.getNumber(prop_name)
        if prop is None:
            logger.warning("[INDI] Number property '%s' not available", prop_name)
            return None
        for el in prop:
            if el.name == element_name:
                return float(el.value)
        logger.warning("[INDI] Element '%s' not in '%s'", element_name, prop_name)
        return None

    def _send_switch(self, prop_name: str, on_element: str) -> None:
        """Set one element of a Switch property to ON, all others to OFF."""
        prop = self._device.getSwitch(prop_name)
        if prop is None:
            logger.error("[INDI] Switch property '%s' not found", prop_name)
            return
        for el in prop:
            el.s = 1 if el.name == on_element else 0
        logger.debug("[INDI] sendNewSwitch %s → %s", prop_name, on_element)
        self._client.sendNewSwitch(prop)

    # ── State properties ──────────────────────────────────────────────────────

    @property
    def at_park(self) -> bool:
        prop = self._device.getSwitch("TELESCOPE_PARK")
        if prop is None:
            return False
        for el in prop:
            if el.name == "PARK" and el.s == 1:
                return True
        return False

    @property
    def slewing(self) -> bool:
        """
        Poll HORIZONTAL_COORD and compare to target.
        Returns False if no slew has been commanded yet.
        """
        if self._target_az is None:
            return False
        az  = self._get_number("HORIZONTAL_COORD", "AZ")
        alt = self._get_number("HORIZONTAL_COORD", "ALT")
        if az is None or alt is None:
            return False
        delta_az  = abs(az  - self._target_az)
        delta_alt = abs(alt - self._target_alt)
        return (delta_az > _SLEW_THRESHOLD_DEG) or (delta_alt > _SLEW_THRESHOLD_DEG)

    @property
    def tracking(self) -> bool:
        prop = self._device.getSwitch("TELESCOPE_TRACK_STATE")
        if prop is None:
            return False
        for el in prop:
            if el.name == "TRACK_ON" and el.s == 1:
                return True
        return False

    @tracking.setter
    def tracking(self, value: bool) -> None:
        logger.debug("[TRACKING] Set INDI tracking = %s", value)
        self._send_switch("TELESCOPE_TRACK_STATE", "TRACK_ON" if value else "TRACK_OFF")

    @property
    def tracking_rate(self) -> int:
        _mode_map = {"TRACK_SIDEREAL": 0, "TRACK_LUNAR": 1, "TRACK_SOLAR": 2}
        prop = self._device.getSwitch("TELESCOPE_TRACK_MODE")
        if prop is None:
            return 0
        for el in prop:
            if el.s == 1 and el.name in _mode_map:
                return _mode_map[el.name]
        return 0

    @tracking_rate.setter
    def tracking_rate(self, rate: int) -> None:
        _modes = {0: "TRACK_SIDEREAL", 1: "TRACK_LUNAR", 2: "TRACK_SOLAR"}
        mode = _modes.get(rate, "TRACK_SIDEREAL")
        logger.debug("[TRACKING_RATE] Set INDI rate = %d (%s)", rate, mode)
        self._send_switch("TELESCOPE_TRACK_MODE", mode)

    @property
    def azimuth(self) -> float:
        return self._get_number("HORIZONTAL_COORD", "AZ") or 0.0

    @property
    def altitude(self) -> float:
        return self._get_number("HORIZONTAL_COORD", "ALT") or 0.0

    # ── Motion commands ───────────────────────────────────────────────────────

    def unpark(self) -> None:
        logger.info("[UNPARK] Sending UNPARK to INDI device")
        self._send_switch("TELESCOPE_PARK", "UNPARK")

    def slew_to_altaz_async(self, az: float, alt: float) -> None:
        """
        Send HORIZONTAL_COORD to start a GoTo slew.
        Records target position so slewing property can poll progress.
        """
        logger.info("[SLEW] → Az=%.2f° Alt=%.2f° (INDI async)", az, alt)
        self._target_az  = az
        self._target_alt = alt

        prop = self._device.getNumber("HORIZONTAL_COORD")
        if prop is None:
            logger.error("[SLEW] HORIZONTAL_COORD property not found!")
            return
        for el in prop:
            if el.name == "AZ":
                el.value = float(az)
            elif el.name == "ALT":
                el.value = float(alt)
        self._client.sendNewNumber(prop)

    def move_axis(self, axis: int, rate: float) -> None:
        """
        Translate axis/rate to INDI TELESCOPE_MOTION_* switches.

        axis 0 (Az):  rate > 0 → MOTION_EAST,  rate < 0 → MOTION_WEST,  0 → stop
        axis 1 (Alt): rate > 0 → MOTION_NORTH,  rate < 0 → MOTION_SOUTH, 0 → stop

        Rate magnitude is written to TELESCOPE_MOTION_RATE (degrees/second).
        """
        logger.debug("[MOVE_AXIS] axis=%d rate=%.4f", axis, rate)

        # Set motion rate (magnitude only)
        rate_prop = self._device.getNumber("TELESCOPE_MOTION_RATE")
        if rate_prop is not None:
            for el in rate_prop:
                el.value = abs(rate)
            self._client.sendNewNumber(rate_prop)

        if axis == 0:
            prop_name = "TELESCOPE_MOTION_WE"
            if rate > 0:
                self._send_switch(prop_name, "MOTION_EAST")
            elif rate < 0:
                self._send_switch(prop_name, "MOTION_WEST")
            else:
                # Stop: set both to OFF
                prop = self._device.getSwitch(prop_name)
                if prop:
                    for el in prop:
                        el.s = 0
                    self._client.sendNewSwitch(prop)

        elif axis == 1:
            prop_name = "TELESCOPE_MOTION_NS"
            if rate > 0:
                self._send_switch(prop_name, "MOTION_NORTH")
            elif rate < 0:
                self._send_switch(prop_name, "MOTION_SOUTH")
            else:
                prop = self._device.getSwitch(prop_name)
                if prop:
                    for el in prop:
                        el.s = 0
                    self._client.sendNewSwitch(prop)

    def abort_slew(self) -> None:
        logger.info("[ABORT] Sending TELESCOPE_ABORT_MOTION to INDI")
        self._target_az  = None
        self._target_alt = None
        self._send_switch("TELESCOPE_ABORT_MOTION", "ABORT")

    def sync_to_altaz(self, az: float, alt: float) -> None:
        """
        One-star sync:
        1. Set ON_COORD_SET to SYNC mode
        2. Send the known position via HORIZONTAL_COORD
        3. Restore ON_COORD_SET to TRACK
        """
        logger.info("[SYNC] INDI SyncToAltAz Az=%.3f° Alt=%.3f°", az, alt)
        self._send_switch("ON_COORD_SET", "SYNC")
        time.sleep(0.1)

        prop = self._device.getNumber("HORIZONTAL_COORD")
        if prop is not None:
            for el in prop:
                if el.name == "AZ":
                    el.value = float(az)
                elif el.name == "ALT":
                    el.value = float(alt)
            self._client.sendNewNumber(prop)
        else:
            logger.error("[SYNC] HORIZONTAL_COORD not available for sync")

        time.sleep(0.2)
        self._send_switch("ON_COORD_SET", "TRACK")  # restore normal mode
