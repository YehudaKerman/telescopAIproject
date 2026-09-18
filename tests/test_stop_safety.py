"""
tests/test_stop_safety.py — the mount must actually stop, and say so when it doesn't.

These cover one defect: _stop_mount used to command both axes inside a single
try/except that swallowed everything. A throw on axis 0 skipped axis 1 — the
mount kept slewing while every caller read success.

Run with: pytest tests/test_stop_safety.py -v
"""
import pytest

from core.tracker import _stop_mount
from hardware.mock_driver import MockTelescopeDriver


class FlakyDriver(MockTelescopeDriver):
    """Mock whose chosen axis refuses to accept a rate command."""

    def __init__(self, failing_axis: int, abort_fails: bool = False):
        super().__init__()
        self.failing_axis = failing_axis
        self.abort_fails = abort_fails
        self.abort_calls = 0

    def move_axis(self, axis: int, rate: float) -> None:
        if axis == self.failing_axis:
            raise RuntimeError(f"axis {axis} not responding")
        super().move_axis(axis, rate)

    def abort_slew(self) -> None:
        self.abort_calls += 1
        if self.abort_fails:
            raise RuntimeError("abort refused")


def _axes_zeroed(d) -> set:
    return {axis for axis, rate in d.move_axis_calls if rate == 0.0}


# ── positive: a healthy mount stops and reports success ───────────────────────

def test_healthy_mount_stops_both_axes():
    d = MockTelescopeDriver()
    d.connect()
    d.unpark()

    assert _stop_mount(d) is True
    assert _axes_zeroed(d) == {0, 1}


# ── negative: the failure the old code hid ────────────────────────────────────

@pytest.mark.parametrize("failing_axis, surviving_axis", [(0, 1), (1, 0)])
def test_one_dead_axis_does_not_strand_the_other(failing_axis, surviving_axis):
    """The whole point: axis 0 throwing must not leave axis 1 slewing."""
    d = FlakyDriver(failing_axis=failing_axis)
    d.connect()
    d.unpark()

    assert _stop_mount(d) is False, "a failed stop must not report success"
    assert surviving_axis in _axes_zeroed(d), (
        f"axis {surviving_axis} was never commanded to stop after axis "
        f"{failing_axis} threw — this is the original bug"
    )
    assert d.abort_calls == 1, "abort_slew is the second, independent mechanism"


def test_total_failure_still_returns_false_and_does_not_raise():
    """A finally block must not be turned into a new exception site."""
    d = FlakyDriver(failing_axis=0, abort_fails=True)
    d.connect()
    d.unpark()

    assert _stop_mount(d) is False
    assert d.abort_calls == 1


# ── the test that proves the tests discriminate ───────────────────────────────

def test_flaky_driver_actually_fails():
    """Guard against a mock that silently succeeds, making the tests vacuous."""
    d = FlakyDriver(failing_axis=0)
    with pytest.raises(RuntimeError):
        d.move_axis(0, 0.0)
    d.move_axis(1, 0.0)  # the other axis must still work
