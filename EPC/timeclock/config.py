"""Settings stored in data/config.json (created automatically on first run)."""

import json
import secrets

from db import DATA_DIR

CONFIG_PATH = DATA_DIR / "config.json"

DEFAULTS = {
    "shop_name": "Time Clock",
    "port": 8080,
    # First day of the week for weekly totals: 0 = Monday, 6 = Sunday
    "week_start": 0,
    "admin_password_hash": "",
}


def load_config():
    DATA_DIR.mkdir(exist_ok=True)
    cfg = dict(DEFAULTS)
    if CONFIG_PATH.exists():
        cfg.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
    if not cfg.get("secret_key"):
        # Used to sign login cookies. Generated once, then kept.
        cfg["secret_key"] = secrets.token_hex(32)
        save_config(cfg)
    elif not CONFIG_PATH.exists():
        save_config(cfg)
    return cfg


def save_config(cfg):
    DATA_DIR.mkdir(exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
