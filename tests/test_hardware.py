"""
tests/test_hardware.py — Unit tests for the hardware abstraction layer

All tests use MockTelescopeDriver — no physical mount required.
Run with: pytest tests/test_hardware.py -v
"""
import pytest
from hardware.mock_driver import MockTelescopeDriver
from hardware import driver_factory


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def driver() -> MockTelescopeDriver:
    d = MockTelescopeDriver()
    d.connect()
    d.unpark()
    return d


# ── Connection lifecycle ──────────────────────────────────────────────────────

def test_connect_disconnect():
    d = MockTelescopeDriver()
    assert not d.is_connected
    d.connect()
    assert d.is_connected
    d.disconnect()
    assert not d.is_connected


def test_unpark_clears_at_park(driver):
    assert not driver.at_park


# ── Slew ─────────────────────────────────────────────────────────────────────

def test_slew_records_call(driver):
    driver.slew_to_altaz_async(az=90.0, alt=30.0)
    assert driver.slew_calls == [(90.0, 30.0)]


def test_slew_sets_slewing_flag(driver):
    driver.slew_to_altaz_async(az=180.0, alt=45.0)
    assert driver.slewing is True


def test_simulate_arrival_clears_slewing(driver):
    driver.slew_to_altaz_async(az=45.0, alt=20.0)
    driver.simulate_arrival()
    assert driver.slewing is False


def test_slew_updates_position(driver):
    driver.slew_to_altaz_async(az=270.0, alt=60.0)
    assert driver.azimuth  == 270.0
    assert driver.altitude == 60.0


# ── MoveAxis ─────────────────────────────────────────────────────────────────

def test_move_axis_records_calls(driver):
    driver.move_axis(0, 1.5)
    driver.move_axis(1, -0.3)
    assert (0,  1.5) in driver.move_axis_calls
    assert (1, -0.3) in driver.move_axis_calls


def test_abort_slew(driver):
    driver.slew_to_altaz_async(90.0, 30.0)
    driver.abort_slew()
    assert not driver.slewing
    assert driver.abort_calls == 1


# ── Tracking ─────────────────────────────────────────────────────────────────

def test_tracking_toggle(driver):
    driver.tracking = True
    assert driver.tracking is True
    driver.tracking = False
    assert driver.tracking is False


def test_tracking_rate(driver):
    driver.tracking_rate = 1   # Lunar
    assert driver.tracking_rate == 1


# ── Sync ─────────────────────────────────────────────────────────────────────

def test_sync_to_altaz(driver):
    driver.sync_to_altaz(az=12.3, alt=45.6)
    assert driver.sync_calls == [(12.3, 45.6)]
    assert driver.azimuth  == 12.3
    assert driver.altitude == 45.6


# ── Reset ────────────────────────────────────────────────────────────────────

def test_reset_clears_history(driver):
    driver.move_axis(0, 1.0)
    driver.slew_to_altaz_async(10.0, 20.0)
    driver.reset()
    assert driver.move_axis_calls == []
    assert driver.slew_calls      == []
    assert driver.abort_calls     == 0


# ── driver_factory ────────────────────────────────────────────────────────────

def test_driver_factory_mock():
    from utils.config import load_config
    cfg = load_config()
    cfg["mount"]["backend"] = "mock"
    d = driver_factory(cfg)
    d.connect()
    assert d.is_connected


def test_driver_factory_unknown_raises():
    from utils.config import load_config
    cfg = load_config()
    cfg["mount"]["backend"] = "nonexistent"
    with pytest.raises(ValueError, match="nonexistent"):
        driver_factory(cfg)
