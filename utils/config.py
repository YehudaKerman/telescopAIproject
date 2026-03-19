"""
utils/config.py — TelescopeAI Configuration Loader

Single source of truth for reading and writing config.yaml.

Usage:
    from utils.config import load_config, save_config

    cfg = load_config()
    lat = cfg['location']['latitude']

    cfg['calibration']['pixel_scale'] = 0.0012
    save_config(cfg)
"""
import os
import yaml


def _default_path() -> str:
    """Resolve config.yaml relative to this file (utils/../config.yaml)."""
    return os.path.abspath(
        os.path.join(os.path.dirname(__file__), '..', 'config.yaml')
    )


def load_config(config_path: str = None) -> dict:
    """
    Load config.yaml and return it as a dict.

    Args:
        config_path: Absolute or relative path to config.yaml.
                     If None, searches in the project root (one level above utils/).

    Returns:
        Parsed YAML as a nested dict.

    Raises:
        FileNotFoundError: if config.yaml does not exist at the resolved path.
    """
    path = os.path.abspath(config_path) if config_path else _default_path()

    if not os.path.exists(path):
        raise FileNotFoundError(f"config.yaml not found at: {path}")

    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def save_config(cfg: dict, config_path: str = None) -> None:
    """
    Write a config dict back to config.yaml, preserving Unicode (Hebrew names).

    Args:
        cfg:         The full config dict (as returned by load_config()).
        config_path: Path to write to.  Defaults to the same file load_config() reads.

    Raises:
        OSError: if the file cannot be written.

    Example:
        cfg = load_config()
        cfg['calibration']['pixel_scale'] = 0.0012
        cfg['calibration']['calibrated_at'] = '2026-03-18T21:30:00'
        save_config(cfg)
    """
    path = os.path.abspath(config_path) if config_path else _default_path()

    with open(path, 'w', encoding='utf-8') as f:
        yaml.dump(cfg, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
