"""
menubar_app.py
--------------
The actual "app". Lives in your macOS menu bar, polls what you're doing
every few seconds, logs it, and escalates warnings the longer you stay on
a distracting app/site:

  0s   -> distraction starts, silently timed
  60s  -> soft nag: a notification banner
  180s -> hard nag: a modal dialog that requires a click to dismiss,
          repeating every 45s for as long as you stay distracted

Run with:
    python3 menubar_app.py
(from inside the tracker/ folder, with the venv activated)
"""

import threading
import time
from datetime import datetime

import rumps

from db import (
    init_db, get_config, log_event, close_session,
    increment_warning_count, get_today_stats, get_current_streak,
)
from classifier import classify
from activity_macos import get_current_activity, send_notification, show_blocking_dialog

HARD_RENAG_INTERVAL_SECONDS = 45


def fmt_minutes(seconds: float) -> str:
    return f"{int(seconds // 60)}m"


class StudyDisciplineApp(rumps.App):
    def __init__(self):
        super().__init__("📚", quit_button=None)

        init_db()

        self.paused = False
        self.current_category = None
        self.current_app = None
        self.segment_start = None

        self.distraction_since = None
        self.warned_soft = False
        self.last_hard_nag_time = None

        self.stats_item = rumps.MenuItem("Today: — focus / — distraction")
        self.streak_item = rumps.MenuItem("🔥 Streak: —")
        self.pause_item = rumps.MenuItem("Pause tracking", callback=self.toggle_pause)
        self.dashboard_item = rumps.MenuItem("Open dashboard", callback=self.open_dashboard)
        self.quit_item = rumps.MenuItem("Quit", callback=self.quit_app)

        self.menu = [
            self.stats_item,
            self.streak_item,
            None,  # separator
            self.pause_item,
            self.dashboard_item,
            None,  # separator
            self.quit_item,
        ]

        poll_interval = float(get_config("poll_interval_seconds") or 5)
        self.timer = rumps.Timer(self.poll, poll_interval)
        self.timer.start()

        self.refresh_menu_stats()

    # ------------------------------------------------------------------
    # Menu actions
    # ------------------------------------------------------------------
    def toggle_pause(self, sender):
        self.paused = not self.paused
        sender.title = "Resume tracking" if self.paused else "Pause tracking"
        if self.paused:
            self._close_current_segment(datetime.now())
            self.title = "⏸️"
        else:
            self.title = "📚"

    def open_dashboard(self, _sender):
        import webbrowser
        webbrowser.open("http://localhost:5000")

    def quit_app(self, _sender):
        self._close_current_segment(datetime.now())
        rumps.quit_application()

    def refresh_menu_stats(self):
        stats = get_today_stats()
        focus_seconds = stats["focus_seconds"]
        distraction_seconds = stats["distraction_seconds"]

        # Add the still-open current segment's elapsed time so the display
        # is live, not just what's been closed out and written to the DB.
        if self.segment_start is not None and self.current_category in ("focus", "distraction"):
            live_elapsed = (datetime.now() - self.segment_start).total_seconds()
            if self.current_category == "focus":
                focus_seconds += live_elapsed
            else:
                distraction_seconds += live_elapsed

        self.stats_item.title = (
            f"Today: {fmt_minutes(focus_seconds)} focus / "
            f"{fmt_minutes(distraction_seconds)} distraction"
        )
        streak = get_current_streak()
        self.streak_item.title = f"🔥 Streak: {streak} day{'s' if streak != 1 else ''}"

    # ------------------------------------------------------------------
    # Core polling loop
    # ------------------------------------------------------------------
    def poll(self, _timer):
        if self.paused:
            return

        now = datetime.now()
        activity = get_current_activity()
        app_name = activity["app_name"]
        window_title = activity["window_title"]
        url = activity.get("url")

        category = classify(app_name, window_title, url)

        if category != self.current_category:
            self._close_current_segment(now)
            self.segment_start = now
            self.current_category = category
            self.current_app = app_name
            log_event(app_name, window_title, category)

            if category == "distraction":
                self.distraction_since = now
                self.warned_soft = False
                self.last_hard_nag_time = None
            else:
                self.distraction_since = None
                self.warned_soft = False
                self.last_hard_nag_time = None

        if category == "distraction" and self.distraction_since:
            elapsed = (now - self.distraction_since).total_seconds()
            soft_th = float(get_config("distraction_warn_seconds") or 60)
            hard_th = float(get_config("distraction_hard_seconds") or 180)

            if elapsed >= soft_th and not self.warned_soft:
                send_notification(
                    "Time to refocus",
                    f"You've been on {app_name} for {int(elapsed)}s. Back to studying?",
                )
                self.warned_soft = True

            if elapsed >= hard_th:
                due_for_renag = (
                    self.last_hard_nag_time is None
                    or (now - self.last_hard_nag_time).total_seconds() >= HARD_RENAG_INTERVAL_SECONDS
                )
                if due_for_renag:
                    self.last_hard_nag_time = now
                    increment_warning_count(now.date().isoformat())
                    threading.Thread(
                        target=self._fire_hard_nag,
                        args=(app_name, int(elapsed)),
                        daemon=True,
                    ).start()

        self.refresh_menu_stats()

    def _fire_hard_nag(self, app_name: str, elapsed_seconds: int):
        # Runs on a background thread so the modal dialog's wait-for-click
        # doesn't freeze the polling loop or the rest of the menu bar UI.
        show_blocking_dialog(
            "Still scrolling?",
            f"{elapsed_seconds}s on {app_name}. Close it and get back to studying.",
        )

    def _close_current_segment(self, end_time: datetime):
        if self.segment_start is not None and self.current_category is not None:
            close_session(self.segment_start, end_time, self.current_category, self.current_app)


if __name__ == "__main__":
    StudyDisciplineApp().run()
