"""Turns raw clock-in/out events into shifts and daily/weekly hour totals.

Rules:
- Each IN is paired with the next OUT for the same employee. That pair is one shift.
- A shift's hours count on the day it STARTED (an overnight shift counts on day one).
- An IN followed by another IN = the first one is missing its clock-out (flagged).
- An OUT with no IN before it = orphan clock-out (flagged).
- The employee's most recent IN with no OUT yet = currently clocked in (not counted yet).
- Shifts longer than LONG_SHIFT_HOURS are flagged (probably a forgotten clock-out).
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta

from db import parse_ts

LONG_SHIFT_HOURS = 14


@dataclass
class Shift:
    employee_id: int
    employee_name: str
    start: datetime
    end: datetime | None
    in_event_id: int
    out_event_id: int | None
    status: str  # 'complete', 'open' (clocked in right now), 'missing_out'

    @property
    def seconds(self):
        if self.status != "complete":
            return 0
        return (self.end - self.start).total_seconds()

    @property
    def work_date(self):
        return self.start.date()

    @property
    def is_long(self):
        return self.seconds > LONG_SHIFT_HOURS * 3600


@dataclass
class OrphanOut:
    employee_id: int
    employee_name: str
    ts: datetime
    event_id: int


def build_shifts(events, open_in_event_ids):
    """events: rows from db.events_between (oldest first).
    open_in_event_ids: IDs of IN events that are an employee's latest event overall
    (i.e. they are clocked in right now)."""
    shifts, orphans = [], []
    pending = {}  # employee_id -> IN event row waiting for its OUT

    for ev in events:
        emp = ev["employee_id"]
        if ev["event_type"] == "IN":
            if emp in pending:
                shifts.append(_unfinished(pending[emp], open_in_event_ids))
            pending[emp] = ev
        else:
            start_ev = pending.pop(emp, None)
            if start_ev is None:
                orphans.append(OrphanOut(emp, ev["employee_name"], parse_ts(ev["ts"]), ev["id"]))
            else:
                shifts.append(Shift(
                    emp, ev["employee_name"], parse_ts(start_ev["ts"]), parse_ts(ev["ts"]),
                    start_ev["id"], ev["id"], "complete",
                ))

    for start_ev in pending.values():
        shifts.append(_unfinished(start_ev, open_in_event_ids))

    shifts.sort(key=lambda s: (s.start, s.employee_name))
    return shifts, orphans


def _unfinished(ev, open_in_event_ids):
    status = "open" if ev["id"] in open_in_event_ids else "missing_out"
    return Shift(ev["employee_id"], ev["employee_name"], parse_ts(ev["ts"]), None,
                 ev["id"], None, status)


def week_start_of(day, week_start):
    """week_start: 0 = Monday ... 6 = Sunday."""
    return day - timedelta(days=(day.weekday() - week_start) % 7)


def summarize(shifts, week_start):
    """Returns (daily, weekly, per_employee) totals in seconds.
    daily:  {(date, employee_name): seconds}
    weekly: {(week_start_date, employee_name): seconds}
    per_employee: {employee_name: seconds}"""
    daily = defaultdict(float)
    weekly = defaultdict(float)
    per_employee = defaultdict(float)
    for s in shifts:
        if s.status != "complete":
            continue
        daily[(s.work_date, s.employee_name)] += s.seconds
        weekly[(week_start_of(s.work_date, week_start), s.employee_name)] += s.seconds
        per_employee[s.employee_name] += s.seconds
    return dict(daily), dict(weekly), dict(per_employee)


# --------------------------------------------------------------- formatting
# (Written by hand because Windows doesn't support strftime's "%-I".)

def fmt_time(dt):
    hour = dt.hour % 12 or 12
    return f"{hour}:{dt.minute:02d} {'AM' if dt.hour < 12 else 'PM'}"


def fmt_date(d):
    return f"{d.strftime('%a, %b')} {d.day}"


def fmt_hours(seconds):
    """Decimal hours for payroll, e.g. 7.5 hours -> '7.50'."""
    return f"{seconds / 3600:.2f}"


def fmt_hm(seconds):
    minutes = int(round(seconds / 60))
    return f"{minutes // 60}h {minutes % 60:02d}m"
