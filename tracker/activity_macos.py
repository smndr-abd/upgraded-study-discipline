"""
activity_macos.py
------------------
Fetches what the person is currently looking at, using AppleScript via
`osascript` — no third-party dependency needed for this part.

Requires macOS System Settings permissions (the OS will prompt the first
time you run this):
  - Accessibility          (for System Events, to get the frontmost app)
  - Automation              (for Terminal/Python to control Safari/Chrome
                             and read the active tab's URL)

If those permissions aren't granted, get_current_activity() degrades
gracefully: it'll still return the frontmost app name (that part doesn't
need Automation permission), just without a browser URL — the classifier
falls back to title-keyword matching in that case.
"""

import subprocess

FRONTMOST_APP_SCRIPT = '''
tell application "System Events"
    set frontApp to name of first application process whose frontmost is true
end tell
return frontApp
'''

WINDOW_TITLE_SCRIPT = '''
tell application "System Events"
    tell process (name of first application process whose frontmost is true)
        try
            return name of front window
        on error
            return ""
        end try
    end tell
end tell
'''

SAFARI_URL_SCRIPT = '''
tell application "Safari"
    if (count of windows) > 0 then
        return URL of current tab of front window
    end if
end tell
return ""
'''

CHROME_URL_SCRIPT = '''
tell application "{browser}"
    if (count of windows) > 0 then
        return URL of active tab of front window
    end if
end tell
return ""
'''

CHROMIUM_BROWSERS = {"Google Chrome", "Chrome", "Arc", "Brave Browser"}


def _run_applescript(script: str, timeout: float = 2.0) -> str:
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=timeout,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def get_frontmost_app() -> str:
    return _run_applescript(FRONTMOST_APP_SCRIPT) or "Unknown"


def get_window_title() -> str:
    return _run_applescript(WINDOW_TITLE_SCRIPT)


def get_browser_url(app_name: str) -> str:
    if app_name == "Safari":
        return _run_applescript(SAFARI_URL_SCRIPT)
    if app_name in CHROMIUM_BROWSERS:
        return _run_applescript(CHROME_URL_SCRIPT.format(browser=app_name))
    return ""


def get_current_activity() -> dict:
    """
    Returns {"app_name": str, "window_title": str, "url": str}.
    Safe to call repeatedly on a polling loop — each call is a couple of
    lightweight AppleScript round-trips (~10-50ms typically).
    """
    app_name = get_frontmost_app()
    window_title = get_window_title()
    url = get_browser_url(app_name) if app_name else ""
    return {"app_name": app_name, "window_title": window_title, "url": url}


def send_notification(title: str, message: str, sound: bool = True):
    sound_clause = ' sound name "Sosumi"' if sound else ""
    script = f'display notification "{message}" with title "{title}"{sound_clause}'
    _run_applescript(script)


def show_blocking_dialog(title: str, message: str, button_text: str = "I'll get back to studying"):
    """
    Shows a native macOS modal alert that requires a click to dismiss.
    Runs via osascript's own process, so it grabs focus and sits in front
    of whatever the person is doing — more attention-grabbing than a
    notification banner, without needing a separate GUI toolkit (Tkinter)
    that would fight with the menu bar app's own event loop.

    Call this from a background thread if you don't want it to block your
    polling loop while waiting for the click.
    """
    escaped_message = message.replace('"', '\\"')
    escaped_title = title.replace('"', '\\"')
    script = (
        f'display dialog "{escaped_message}" with title "{escaped_title}" '
        f'buttons {{"{button_text}"}} default button 1 with icon caution '
        f'giving up after 30'
    )
    _run_applescript(script, timeout=35)


if __name__ == "__main__":
    print("Current activity:", get_current_activity())
    send_notification("Study Discipline", "Test notification — tracker is working.")
