"""Start the time clock server. This is what runs 24/7.

Run:  .venv\\Scripts\\python serve.py      (Windows)
Stop: Ctrl+C
"""

import logging
import threading
import time
from datetime import date

from waitress import serve

import db
from app import app, lan_ip
from config import load_config

BACKUP_DIR = db.DATA_DIR / "backups"
BACKUPS_TO_KEEP = 60

log = logging.getLogger("timeclock")


def make_daily_backup():
    """Copies the database to data/backups/timeclock-YYYY-MM-DD.db once a day."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    target = BACKUP_DIR / f"timeclock-{date.today().isoformat()}.db"
    if target.exists():
        return
    tmp = target.with_suffix(".tmp")
    db.backup_to(tmp)
    tmp.replace(target)
    log.info("Saved daily backup %s", target.name)
    for old in sorted(BACKUP_DIR.glob("timeclock-*.db"))[:-BACKUPS_TO_KEEP]:
        old.unlink()


def backup_loop():
    while True:
        try:
            make_daily_backup()
        except Exception:
            log.exception("Daily backup failed")
        time.sleep(3600)  # check once an hour


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config()
    db.init_db()
    threading.Thread(target=backup_loop, daemon=True).start()

    port = cfg["port"]
    log.info("Time clock running.")
    log.info("  Employees (NFC tag URL): http://%s:%s/", lan_ip(), port)
    log.info("  Admin:                   http://%s:%s/admin", lan_ip(), port)
    if not cfg["admin_password_hash"]:
        log.warning("No admin password set yet. Run: python set_password.py")
    serve(app, host="0.0.0.0", port=port, threads=8)


if __name__ == "__main__":
    main()
