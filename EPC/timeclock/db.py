"""Database access. Everything is stored in one SQLite file: data/timeclock.db"""

import os
import sqlite3
from datetime import datetime
from pathlib import Path

# TIMECLOCK_DATA_DIR lets the tests use a throwaway folder.
DATA_DIR = Path(os.environ.get("TIMECLOCK_DATA_DIR") or Path(__file__).resolve().parent / "data")
DB_PATH = DATA_DIR / "timeclock.db"

TS_FORMAT = "%Y-%m-%d %H:%M:%S"

SCHEMA = """
CREATE TABLE IF NOT EXISTS employees (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL UNIQUE,
    active     INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL REFERENCES employees(id),
    event_type  TEXT NOT NULL CHECK (event_type IN ('IN', 'OUT')),
    ts          TEXT NOT NULL,              -- local time, 'YYYY-MM-DD HH:MM:SS'
    source      TEXT NOT NULL DEFAULT 'tap', -- 'tap' (phone) or 'admin' (manual fix)
    note        TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_emp_ts ON events (employee_id, ts);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events (ts);
"""


def now_str():
    return datetime.now().strftime(TS_FORMAT)


def parse_ts(value):
    return datetime.strptime(value, TS_FORMAT)


def connect():
    DATA_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db():
    conn = connect()
    try:
        conn.executescript(SCHEMA)
    finally:
        conn.close()


# ---------------------------------------------------------------- employees

def list_employees(conn, include_inactive=False):
    sql = "SELECT * FROM employees"
    if not include_inactive:
        sql += " WHERE active = 1"
    return conn.execute(sql + " ORDER BY name COLLATE NOCASE").fetchall()


def get_employee(conn, employee_id):
    return conn.execute("SELECT * FROM employees WHERE id = ?", (employee_id,)).fetchone()


def add_employee(conn, name):
    conn.execute("INSERT INTO employees (name, created_at) VALUES (?, ?)", (name, now_str()))


def rename_employee(conn, employee_id, name):
    conn.execute("UPDATE employees SET name = ? WHERE id = ?", (name, employee_id))


def set_employee_active(conn, employee_id, active):
    conn.execute("UPDATE employees SET active = ? WHERE id = ?", (1 if active else 0, employee_id))


# ------------------------------------------------------------------- events

def last_event(conn, employee_id):
    return conn.execute(
        "SELECT * FROM events WHERE employee_id = ? ORDER BY ts DESC, id DESC LIMIT 1",
        (employee_id,),
    ).fetchone()


def add_event(conn, employee_id, event_type, ts=None, source="tap", note=""):
    cur = conn.execute(
        "INSERT INTO events (employee_id, event_type, ts, source, note, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (employee_id, event_type, ts or now_str(), source, note, now_str()),
    )
    return cur.lastrowid


def get_event(conn, event_id):
    return conn.execute(
        "SELECT e.*, emp.name AS employee_name FROM events e "
        "JOIN employees emp ON emp.id = e.employee_id WHERE e.id = ?",
        (event_id,),
    ).fetchone()


def delete_event(conn, event_id):
    conn.execute("DELETE FROM events WHERE id = ?", (event_id,))


def events_between(conn, start, end, employee_id=None):
    """Events with start <= ts < end (both 'YYYY-MM-DD HH:MM:SS' strings), oldest first."""
    sql = (
        "SELECT e.*, emp.name AS employee_name FROM events e "
        "JOIN employees emp ON emp.id = e.employee_id WHERE e.ts >= ? AND e.ts < ?"
    )
    params = [start, end]
    if employee_id is not None:
        sql += " AND e.employee_id = ?"
        params.append(employee_id)
    return conn.execute(sql + " ORDER BY e.ts, e.id", params).fetchall()


def backup_to(path):
    """Safe copy of the live database (works even while the server is running)."""
    src = connect()
    dst = sqlite3.connect(path)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
