"""
utils/config.py — TelescopeAI Configuration Loader

Usage:
    from utils.config import load_config
    cfg = load_config()
    lat = cfg['location']['latitude']
"""
import os
import yaml


def load_config(config_path: str = None) -> dict:
    """
    Loads config.yaml and returns it as a dict.
    Searches relative to this file's location if no path given.
    """
    if config_path is None:
        # utils/ is one level inside telescopAIproject/, config.yaml is at its root
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config.yaml')

    config_path = os.path.abspath(config_path)
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"config.yaml not found at: {config_path}")

    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)
