"""
app.py
------
Dashboard for the Study Discipline tracker. Reads from the same SQLite
database the menu bar app (tracker/menubar_app.py) writes to — no
duplicate state, just a window onto it.

Run with:
    python3 app.py
Then open http://localhost:5000

Note: today's totals reflect sessions that have already been CLOSED (i.e.
you switched away from that app at least once). Whatever you're doing
right this second won't count until you switch away from it — the tracker
process holds that "live" number in memory, the dashboard doesn't have
access to another process's memory, only to what's been written to disk.
"""

import os
import sys
from datetime import date, timedelta

from flask import Flask, jsonify, render_template

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tracker"))
import db  # noqa: E402

app = Flask(__name__)
db.init_db()


@app.route("/")
def index():
    goal_minutes = int(db.get_config("daily_goal_minutes") or 60)
    return render_template("index.html", goal_minutes=goal_minutes)


@app.route("/api/summary")
def api_summary():
    today = db.get_today_stats()
    goal_minutes = int(db.get_config("daily_goal_minutes") or 60)
    return jsonify({
        "today": today,
        "goal_seconds": goal_minutes * 60,
        "current_streak": db.get_current_streak(),
        "longest_streak": db.get_longest_streak(),
    })


@app.route("/api/history")
def api_history():
    """
    Last N days (default 84 = 12 weeks) for the chain grid, oldest first,
    padded so the grid always starts on a Monday for clean week columns.
    """
    days = 84
    rows = {r["day"]: r for r in db.get_history(days=days)}

    today = date.today()
    start = today - timedelta(days=days - 1)
    # pad backward to the most recent Monday on/before `start`
    start -= timedelta(days=start.weekday())

    result = []
    cursor = start
    while cursor <= today:
        key = cursor.isoformat()
        row = rows.get(key)
        result.append({
            "day": key,
            "focus_seconds": row["focus_seconds"] if row else 0,
            "goal_met": bool(row["goal_met"]) if row else False,
            "is_future": cursor > today,
        })
        cursor += timedelta(days=1)

    return jsonify(result)


@app.route("/api/breakdown")
def api_breakdown():
    return jsonify(db.get_app_breakdown())


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
