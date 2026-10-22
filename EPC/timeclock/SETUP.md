# TimeClock Setup Guide

This guide walks you through everything from a fresh Windows PC to employees tapping the wall tag. Follow the steps in order. Each step says how to check it worked.

**What you'll end up with**

```
 Employee's phone ──tap──▶ NFC tag on wall ──opens──▶ http://192.168.1.50:8080/
                                                              │  (shop Wi-Fi)
                                                              ▼
                                         Windows PC running TimeClock 24/7
                                         • stores every clock-in/out (data\timeclock.db)
                                         • admin timesheet at /admin
                                         • backs itself up every day
                                                              ▲
 You, from home ──Tailscale (free, private)───────────────────┘
```

---

## Contents

1. [Shopping list](#1-shopping-list)
2. [Install Python](#2-install-python)
3. [Copy the TimeClock folder to the PC](#3-copy-the-timeclock-folder-to-the-pc)
4. [Run the first-time setup](#4-run-the-first-time-setup)
5. [Try it out](#5-try-it-out)
6. [Give the PC a fixed address](#6-give-the-pc-a-fixed-address)
7. [Make it run 24/7](#7-make-it-run-247)
8. [Write the NFC tag](#8-write-the-nfc-tag)
9. [How employees use it](#9-how-employees-use-it)
10. [Using the admin timesheet](#10-using-the-admin-timesheet)
11. [Remote access from home (Tailscale)](#11-remote-access-from-home-tailscale)
12. [Backups and restoring](#12-backups-and-restoring)
13. [Settings](#13-settings)
14. [Updating the code later](#14-updating-the-code-later)
15. [Troubleshooting](#15-troubleshooting)
16. [What each file does](#16-what-each-file-does)

---

## 1. Shopping list

| Item | What to buy | Approx. cost |
|------|-------------|--------------|
| NFC tags | **NTAG213** stickers, round 25 to 30 mm (a 10-pack gives you spares). NTAG215 or NTAG216 also work; they just hold more data than you need. | $5 to $12 |
| Only if mounting on metal | "Anti-metal" or "on-metal" NTAG213 tags. Normal tags don't work on or right in front of metal. | $8 to $15 |
| Server | The Windows PC you already have. A wired Ethernet connection to the router is more reliable than Wi-Fi, but Wi-Fi works. | — |
| Software | Python, Flask, Waitress, Tailscale, an NFC writing app. | All free |

Why NTAG213: every iPhone and Android phone with NFC can read it, and its 144 bytes easily holds a URL like `http://192.168.1.50:8080/`.

---

## 2. Install Python

1. On the Windows PC, go to <https://www.python.org/downloads/> and download the latest **Python 3** (3.12 or newer).
2. Run the installer. On the first screen, **tick "Add python.exe to PATH"**, then click **Install Now**.
3. **Check it worked:** open the Start menu, type `cmd`, open **Command Prompt**, and type:
   ```
   py --version
   ```
   You should see something like `Python 3.13.1`.

---

## 3. Copy the TimeClock folder to the PC

Copy the whole `timeclock` folder (USB stick, email as a zip, etc.) to:

```
C:\TimeClock
```

So you end up with `C:\TimeClock\app.py`, `C:\TimeClock\windows\...`, and so on.

> **Why not Desktop or Documents?** On many Windows PCs those folders are synced by OneDrive. OneDrive syncing a database file while it's in use can corrupt it. `C:\TimeClock` is safe.

---

## 4. Run the first-time setup

1. Open `C:\TimeClock\windows\` in File Explorer.
2. Double-click **`first_time_setup.bat`**.

It will:
- create a private `.venv` folder holding the two libraries this app needs (Flask and Waitress),
- run the automated tests (you'll see a list of tests ending with **`OK`**),
- ask you to choose an **admin password** (typing is hidden, so that's normal).

**Check it worked:** the window ends with `=== Setup complete ===`.

> If Windows shows a blue "Windows protected your PC" box, click **More info → Run anyway**. It appears for any downloaded `.bat` file.

---

## 5. Try it out

1. Double-click **`C:\TimeClock\windows\test_run.bat`**. A black window opens and shows:
   ```
   Time clock running.
     Employees (NFC tag URL): http://192.168.1.50:8080/
     Admin:                   http://192.168.1.50:8080/admin
   ```
   Your numbers will differ. **Write down that URL.**
2. If Windows Firewall pops up asking about Python, tick **Private networks** and click **Allow**.
3. On the PC, open a browser to <http://localhost:8080/admin> and log in with your admin password.
4. Go to **Employees** and add both employees' names.
5. On your phone, **connected to the shop Wi-Fi**, open the employee URL you wrote down (e.g. `http://192.168.1.50:8080/`). Tap a name, then **Clock In**, and check it shows up on the admin **Timesheet** page.
6. When you're done testing, close the black window. You can delete the test entries in **Event log**.

> If the phone can't connect but the PC can: skip ahead to step 7 (it sets up the firewall properly), then try again. Also make sure the phone is on Wi-Fi, not mobile data.

---

## 6. Give the PC a fixed address

The NFC tag has the PC's address written into it. Most routers hand out addresses that can **change** after a restart, which would break the tag. The fix is a "DHCP reservation" in your router, which tells it to always give this PC the same address.

1. On the PC, open Command Prompt and run `ipconfig /all`. Under the adapter you use (Ethernet or Wi-Fi), note:
   - **IPv4 Address**, e.g. `192.168.1.50`
   - **Physical Address**, e.g. `A4-BB-6D-12-34-56`
   - **Default Gateway**, e.g. `192.168.1.1` (that's your router)
2. Open the Default Gateway address in a browser and log in to your router. The login is often printed on a sticker on the router.
3. Find the setting called **DHCP Reservation**, **Address Reservation**, **Static Lease**, or **Fixed IP**. It's usually under LAN, DHCP, or Network settings.
4. Add a reservation: the PC's Physical (MAC) Address → its current IPv4 Address. Save.

**Also:** in Windows, open **Settings → Network & Internet → (Ethernet or Wi-Fi) → your network** and set **Network profile type** to **Private**.

**Check it worked:** restart the PC and router, then run `ipconfig` again. The address should be the same.

---

## 7. Make it run 24/7

Make sure the `test_run.bat` window is closed, then double-click:

```
C:\TimeClock\windows\install_autostart.bat
```

Click **Yes** when Windows asks for permission. It will:

| What | Why |
|------|-----|
| Creates a Task Scheduler task called **TimeClock** that runs at every boot, in the background, even if nobody logs in | Survives restarts and Windows Updates |
| Runs the server inside a loop that restarts it 5 seconds after any crash | Keeps it alive |
| Opens port 8080 in Windows Firewall, **only** for your local network and Tailscale | Phones can reach it; the internet can't |
| Turns off sleep and hibernate while plugged in (the screen can still turn off) | A sleeping PC can't answer phones |

**Check it worked:** the window ends with **"Server is running."** in green. Then **restart the PC**, don't log in, and open the employee URL on your phone. It should load.

**Power cuts (recommended):** most PCs have a BIOS/UEFI setting called **"Restore on AC Power Loss"** or **"AC Power Recovery"**. Set it to **Power On** so the PC turns itself back on after an outage. How you get into the BIOS depends on the PC (usually pressing F2, F10, or Delete at startup). Look up your PC model if unsure.

**Controls** (all in `C:\TimeClock\windows\`, double-click to run):

| File | Does |
|------|------|
| `restart_server.bat` | Restart the server (after changing settings or updating code) |
| `stop_server.bat` | Stop it until the next reboot |
| `install_autostart.bat` | Set up auto-start (safe to run again) |
| `uninstall_autostart.bat` | Remove auto-start and the firewall rule. Your data is kept. |

---

## 8. Write the NFC tag

### Get the URL
In the admin page, go to **Employees**. The bottom of the page shows the **Wall tag URL**, e.g.:

```
http://192.168.1.50:8080/
```

Use **`http://`**, not `https://`.

### Write it with your phone
Use either free app:
- **NFC Tools** by wakdev (iPhone and Android), or
- **NXP TagWriter** (iPhone and Android).

Steps in **NFC Tools**:
1. Open the app → **Write** → **Add a record** → **URL / URI**.
2. Set the prefix to `http://` and type the rest, e.g. `192.168.1.50:8080/`. Tap **OK**.
3. Tap **Write**, then hold the phone against the tag until it says the write succeeded.

### Test it
Lock your phone screen, unlock it, and tap the tag:
- **iPhone XS and newer:** hold the **top edge** of the phone to the tag. A notification banner appears; tap it to open the page.
- **iPhone 7, 8, X:** open Control Center and tap the **NFC Tag Reader** button first. (You may need to add it in Settings → Control Center.)
- **Android:** NFC must be on (Settings → Connected devices / Connections → NFC). Hold the **middle of the back** of the phone to the tag. The first time, it may ask which browser to use.

### Locking the tag (optional)
NFC Tools can **lock** the tag (Other → Lock tag) so nobody can overwrite it. **Locking is permanent.** If the PC's address ever changes, you'd need a new tag. Wait until everything has worked for a week or two before locking. Tags are cheap, so you can also just skip locking and keep spares.

### Tips for the 3D-printed cover
- Keep the plastic in front of the tag thin: **2 to 3 mm or less**.
- No metal behind or in front of the tag (unless you're using an anti-metal tag).
- Add a "Tap phone here" label or icon. Phones read best when centered on the tag.

---

## 9. How employees use it

1. Connect their phone to the **shop Wi-Fi** once. (The page won't load on mobile data, because the PC isn't on the internet.)
2. Tap the wall tag → the page opens.
3. **First time only:** tap their name. The phone remembers them after that.
4. The page shows whether they're clocked in or out, and **only the button that makes sense** (Clock In *or* Clock Out). Tap it.
5. A confirmation shows the time (and the shift length when clocking out). Done.

**"Not you? Switch person"** at the bottom lets them pick a different name, e.g. on a shared or borrowed phone. If they clear their browser data or use private browsing, they'll just pick their name again.

Double clock-ins can't happen. If someone is already clocked in, the page only offers Clock Out, and the server also re-checks before saving, so even a double-tap on the button is caught.

---

## 10. Using the admin timesheet

Open `http://<PC address>:8080/admin` (on the PC itself, `http://localhost:8080/admin` works too) and log in. You stay logged in for 12 hours.

**Timesheet page**
- **Right now:** who's clocked in. **Clock out now** fixes it if someone forgot and has already left.
- **Date range:** quick buttons (This week, Last week, This month, Last month) or pick dates.
- **Needs attention** (yellow box): forgotten clock-outs, shifts over 14 hours, clock-outs with no clock-in. Each one has a link that fills in a correction form for you.
- **Weekly hours** and **Daily hours** tables. Hours are decimal: `7.50` = 7 hours 30 minutes. A shift's hours count on the day it **started**.
- **Shifts:** every in/out pair.
- **Export (CSV):** downloads for the selected date range. CSV files open in Excel, Google Sheets, or Numbers.
  - *Weekly hours*: one row per employee per week (usually what payroll needs)
  - *Daily hours*: one row per employee per day
  - *Shifts*: every in/out pair with times
  - *All events*: every raw tap, for your records

**Suggested payroll routine:** Timesheet → **Last week** → fix anything in the yellow box → **Weekly hours** export.

**Event log page**
- Every tap, newest first. Filter by date and employee.
- **Add a missing clock-in or clock-out** at the top. Entries you add are marked "Admin".
- **To fix a wrong time:** add the correct entry, then delete the wrong one.

**Employees page**
- Add, rename, or deactivate employees. Deactivated employees disappear from the phone screen but their past hours stay in the records.

---

## 11. Remote access from home (Tailscale)

Tailscale makes a private, encrypted link between your own devices. It's free for personal use, needs no router changes, and doesn't open anything to the public internet. Employees don't install it, so clocking in still only works at the shop.

**On the Windows PC**
1. Download from <https://tailscale.com/download> and install.
2. Sign in (Google, Microsoft, or Apple account).
3. Right-click the Tailscale icon by the clock → **Preferences** (or Settings) → turn on **Run unattended**. This keeps Tailscale connected even when nobody is logged into the PC.
4. Go to <https://login.tailscale.com/admin/machines>, click the **⋯** menu next to the PC, and choose **Disable key expiry**. Otherwise it disconnects every few months until you log in again.

**On your phone or laptop**
1. Install Tailscale and sign in with the **same account**.
2. Turn Tailscale on, then open:
   ```
   http://<pc-name>:8080/admin
   ```
   where `<pc-name>` is the PC's name as shown in the Tailscale app (e.g. `http://shop-pc:8080/admin`). The `100.x.y.z` address shown in the app also works: `http://100.101.102.103:8080/admin`.

The firewall rule from step 7 already allows Tailscale addresses, so there's nothing else to set up.

---

## 12. Backups and restoring

**Where your data lives:** everything is in one file, `C:\TimeClock\data\timeclock.db`.

**Automatic backups:** the server saves a copy every day to `C:\TimeClock\data\backups\` (named like `timeclock-2026-10-22.db`) and keeps the last 60 days.

**Off-site copy (please do this):** the automatic backups sit on the same disk as the database, so if the disk dies you lose both. Pick one:
- Once a week, on the admin Timesheet page, click **download a full backup now** and save it somewhere else (e.g. email it to yourself or put it in Google Drive).
- Or copy the `C:\TimeClock\data\backups` folder to a USB stick or into OneDrive now and then. Copying the *backup* files to OneDrive is fine. Just don't put the live `timeclock.db` in OneDrive.

**Restoring a backup**
1. Double-click `windows\stop_server.bat`.
2. In `C:\TimeClock\data\`, rename `timeclock.db` to `timeclock-broken.db`. If they exist, delete `timeclock.db-wal` and `timeclock.db-shm`.
3. Copy the backup file into `C:\TimeClock\data\` and rename it to `timeclock.db`.
4. Double-click `windows\restart_server.bat`.

---

## 13. Settings

Settings are in `C:\TimeClock\data\config.json` (created on first run). Open it with Notepad:

```json
{
  "shop_name": "Time Clock",
  "port": 8080,
  "week_start": 0,
  "admin_password_hash": "…",
  "secret_key": "…"
}
```

| Setting | Meaning |
|---------|---------|
| `shop_name` | Shown at the top of every page. Put your shop's name here. |
| `port` | Leave it at 8080 unless something else on the PC uses that port. If you change it: run `install_autostart.bat` again (updates the firewall) and rewrite the NFC tag. |
| `week_start` | First day of the week for weekly totals: `0` = Monday … `6` = Sunday. |
| `admin_password_hash` | Don't edit. To change the password, run `.venv\Scripts\python set_password.py` in Command Prompt from `C:\TimeClock`. |
| `secret_key` | Don't edit or share. |

After editing, double-click `windows\restart_server.bat`.

---

## 14. Updating the code later

1. Double-click `windows\stop_server.bat`.
2. Copy the new files over the old ones in `C:\TimeClock`. **Don't overwrite or delete the `data` folder.**
3. If `requirements.txt` changed, run `first_time_setup.bat` again (it skips anything already done, re-runs the tests, and asks for the password again).
4. Double-click `windows\restart_server.bat`.

---

## 15. Troubleshooting

**First stop for any server problem:** open `C:\TimeClock\data\server.log` in Notepad and read the last 20 lines.

| Problem | Fix |
|---------|-----|
| Tapping the tag does nothing | iPhone: screen must be unlocked; use the top edge. iPhone 7/8/X need the Control Center NFC button. Android: turn NFC on. Check the cover isn't too thick and there's no metal nearby. Test the tag with the NFC Tools **Read** tab. |
| Page won't load on the phone | Is the phone on the **shop Wi-Fi** (not mobile data)? Does `http://localhost:8080/` work on the PC? If yes, run `install_autostart.bat` again (fixes firewall) and check the network is set to **Private** (step 6). |
| Worked before, now won't load anywhere | Is the PC on and awake? Run `restart_server.bat` and read its message. Check `server.log`. |
| Worked before, PC is fine, phones can't connect | The PC's address probably changed. Run `ipconfig`. If the address is different, set up the DHCP reservation (step 6) or rewrite the tag. |
| `server.log` says *address already in use* / *only one usage of each socket address* | Something else is using port 8080, or a `test_run.bat` window is still open. Close it, or change `port` in config.json (see section 13). |
| "That page had expired. Please try again." | Normal if a page sat open a long time. Just tap the button again (or re-tap the tag). |
| Employee picked the wrong name | They tap **"Not [name]? Switch person"** at the bottom of the page. |
| Someone forgot to clock out | Admin → Timesheet. It shows in the yellow box; use the link to add the clock-out with the right time. |
| Forgot the admin password | On the PC, open Command Prompt: `cd C:\TimeClock` then `.venv\Scripts\python set_password.py`. |
| Can't reach admin from home | Is Tailscale on (phone/laptop and PC)? Is **Run unattended** on, on the PC? Did the PC's key expire (step 11.4)? |
| Times are wrong | The server uses the PC's clock. Check Windows Settings → Time & language → **Set time automatically** is on, and the time zone is right. |
| Want to check everything still works | From `C:\TimeClock` in Command Prompt: `.venv\Scripts\python -m unittest discover -s tests -v` (all should say `ok`). |

---

## 16. What each file does

```
C:\TimeClock\
├── app.py              The web app: employee pages and admin pages
├── serve.py            Starts the server; also makes the daily backup
├── db.py               Saves and reads data in the SQLite database
├── timesheet.py        Pairs clock-ins with clock-outs and adds up hours
├── config.py           Reads/writes data\config.json
├── set_password.py     Sets the admin password
├── requirements.txt    The two libraries needed: Flask and Waitress
├── templates\          The HTML pages
├── static\style.css    The look of the pages
├── tests\              Automated tests
├── windows\            Setup, auto-start and control scripts (see section 7)
├── .venv\              Created by setup: Python libraries (safe to delete and re-create)
└── data\               Created on first run: YOUR DATA. Back this up.
    ├── timeclock.db       The database
    ├── config.json        Settings
    ├── server.log         Server messages
    └── backups\           Automatic daily backups
```

**About security:** the employee page has no password, by design, so taps are quick. Anyone on the shop Wi-Fi could open it and clock in as someone else. Every entry is logged with its time, and admin corrections are marked, so mistakes and misuse are easy to spot. If that ever becomes a problem, a per-employee PIN can be added. The admin pages are password protected, and the firewall only allows the local network and your Tailscale devices.
