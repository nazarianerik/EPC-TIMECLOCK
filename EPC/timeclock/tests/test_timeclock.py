"""Automated checks. Run from the TimeClock folder:

    .venv\\Scripts\\python -m unittest discover tests      (Windows)
"""

import os
import re
import sys
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

TMP = tempfile.mkdtemp()
os.environ["TIMECLOCK_DATA_DIR"] = TMP
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from werkzeug.security import generate_password_hash  # noqa: E402

import db  # noqa: E402
from app import app  # noqa: E402
from config import load_config, save_config  # noqa: E402
from timesheet import build_shifts, fmt_hm, fmt_time, summarize, week_start_of  # noqa: E402


def ev(id, emp, typ, ts, name="A"):
    return {"id": id, "employee_id": emp, "employee_name": name, "event_type": typ, "ts": ts}


class TimesheetMath(unittest.TestCase):
    def test_pairs_and_totals(self):
        events = [
            ev(1, 1, "IN", "2026-10-19 08:00:00"), ev(2, 1, "OUT", "2026-10-19 12:00:00"),
            ev(3, 1, "IN", "2026-10-19 12:30:00"), ev(4, 1, "OUT", "2026-10-19 17:00:00"),
            ev(5, 1, "IN", "2026-10-20 09:00:00"), ev(6, 1, "OUT", "2026-10-20 13:15:00"),
        ]
        shifts, orphans = build_shifts(events, set())
        self.assertEqual(len(shifts), 3)
        self.assertEqual(orphans, [])
        daily, weekly, per_emp = summarize(shifts, week_start=0)
        self.assertEqual(daily[(date(2026, 10, 19), "A")], 8.5 * 3600)
        self.assertEqual(daily[(date(2026, 10, 20), "A")], 4.25 * 3600)
        self.assertEqual(weekly[(date(2026, 10, 19), "A")], 12.75 * 3600)
        self.assertEqual(per_emp["A"], 12.75 * 3600)

    def test_problems_are_flagged(self):
        events = [
            ev(1, 1, "OUT", "2026-10-19 07:00:00"),  # orphan clock-out
            ev(2, 1, "IN", "2026-10-19 08:00:00"),   # never clocked out
            ev(3, 1, "IN", "2026-10-20 08:00:00"),   # currently clocked in
        ]
        shifts, orphans = build_shifts(events, {3})
        self.assertEqual([o.event_id for o in orphans], [1])
        self.assertEqual([s.status for s in shifts], ["missing_out", "open"])
        self.assertEqual(summarize(shifts, 0)[2], {})

    def test_overnight_shift_counts_on_start_day(self):
        shifts, _ = build_shifts([ev(1, 1, "IN", "2026-10-19 22:00:00"),
                                  ev(2, 1, "OUT", "2026-10-20 02:00:00")], set())
        daily = summarize(shifts, 0)[0]
        self.assertEqual(daily, {(date(2026, 10, 19), "A"): 4 * 3600})

    def test_week_start(self):
        wed = date(2026, 10, 21)
        self.assertEqual(week_start_of(wed, 0), date(2026, 10, 19))  # Monday
        self.assertEqual(week_start_of(wed, 6), date(2026, 10, 18))  # Sunday

    def test_formatting(self):
        self.assertEqual(fmt_time(datetime(2026, 1, 1, 0, 5)), "12:05 AM")
        self.assertEqual(fmt_time(datetime(2026, 1, 1, 13, 7)), "1:07 PM")
        self.assertEqual(fmt_hm(8 * 3600 + 5 * 60), "8h 05m")


class WebFlow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init_db()
        cfg = load_config()
        cfg["admin_password_hash"] = generate_password_hash("secret123")
        save_config(cfg)
        conn = db.connect()
        db.add_employee(conn, "Alice")
        db.add_employee(conn, "Bob")
        conn.commit()
        cls.alice = conn.execute("SELECT id FROM employees WHERE name='Alice'").fetchone()[0]
        conn.close()

    def client_with_token(self, path):
        client = app.test_client()
        page = client.get(path, follow_redirects=True)
        token = re.search(r'name="csrf_token" value="([^"]+)"', page.text)
        return client, page, token.group(1) if token else None

    def test_clock_in_then_out_and_no_double_clock_in(self):
        client, page, token = self.client_with_token(f"/e/{self.alice}")
        self.assertIn("Clock In", page.text)

        r = client.post("/punch", data={"csrf_token": token, "employee_id": self.alice,
                                        "action": "IN"}, follow_redirects=True)
        self.assertIn("you're clocked in", r.text)

        # Same tap again: refused, and the page now offers Clock Out only.
        r = client.post("/punch", data={"csrf_token": token, "employee_id": self.alice,
                                        "action": "IN"}, follow_redirects=True)
        self.assertIn("already clocked in", r.text)
        self.assertIn("Clock Out", r.text)
        self.assertNotIn(">Clock In<", r.text)

        r = client.post("/punch", data={"csrf_token": token, "employee_id": self.alice,
                                        "action": "OUT"}, follow_redirects=True)
        self.assertIn("you're clocked out", r.text)

        # Phone remembers the employee.
        r = client.get("/")
        self.assertEqual(r.status_code, 302)
        self.assertIn(f"/e/{self.alice}", r.headers["Location"])

    def test_post_without_token_is_rejected(self):
        client = app.test_client()
        r = client.post("/punch", data={"employee_id": self.alice, "action": "IN"},
                        follow_redirects=True)
        self.assertIn("expired", r.text)

    def test_admin_requires_login(self):
        client = app.test_client()
        self.assertEqual(client.get("/admin").status_code, 302)
        self.assertEqual(client.get("/admin/export/weekly.csv").status_code, 302)

    def test_admin_pages_and_exports(self):
        client, _, token = self.client_with_token("/admin/login")
        r = client.post("/admin/login", data={"csrf_token": token, "password": "secret123"})
        self.assertEqual(r.status_code, 302)

        page = client.get("/admin/events")
        token = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
        client.post("/admin/events/add", data={
            "csrf_token": token, "employee_id": self.alice, "event_type": "IN",
            "date": "2026-10-05", "time": "08:00"})
        client.post("/admin/events/add", data={
            "csrf_token": token, "employee_id": self.alice, "event_type": "OUT",
            "date": "2026-10-05", "time": "16:30"})

        for path in ["/admin", "/admin/events", "/admin/employees",
                     "/admin?start=2026-10-01&end=2026-10-31"]:
            self.assertEqual(client.get(path).status_code, 200, path)

        csv = client.get("/admin/export/weekly.csv?start=2026-10-05&end=2026-10-11").text
        self.assertIn("Alice,2026-10-05,8.50", csv)
        csv = client.get("/admin/export/shifts.csv?start=2026-10-05&end=2026-10-05").text
        self.assertIn("Alice,2026-10-05,08:00,16:30,8.50", csv)

        backup = client.get("/admin/backup")
        self.assertTrue(backup.data.startswith(b"SQLite format 3"))


if __name__ == "__main__":
    unittest.main()
