"""
hardware/__init__.py — Driver Factory

Creates the correct TelescopeDriver based on config.yaml mount.backend.

Usage:
    from hardware import driver_factory
    from utils.config import load_config

    cfg    = load_config()
    driver = driver_factory(cfg)
    driver.connect()

config.yaml mount.backend values:
    "ascom"  — Windows, ASCOM COM driver (default)
    "indi"   — Raspberry Pi / Linux, INDI protocol
    "mock"   — No hardware, for unit tests
"""
from utils.logger import get_logger
from hardware.base import TelescopeDriver

logger = get_logger(__name__)


def driver_factory(cfg: dict) -> TelescopeDriver:
    """
    Instantiate and return the appropriate TelescopeDriver.

    Args:
        cfg: Full config dict (as returned by load_config())

    Returns:
        An uninitialised TelescopeDriver subclass.
        Call driver.connect() before using it.

    Raises:
        ValueError: if mount.backend is not recognised.
    """
    backend = cfg.get("mount", {}).get("backend", "ascom").lower()
    logger.info("[DRIVER_FACTORY] Selected backend: %s", backend)

    if backend == "ascom":
        from hardware.ascom_driver import ASCOMTelescopeDriver
        prog_id = cfg["mount"]["driver"]
        logger.info("[DRIVER_FACTORY] ASCOM ProgID: %s", prog_id)
        return ASCOMTelescopeDriver(prog_id)

    elif backend == "indi":
        from hardware.indi_driver import INDITelescopeDriver
        indi_cfg    = cfg.get("indi", {})
        host        = indi_cfg.get("host", "localhost")
        port        = int(indi_cfg.get("port", 7624))
        device_name = indi_cfg.get("device_name", "Telescope Simulator")
        logger.info("[DRIVER_FACTORY] INDI server: %s:%d  device: '%s'",
                    host, port, device_name)
        return INDITelescopeDriver(host=host, port=port, device_name=device_name)

    elif backend == "mock":
        from hardware.mock_driver import MockTelescopeDriver
        logger.info("[DRIVER_FACTORY] Using MockTelescopeDriver (no hardware)")
        return MockTelescopeDriver()

    else:
        raise ValueError(
            f"Unknown mount backend: '{backend}'. "
            "Valid options: 'ascom', 'indi', 'mock'. "
            "Check mount.backend in config.yaml."
        )
