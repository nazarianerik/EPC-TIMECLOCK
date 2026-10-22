"""NFC Time Clock: the web app.

Employee pages:  /            (opened by tapping the wall NFC tag)
Admin pages:     /admin       (password protected)
"""

import csv
import io
import logging
import secrets
import socket
import sqlite3
import time
from datetime import date, datetime, timedelta
from functools import wraps

from flask import (Flask, Response, abort, flash, g, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash

import db
from config import load_config
from timesheet import (LONG_SHIFT_HOURS, build_shifts, fmt_date, fmt_hm, fmt_hours,
                       fmt_time, summarize, week_start_of)

log = logging.getLogger("timeclock")

EMPLOYEE_COOKIE = "tc_employee"
EMPLOYEE_COOKIE_MAX_AGE = 400 * 24 * 3600  # ~13 months (browsers cap cookies at 400 days)

app = Flask(__name__)
app.config.update(
    SECRET_KEY=load_config()["secret_key"],
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
)
app.jinja_env.globals.update(fmt_time=fmt_time, fmt_date=fmt_date, fmt_hm=fmt_hm,
                             fmt_hours=fmt_hours)


# ------------------------------------------------------------------ plumbing

def get_db():
    if "db" not in g:
        g.db = db.connect()
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


@app.context_processor
def inject_globals():
    return {"shop_name": load_config()["shop_name"], "csrf_token": csrf_token,
            "is_admin": session.get("admin", False)}


def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(16)
    return session["csrf"]


@app.before_request
def check_csrf():
    """Every form includes a hidden token so other websites can't submit forms here."""
    if request.method == "POST":
        sent = request.form.get("csrf_token", "")
        if not sent or not secrets.compare_digest(sent, session.get("csrf", "")):
            flash("That page had expired. Please try again.", "error")
            return redirect(request.referrer or url_for("home"))


def admin_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("admin_login", next=request.path))
        return view(*args, **kwargs)
    return wrapper


def employee_status(conn, employee_id):
    """Returns (is_clocked_in, since_datetime_or_None)."""
    ev = db.last_event(conn, employee_id)
    if ev and ev["event_type"] == "IN":
        return True, db.parse_ts(ev["ts"])
    return False, None


def open_in_event_ids(conn):
    ids = set()
    for emp in db.list_employees(conn, include_inactive=True):
        ev = db.last_event(conn, emp["id"])
        if ev and ev["event_type"] == "IN":
            ids.add(ev["id"])
    return ids


def range_report(conn, start, end, employee_id=None):
    """Shifts and totals for shifts that STARTED between start and end dates (inclusive)."""
    # Look a couple of days past both edges so shifts crossing the edges pair up correctly.
    q_start = (start - timedelta(days=2)).strftime("%Y-%m-%d 00:00:00")
    q_end = (end + timedelta(days=3)).strftime("%Y-%m-%d 00:00:00")
    events = db.events_between(conn, q_start, q_end, employee_id)
    shifts, orphans = build_shifts(events, open_in_event_ids(conn))
    shifts = [s for s in shifts if start <= s.work_date <= end]
    orphans = [o for o in orphans if start <= o.ts.date() <= end]
    daily, weekly, per_employee = summarize(shifts, load_config()["week_start"])
    return shifts, orphans, daily, weekly, per_employee


def worked_today(conn, employee_id):
    today = date.today()
    shifts, _, _, _, per_employee = range_report(conn, today, today, employee_id)
    total = sum(per_employee.values())
    current = next((s for s in shifts if s.status == "open"), None)
    if current:
        total += (datetime.now() - current.start).total_seconds()
    return total


