# NFC Clock-In/Clock-Out System: Project Tracker

_Last updated: 2026-10-22_

This file tracks the whole project: requirements, decisions, open questions, and progress.
The app itself is in [`timeclock/`](timeclock/). The setup guide is [`timeclock/SETUP.md`](timeclock/SETUP.md).

**Status:** Code and setup guide written. **Next: set it up on the Windows PC (see section 7).**

---

## 1. Project Brief (summary)

A cheap, simple employee time clock for a small shop with **2 employees**.

- An NFC tag is mounted on the wall inside a 3D-printed cover.
- Employees tap their phone on the tag. The tag opens a URL in the phone's browser (no app needed).
- The URL points to a small web app running on an always-on Windows PC acting as a local server.
- Employees identify themselves and log **Clock In** / **Clock Out** with a timestamp.
- Data is stored locally (SQLite) with CSV export.
- An admin view shows timesheets (hours per employee per day/week) for payroll.

### Constraints
- No cloud subscriptions or paid services. Everything runs locally.
- Must work reliably on home/office Wi-Fi (local address; Tailscale for remote admin).
- Owner is comfortable with VS Code and Claude Code but not an expert developer, so explanations need to be clear.
- The 3D-printed enclosure is handled separately. Software assumes the tag reliably triggers the URL.

---

## 2. Requirements Checklist

✅ = built. 🧪 = built but must be verified on the Windows PC (nothing was installed or run on the Mac except a syntax check and the timesheet-math tests, which passed).

### 2.1 Web app / local server
- ✅🧪 Lightweight local web server: Python + Flask, served by Waitress (`app.py`, `serve.py`)
- ✅🧪 Mobile-friendly page opened by the NFC tap (`/`)
- ✅🧪 Employee taps their name; the phone remembers them after that ("Not you? Switch person" link)
- ✅🧪 Clock In / Clock Out
- ✅🧪 Records employee, date, time, type (in/out), and source (phone tap vs. admin fix) in SQLite (`data/timeclock.db`)
- ✅🧪 Prevents double clock-in: page shows only the valid next action, and the server re-checks before saving (double-tap safe)

### 2.2 Admin view (`/admin`)
- ✅🧪 Password protected (hashed password, 12-hour login, form tokens)
- ✅🧪 Event log of all clock-in/out events, filterable, with add/delete for fixes
- ✅🧪 Total hours per employee per **day**
- ✅🧪 Total hours per employee per **week**
- ✅🧪 CSV export: weekly hours, daily hours, shifts, all events
- ✅🧪 Extras: "Right now" status, "Clock out now", problem detection (forgotten clock-out, 14h+ shifts, clock-out without clock-in) with one-click fix links, employee management, backup download

### 2.3 Run 24/7 (Windows)
- ✅🧪 Auto-start at boot, even with nobody logged in (Task Scheduler, runs as SYSTEM)
- ✅🧪 Runs in the background (no window)
- ✅🧪 Auto-restart on crash (restart loop in `windows/start_server.bat`)
- ✅🧪 Sleep/hibernate disabled while plugged in (done by the install script)
- ✅🧪 Firewall opened only for local network + Tailscale
- ✅ BIOS "power on after outage" explained in SETUP.md

### 2.4 NFC tag guidance (SETUP.md section 8)
- ✅ Tag type: NTAG213 (anti-metal version if on metal)
- ✅ URL format: `http://<PC address>:8080/`
- ✅ Free apps: NFC Tools or NXP TagWriter, with steps
- ✅ Locking the tag (optional) + enclosure tips

