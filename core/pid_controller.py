"""
pid_controller.py — PID Controller for TelescopeAI

Usage:
    pid = PIDController(kp=0.4, ki=0.005, kd=0.08, output_limits=(-3.5, 3.5))
    rate = pid.update(error_degrees)   # call each frame
    pid.reset()                        # call when target is lost

Input  (error)  — degrees from frame center
Output (rate)   — degrees/second for scope.MoveAxis()
"""
import time


class PIDController:
    """
    PID controller with anti-windup integral clamping.

    Anti-windup: the integral is back-calculated after clamping so that
    it cannot accumulate beyond what the output limits allow.
    """

    def __init__(
        self,
        kp: float,
        ki: float,
        kd: float,
        output_limits: tuple = (-4.0, 4.0),
    ):
        """
        Args:
            kp: Proportional gain
            ki: Integral gain
            kd: Derivative gain
            output_limits: (min, max) output rate in degrees/second
        """
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.min_out, self.max_out = output_limits

        self._integral = 0.0
        self._prev_error = 0.0
        self._last_time: float | None = None

    def update(self, error: float) -> float:
        """
        Calculate PID output for the given error.

        Args:
            error: signed error in degrees
                   positive = target is right of center (Az) or above center (Alt)

        Returns:
            Motor rate in degrees/second, clamped to output_limits
        """
        now = time.monotonic()
        dt = (now - self._last_time) if self._last_time is not None else 0.033
        self._last_time = now

        # Proportional
        p = self.kp * error

        # Integral with anti-windup back-calculation
        self._integral += error * dt
        i_raw = self.ki * self._integral
        i_clamped = max(self.min_out, min(self.max_out, i_raw))
        if self.ki != 0:
            self._integral = i_clamped / self.ki  # back-calculate to prevent windup

        # Derivative (on error to avoid kick on setpoint change)
        d = self.kd * (error - self._prev_error) / dt if dt > 0 else 0.0
        self._prev_error = error

        output = p + i_clamped + d
        return max(self.min_out, min(self.max_out, output))

    def reset(self):
        """Reset integrator and history. Call when tracking is lost or restarted."""
        self._integral = 0.0
        self._prev_error = 0.0
        self._last_time = None