def lan_ip():
    """This computer's address on the local network (no data is actually sent)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def parse_date(value, default):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------- employee pages

@app.get("/")
def home():
    conn = get_db()
    remembered = request.cookies.get(EMPLOYEE_COOKIE, "")
    if remembered.isdigit():
        emp = db.get_employee(conn, int(remembered))
        if emp and emp["active"]:
            return redirect(url_for("employee_page", employee_id=emp["id"]))
    return render_template("choose.html", employees=db.list_employees(conn))


@app.get("/switch")
def switch_employee():
    resp = redirect(url_for("home"))
    resp.delete_cookie(EMPLOYEE_COOKIE)
    return resp


@app.get("/e/<int:employee_id>")
def employee_page(employee_id):
    conn = get_db()
    emp = db.get_employee(conn, employee_id)
    if not emp or not emp["active"]:
        return redirect(url_for("switch_employee"))
    is_in, since = employee_status(conn, employee_id)
    resp = Response(render_template(
        "status.html", emp=emp, is_in=is_in, since=since,
        so_far=(datetime.now() - since).total_seconds() if since else 0,
        today_total=worked_today(conn, employee_id), now_date=date.today(),
    ))
    resp.set_cookie(EMPLOYEE_COOKIE, str(employee_id), max_age=EMPLOYEE_COOKIE_MAX_AGE,
                    samesite="Lax")
    return resp


@app.post("/punch")
def punch():
    action = request.form.get("action")
    employee_id = request.form.get("employee_id", type=int)
    if action not in ("IN", "OUT") or employee_id is None:
        abort(400)
    conn = get_db()
    emp = db.get_employee(conn, employee_id)
    if not emp or not emp["active"]:
        abort(404)

    conn.execute("BEGIN IMMEDIATE")  # one punch at a time, so double taps can't sneak through
    is_in, since = employee_status(conn, employee_id)
    if action == "IN" and is_in:
        conn.rollback()
        flash(f"You're already clocked in (since {fmt_time(since)}).", "error")
        return redirect(url_for("employee_page", employee_id=employee_id))
    if action == "OUT" and not is_in:
        conn.rollback()
        flash("You're already clocked out.", "error")
        return redirect(url_for("employee_page", employee_id=employee_id))
    event_id = db.add_event(conn, employee_id, action)
    conn.commit()

    log.info("%s clocked %s", emp["name"], action)
    session["last_punch"] = event_id
    return redirect(url_for("punch_done"))


@app.get("/done")
def punch_done():
    conn = get_db()
    ev = db.get_event(conn, session.get("last_punch", 0))
    if not ev:
        return redirect(url_for("home"))
    shift_seconds = None
    if ev["event_type"] == "OUT":
        start = conn.execute(
            "SELECT ts FROM events WHERE employee_id = ? AND event_type = 'IN' AND ts <= ? "
            "ORDER BY ts DESC, id DESC LIMIT 1", (ev["employee_id"], ev["ts"])).fetchone()
        if start:
            shift_seconds = (db.parse_ts(ev["ts"]) - db.parse_ts(start["ts"])).total_seconds()
    return render_template("done.html", ev=ev, ts=db.parse_ts(ev["ts"]),
                           shift_seconds=shift_seconds,
                           today_total=worked_today(conn, ev["employee_id"]))


# ------------------------------------------------------------- admin: auth

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    pw_hash = load_config()["admin_password_hash"]
    if request.method == "POST" and pw_hash:
        if check_password_hash(pw_hash, request.form.get("password", "")):
            session.clear()
            session["admin"] = True
            session.permanent = True
            target = request.args.get("next", "")
            return redirect(target if target.startswith("/admin") else url_for("admin_dashboard"))
        time.sleep(1)  # slows down password guessing
        flash("Wrong password.", "error")
    return render_template("admin_login.html", password_set=bool(pw_hash))


@app.post("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))


# -------------------------------------------------------- admin: dashboard

def date_presets(today, week_start):
    this_week = week_start_of(today, week_start)
    last_week = this_week - timedelta(days=7)
    first_of_month = today.replace(day=1)
    last_month_end = first_of_month - timedelta(days=1)
    return {
        "This week": (this_week, this_week + timedelta(days=6)),
        "Last week": (last_week, last_week + timedelta(days=6)),
        "This month": (first_of_month, (first_of_month + timedelta(days=32)).replace(day=1)
                       - timedelta(days=1)),
        "Last month": (last_month_end.replace(day=1), last_month_end),
    }


def selected_range():
    week_start = load_config()["week_start"]
    presets = date_presets(date.today(), week_start)
    default_start, default_end = presets["This week"]
    start = parse_date(request.args.get("start"), default_start)
    end = parse_date(request.args.get("end"), default_end)
    if end < start:
        start, end = end, start
    if (end - start).days > 400:
        end = start + timedelta(days=400)
    return start, end, presets


@app.get("/admin")
@admin_required
def admin_dashboard():
    conn = get_db()
    start, end, presets = selected_range()
    week_start = load_config()["week_start"]
    shifts, orphans, daily, weekly, per_employee = range_report(conn, start, end)

    employees = db.list_employees(conn)
    statuses = []
    for emp in employees:
        is_in, since = employee_status(conn, emp["id"])
        statuses.append({"emp": emp, "is_in": is_in, "since": since})

    # Columns: active employees plus anyone (e.g. a former employee) with hours in range.
    names = [e["name"] for e in employees]
    names += sorted({s.employee_name for s in shifts} - set(names))

    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    weeks = [{"start": w, "partial": w < start or w + timedelta(days=6) > end}
             for w in sorted({week_start_of(d, week_start) for d in days})]

    now = datetime.now()
    long_open = timedelta(hours=LONG_SHIFT_HOURS)
    problems = ([s for s in shifts if s.status == "missing_out" or s.is_long
                 or (s.status == "open" and now - s.start > long_open)], orphans)

    return render_template(
        "admin_dashboard.html", start=start, end=end, presets=presets, names=names,
        employee_id=None,
        statuses=statuses, shifts=shifts, problems=problems, daily=daily, weekly=weekly,
        per_employee=per_employee, days=days, weeks=weeks, today=date.today(),
        tag_url=f"http://{lan_ip()}:{load_config()['port']}/", now=now,
    )


@app.post("/admin/clock-out/<int:employee_id>")
@admin_required
def admin_clock_out(employee_id):
    conn = get_db()
    emp = db.get_employee(conn, employee_id)
    if emp and employee_status(conn, employee_id)[0]:
        db.add_event(conn, employee_id, "OUT", source="admin", note="Clocked out by admin")
        conn.commit()
        flash(f"{emp['name']} has been clocked out.", "ok")
    return redirect(request.referrer or url_for("admin_dashboard"))


# ----------------------------------------------------------- admin: events

@app.get("/admin/events")
@admin_required
def admin_events():
    conn = get_db()
    start, end, presets = selected_range()
    employee_id = request.args.get("employee", type=int)
    events = db.events_between(conn, start.strftime("%Y-%m-%d 00:00:00"),
                               (end + timedelta(days=1)).strftime("%Y-%m-%d 00:00:00"),
                               employee_id)
    return render_template(
        "admin_events.html", events=list(reversed(events)), start=start, end=end,
        presets=presets, employees=db.list_employees(conn, include_inactive=True),
        employee_id=employee_id, parse_ts=db.parse_ts, today=date.today(),
        prefill_employee=request.args.get("add_employee", type=int),
        prefill_type=request.args.get("add_type", ""),
        prefill_date=request.args.get("add_date", date.today().isoformat()),
    )


@app.post("/admin/events/add")
@admin_required
def admin_add_event():
    conn = get_db()
    employee_id = request.form.get("employee_id", type=int)
    event_type = request.form.get("event_type")
    try:
        ts = datetime.strptime(f"{request.form.get('date')} {request.form.get('time')}",
                               "%Y-%m-%d %H:%M")
    except ValueError:
        flash("Please enter a valid date and time.", "error")
        return redirect(url_for("admin_events"))
    if not db.get_employee(conn, employee_id or 0) or event_type not in ("IN", "OUT"):
        flash("Please choose an employee and In/Out.", "error")
        return redirect(url_for("admin_events"))
    db.add_event(conn, employee_id, event_type, ts.strftime(db.TS_FORMAT), source="admin",
                 note=request.form.get("note", "").strip()[:200])
    conn.commit()
    flash("Event added.", "ok")
    day = ts.date().isoformat()
    return redirect(url_for("admin_events", start=day, end=day))


@app.post("/admin/events/<int:event_id>/delete")
@admin_required
def admin_delete_event(event_id):
    conn = get_db()
    ev = db.get_event(conn, event_id)
    if ev:
        db.delete_event(conn, event_id)
        conn.commit()
        log.info("Admin deleted event %s (%s %s at %s)", event_id, ev["employee_name"],
                 ev["event_type"], ev["ts"])
        flash(f"Deleted: {ev['employee_name']} clock-{ev['event_type'].lower()} "
              f"at {fmt_time(db.parse_ts(ev['ts']))}.", "ok")
    return redirect(request.referrer or url_for("admin_events"))


# -------------------------------------------------------- admin: employees

@app.get("/admin/employees")
@admin_required
def admin_employees():
    return render_template("admin_employees.html",
                           employees=db.list_employees(get_db(), include_inactive=True),
                           tag_url=f"http://{lan_ip()}:{load_config()['port']}/")


@app.post("/admin/employees")
@admin_required
def admin_employees_update():
    conn = get_db()
    action = request.form.get("action")
    name = " ".join(request.form.get("name", "").split())[:60]
    employee_id = request.form.get("employee_id", type=int)
    try:
        if action == "add" and name:
            db.add_employee(conn, name)
            flash(f"Added {name}.", "ok")
        elif action == "rename" and name and employee_id:
            db.rename_employee(conn, employee_id, name)
            flash(f"Renamed to {name}.", "ok")
        elif action in ("activate", "deactivate") and employee_id:
            db.set_employee_active(conn, employee_id, action == "activate")
            flash("Employee updated.", "ok")
        conn.commit()
    except sqlite3.IntegrityError:
        flash(f"There is already an employee named {name}.", "error")
    return redirect(url_for("admin_employees"))


# ----------------------------------------------------------- admin: export

def csv_response(filename, header, rows):
    buf = io.StringIO()
    buf.write("\ufeff")  # lets Excel open the file with the right character encoding
    writer = csv.writer(buf)
    writer.writerow(header)
    writer.writerows(rows)
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@app.get("/admin/export/<kind>.csv")
@admin_required
def admin_export(kind):
    conn = get_db()
    start, end, _ = selected_range()
    suffix = f"{start.isoformat()}_to_{end.isoformat()}.csv"
    shifts, orphans, daily, weekly, _ = range_report(conn, start, end)

    if kind == "shifts":
        def clock_out(s):
            if not s.end:
                return ""
            # Show the date too if the shift ended on a later day.
            return s.end.strftime("%H:%M" if s.end.date() == s.work_date else "%Y-%m-%d %H:%M")

        def note(s):
            if s.status == "open":
                return "Still clocked in"
            if s.status == "missing_out":
                return "MISSING CLOCK-OUT"
            return "Over 14 hours, please check" if s.is_long else ""

        rows = [[s.employee_name, s.work_date.isoformat(), s.start.strftime("%H:%M"),
                 clock_out(s), fmt_hours(s.seconds) if s.status == "complete" else "", note(s)]
                for s in shifts]
        return csv_response(f"shifts_{suffix}",
                            ["Employee", "Date", "Clock In", "Clock Out", "Hours", "Note"], rows)
    if kind == "daily":
        rows = [[name, d.isoformat(), fmt_hours(sec)]
                for (d, name), sec in sorted(daily.items(), key=lambda kv: (kv[0][1], kv[0][0]))]
        return csv_response(f"daily_hours_{suffix}", ["Employee", "Date", "Hours"], rows)
    if kind == "weekly":
        rows = [[name, wk.isoformat(), fmt_hours(sec)]
                for (wk, name), sec in sorted(weekly.items(), key=lambda kv: (kv[0][1], kv[0][0]))]
        return csv_response(f"weekly_hours_{suffix}", ["Employee", "Week Starting", "Hours"], rows)
    if kind == "events":
        events = db.events_between(conn, start.strftime("%Y-%m-%d 00:00:00"),
                                   (end + timedelta(days=1)).strftime("%Y-%m-%d 00:00:00"))
        rows = [[e["employee_name"], e["ts"][:10], e["ts"][11:16], e["event_type"],
                 e["source"], e["note"]] for e in events]
        return csv_response(f"all_events_{suffix}",
                            ["Employee", "Date", "Time", "Type", "Source", "Note"], rows)
    abort(404)


@app.get("/admin/backup")
@admin_required
def admin_backup():
    src = db.connect()
    mem = sqlite3.connect(":memory:")
    try:
        src.backup(mem)
        data = mem.serialize()
    finally:
        mem.close()
        src.close()
    filename = f"timeclock-backup-{datetime.now().strftime('%Y-%m-%d_%H%M')}.db"
    return Response(data, mimetype="application/octet-stream",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})
