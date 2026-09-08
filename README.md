# Study Discipline

A menu bar app that watches what you're actually doing on your Mac, nags
you when you've been on YouTube/Instagram/Facebook/Telegram/etc too long,
and tracks a daily focus streak — plus a web dashboard to see the history.

## What's inside

```
study-discipline/
├── requirements.txt
├── tracker/
│   ├── db.py              # SQLite storage (sessions, daily totals, streaks, config)
│   ├── classifier.py      # decides focus / distraction / neutral for an app or site
│   ├── activity_macos.py  # AppleScript hooks: frontmost app, tab URL, notifications, nag dialog
│   └── menubar_app.py     # the actual app — polls, classifies, logs, escalates warnings
└── dashboard/
    ├── app.py              # Flask server reading the same database
    ├── templates/index.html
    └── static/{style.css, dashboard.js}
```

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run the tracker (the actual discipline enforcer)

```bash
cd tracker
python3 menubar_app.py
```

A 📚 appears in your menu bar. The first run will prompt for macOS
permissions — **Accessibility** (to see the frontmost app) and
**Automation** (to read the active browser tab's URL, and to show
notifications/dialogs). Allow both.

**How it behaves:**
- Every 5 seconds, checks what app/site is in front
- Classifies it as `focus`, `distraction`, or `neutral` (see
  `app_config.json`, auto-created on first run — edit it to add/remove
  apps and sites)
- **60s** on a distraction → a notification banner
- **180s+** → a modal dialog requiring a click to dismiss, repeating
  every 45s until you leave
- Menu dropdown shows today's live focus/distraction time and your
  current streak
- "Pause tracking" for real breaks; "Quit" saves whatever session was
  still open

A day counts toward your streak once your total focus time crosses the
daily goal (default 60 minutes — change it any time with:
```python
from db import set_config
set_config("daily_goal_minutes", "90")
```

## Run the dashboard (view streaks & history)

In a second terminal (tracker keeps running in the first):
```bash
cd dashboard
python3 app.py
```
Open **http://localhost:5000**.

Shows: current streak, longest streak, today's progress toward goal,
a 12-week "chain" grid (amber = goal met, connected by a line for
consecutive days — don't break the chain), and today's time breakdown
by app.

Note: the dashboard only sees *closed* sessions — whatever you're doing
right now updates once you switch away from it, since that's when the
tracker writes it to the database.

## Customizing what counts as a distraction

Edit `tracker/app_config.json` (created automatically on first run):
```json
{
  "distraction_apps": ["Instagram", "Facebook", "Telegram", ...],
  "focus_apps": ["Visual Studio Code", "Xcode", "Terminal", ...],
  "distraction_sites": ["youtube.com", "instagram.com", ...],
  "focus_sites": ["stackoverflow.com", "github.com", ...]
}
```
No code changes needed — the tracker re-reads this file on each poll.

## Possible next additions

- Pomodoro timer mode (25/5 min cycles) as a menu item
- Weekly email/notification summary
- A "focus mode" that blocks distracting sites at the network level
  (would need a system extension, not just polling)
- Launch-at-login (via a LaunchAgent plist) so it starts automatically

## Created by Samandar Abudjabbar