### 2.5 UI
- ✅ Clean, mobile-friendly design, automatic dark mode
- ✅ Large buttons, confirmation page after each tap (shows time, shift length, today's total)

---

## 3. Deliverables

| # | Deliverable | Status |
|---|-------------|--------|
| 1 | Full working code (web app + local server) | ✅ Written: `timeclock/` (to be run on the Windows PC) |
| 2 | Setup guide: prerequisites | ✅ SETUP.md §1–4 |
| 3 | Setup guide: running 24/7 | ✅ SETUP.md §6–7 |
| 4 | Setup guide: writing NFC tags | ✅ SETUP.md §8 |
| 5 | Setup guide: accessing admin/timesheet view | ✅ SETUP.md §10–11 |
| 6 | Setup guide: backing up data | ✅ SETUP.md §12 |
| 7 | Setup guide: troubleshooting | ✅ SETUP.md §15 |
| + | Automated tests | ✅ `timeclock/tests/` (run automatically by `first_time_setup.bat`) |

---

## 4. Clarifying Questions (answered)

| # | Question | Answer |
|---|----------|--------|
| Q1 | How should employees be identified? | **Name buttons.** Phone remembers the employee after first tap, with a "Not you?" link. |
| Q2 | One tag with a choice screen, or two tags (in / out)? | **One tag, smart screen.** Shows only the valid next action. |
| Q3 | What OS does the always-on desktop run? | **Windows PC.** (Written on the Mac; Python code is cross-platform.) |
| Q4 | Local network only, or remote access? | **Shop Wi-Fi for clocking + remote admin access** via Tailscale (free, no port forwarding). |
| Q5 | Employee names | Added in the admin page, not hard-coded. |
| Q6 | Week start day for weekly totals | Monday by default, changeable in `data/config.json`. |
| Q7 | Time zone | Uses the Windows PC's clock/time zone. |
| Q8 | Where to install and test | On the work PC only. Nothing installed on the Mac. |

---

## 5. Decisions Log

| Date | Decision | Reason |
|------|----------|--------|
| 2026-10-22 | Stack: Python 3 + Flask + SQLite | Free, simple, single folder, no separate database server, easy to back up (one file). |
| 2026-10-22 | Admin page is password protected | Employees share the same network, so admin pages must not be open. |
| 2026-10-22 | Web server: Waitress (not Flask's dev server) | Production-grade, pure Python, works on Windows. |
| 2026-10-22 | 24/7 on Windows: Task Scheduler (at startup, as SYSTEM) + a restart loop in a `.bat` file | Built into Windows, no extra installs, restarts within seconds after a crash. |
| 2026-10-22 | Install location `C:\TimeClock` (not Documents/Desktop) | Documents/Desktop are often synced by OneDrive, which can corrupt a live database file. |
| 2026-10-22 | Firewall rule allows only local subnet + Tailscale range (100.64.0.0/10) | Reachable from shop Wi-Fi and your Tailscale devices, nothing else. |
| 2026-10-22 | A shift's hours count on the day it started | Keeps overnight shifts simple; unlikely in a small shop. |
| 2026-10-22 | Automatic daily database backup, keeps last 60 | Protects against mistakes or file corruption with zero effort. |
| 2026-10-22 | Admin can add/delete events and clock someone out | People forget to clock out; payroll needs a way to fix it. |
| 2026-10-22 | After clocking in/out, show a confirmation page (no button) | Prevents an accidental second tap from immediately clocking back out. |
| 2026-10-22 | Use `http://` on port 8080 | HTTPS on a local IP needs certificates and causes browser warnings; traffic never leaves the shop network (or is encrypted by Tailscale). |
| 2026-10-22 | No install/test on the Mac | Owner's preference. Tests run on the Windows PC during setup. |

---

## 6. Progress Log

- **2026-10-22**: Project tracker created. Clarifying questions answered (see section 4).
- **2026-10-22**: Built the app (`timeclock/`): employee pages, admin timesheet, event log, employees, CSV exports, backups, Windows auto-start scripts, automated tests, and `SETUP.md`. Checked on the Mac without installing anything: all Python files parse, and the timesheet math tests pass (5/5). The web-page tests run on the Windows PC.

---

## 7. Next Steps (owner)

Follow [`timeclock/SETUP.md`](timeclock/SETUP.md) on the Windows PC:

1. [ ] Buy NTAG213 tags (§1)
2. [ ] Install Python (§2)
3. [ ] Copy `timeclock` folder to `C:\TimeClock` (§3)
4. [ ] Run `windows\first_time_setup.bat`; confirm all tests say **OK** (§4)
5. [ ] Test run, add both employees, test from a phone (§5)
6. [ ] DHCP reservation in the router so the PC's address never changes (§6)
7. [ ] Run `windows\install_autostart.bat`, then reboot to confirm it comes back (§7)
8. [ ] Write and test the NFC tag (§8)
9. [ ] Set up Tailscale for remote admin (§11)
10. [ ] Set up an off-site backup habit (§12)
11. [ ] Set `shop_name` in `data\config.json` (§13)

If anything fails, note the error here and bring it back to Claude Code (include the end of `data\server.log`).

## 8. Possible Future Improvements (not built)

- Per-employee PIN (if buddy-punching ever becomes a concern)
- Break tracking (separate "start break / end break")
- Overtime highlighting (e.g. over 40 h/week)
- Automatic copy of backups to a USB drive or cloud folder
