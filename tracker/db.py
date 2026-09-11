"""
db.py
-----
SQLite storage shared by the menu bar tracker and the Flask dashboard.
One file, one schema, no server needed — both processes just open the
same .db file (SQLite handles the concurrent access fine at this scale).

Tables:
  events   — every raw app-switch / classification event (append-only log)
  sessions — merged, closed intervals of continuous focus/distraction time
  daily    — one row per calendar day: total focus & distraction seconds,
             whether the day's goal was met (used for streak calculation)
"""

import os
import sqlite3
from datetime import datetime, date
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "study_discipline.db")
DB_PATH = os.path.abspath(DB_PATH)


SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,              -- ISO timestamp
    app_name TEXT NOT NULL,
    window_title TEXT,
    category TEXT NOT NULL         -- 'focus' | 'distraction' | 'neutral'
);

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    start_ts TEXT NOT NULL,
    end_ts TEXT NOT NULL,
    category TEXT NOT NULL,        -- 'focus' | 'distraction' | 'neutral'
    app_name TEXT NOT NULL,
    duration_seconds REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS daily (
    day TEXT PRIMARY KEY,          -- 'YYYY-MM-DD'
    focus_seconds REAL NOT NULL DEFAULT 0,
    distraction_seconds REAL NOT NULL DEFAULT 0,
    goal_met INTEGER NOT NULL DEFAULT 0,
    warnings_triggered INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

DEFAULT_CONFIG = {
    "daily_goal_minutes": "60",         # focus minutes/day to keep the streak alive
    "distraction_warn_seconds": "60",   # continuous distraction time before first nag
    "distraction_hard_seconds": "180",  # continuous distraction time before fullscreen overlay
    "poll_interval_seconds": "5",
}


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        for k, v in DEFAULT_CONFIG.items():
            conn.execute(
                "INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)", (k, v)
            )


def get_config(key: str) -> str:
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM config WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else DEFAULT_CONFIG.get(key)


def set_config(key: str, value: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO config (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


def log_event(app_name: str, window_title: str, category: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO events (ts, app_name, window_title, category) VALUES (?, ?, ?, ?)",
            (datetime.now().isoformat(), app_name, window_title, category),
        )


def close_session(start_ts: datetime, end_ts: datetime, category: str, app_name: str):
    """Record one continuous block of time spent in a given category, and
    roll it into that day's totals."""
    duration = (end_ts - start_ts).total_seconds()
    if duration < 1:
        return

    with get_conn() as conn:
        conn.execute(
            "INSERT INTO sessions (start_ts, end_ts, category, app_name, duration_seconds) "
            "VALUES (?, ?, ?, ?, ?)",
            (start_ts.isoformat(), end_ts.isoformat(), category, app_name, duration),
        )

        day = start_ts.date().isoformat()
        conn.execute(
            "INSERT INTO daily (day, focus_seconds, distraction_seconds) "
            "VALUES (?, 0, 0) ON CONFLICT(day) DO NOTHING",
            (day,),
        )
        if category == "focus":
            conn.execute(
                "UPDATE daily SET focus_seconds = focus_seconds + ? WHERE day = ?",
                (duration, day),
            )
        elif category == "distraction":
            conn.execute(
                "UPDATE daily SET distraction_seconds = distraction_seconds + ? WHERE day = ?",
                (duration, day),
            )

        goal_seconds = int(get_config("daily_goal_minutes")) * 60
        row = conn.execute("SELECT focus_seconds FROM daily WHERE day = ?", (day,)).fetchone()
        goal_met = 1 if row and row["focus_seconds"] >= goal_seconds else 0
        conn.execute("UPDATE daily SET goal_met = ? WHERE day = ?", (goal_met, day))


def increment_warning_count(day: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO daily (day, warnings_triggered) VALUES (?, 1) "
            "ON CONFLICT(day) DO UPDATE SET warnings_triggered = warnings_triggered + 1",
            (day,),
        )


def get_today_stats() -> dict:
    today = date.today().isoformat()
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM daily WHERE day = ?", (today,)).fetchone()
        if row is None:
            return {"day": today, "focus_seconds": 0, "distraction_seconds": 0,
                     "goal_met": 0, "warnings_triggered": 0}
        return dict(row)


def get_current_streak() -> int:
    """Consecutive days (ending today or yesterday) where the focus goal was met."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT day, goal_met FROM daily ORDER BY day DESC"
        ).fetchall()

    if not rows:
        return 0

    days = {r["day"]: r["goal_met"] for r in rows}
    streak = 0
    cursor = date.today()
    # Today doesn't have to be complete yet to keep counting backward from yesterday
    if days.get(cursor.isoformat(), 0) != 1:
        from datetime import timedelta
        cursor = cursor - timedelta(days=1)

    from datetime import timedelta
    while days.get(cursor.isoformat(), 0) == 1:
        streak += 1
        cursor = cursor - timedelta(days=1)

    return streak


def get_longest_streak() -> int:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT day, goal_met FROM daily ORDER BY day ASC"
        ).fetchall()

    longest = current = 0
    prev_day = None
    from datetime import timedelta
    for r in rows:
        d = date.fromisoformat(r["day"])
        if r["goal_met"] == 1:
            if prev_day is not None and d == prev_day + timedelta(days=1):
                current += 1
            else:
                current = 1
            longest = max(longest, current)
            prev_day = d
        else:
            current = 0
            prev_day = d
    return longest


def get_history(days: int = 30) -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM daily ORDER BY day DESC LIMIT ?", (days,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_app_breakdown(day: str = None) -> list:
    day = day or date.today().isoformat()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT app_name, category, SUM(duration_seconds) as total_seconds "
            "FROM sessions WHERE start_ts LIKE ? "
            "GROUP BY app_name, category ORDER BY total_seconds DESC",
            (f"{day}%",),
        ).fetchall()
        return [dict(r) for r in rows]


if __name__ == "__main__":
    init_db()
    print(f"Database initialized at {DB_PATH}")
