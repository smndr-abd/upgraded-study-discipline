"""
classifier.py
-------------
Decides whether the app/site the person is currently looking at counts as
'focus', 'distraction', or 'neutral'. Fully configurable via config.json
so the person can add/remove sites without touching code.
"""

import json
import os

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app_config.json")

DEFAULT_APP_CONFIG = {
    # Matched against the frontmost app name (case-insensitive substring match)
    "distraction_apps": [
        "Instagram", "Facebook", "Telegram", "TikTok", "Twitter", "X",
        "Snapchat", "Reddit", "Discord",
    ],
    "focus_apps": [
        "Visual Studio Code", "Code", "Xcode", "Terminal", "iTerm",
        "PyCharm", "Jupyter", "Preview", "Notes", "Notion", "Obsidian",
        "Numbers", "Pages", "Keynote", "Microsoft Word", "Microsoft Excel",
    ],
    # Matched against the active tab's URL (case-insensitive substring).
    # This is the reliable path — used whenever we can fetch the real URL
    # via AppleScript (Safari, Chrome, and most Chromium browsers support this).
    "distraction_sites": [
        "youtube.com", "instagram.com", "facebook.com", "web.telegram.org",
        "tiktok.com", "twitter.com", "x.com", "reddit.com", "netflix.com",
        "twitch.tv",
    ],
    "focus_sites": [
        "stackoverflow.com", "github.com", "docs.python.org", "chatgpt.com",
        "claude.ai", "coursera.org", "leetcode.com", "kaggle.com",
        "arxiv.org", "geeksforgeeks.org",
    ],
    # Fallback keyword patterns matched against the window/tab TITLE, used
    # only when we couldn't fetch a real URL (e.g. Firefox, or Automation
    # permission not granted). Browser tab titles conventionally end with
    # "- YouTube", "| Facebook", etc, so these are safe substrings.
    "distraction_title_keywords": [
        "- YouTube", "• Instagram", "| Facebook", "/ X", "on X", "- TikTok",
        "- Reddit", "Netflix", "- Twitch",
    ],
    "focus_title_keywords": [
        "- Stack Overflow", "GitHub", "- ChatGPT", "- Claude", "- Coursera",
        "- LeetCode", "- Kaggle", "GeeksforGeeks",
    ],
    "browsers": ["Safari", "Google Chrome", "Chrome", "Arc", "Firefox", "Brave Browser"],
}


def load_app_config() -> dict:
    if not os.path.exists(CONFIG_PATH):
        save_app_config(DEFAULT_APP_CONFIG)
        return DEFAULT_APP_CONFIG
    with open(CONFIG_PATH) as f:
        return json.load(f)


def save_app_config(cfg: dict):
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


def _matches_any(text: str, needles: list) -> bool:
    text_lower = (text or "").lower()
    return any(n.lower() in text_lower for n in needles)


def classify(app_name: str, window_title: str, url: str = None) -> str:
    """
    Returns 'focus', 'distraction', or 'neutral'.

    Priority:
      1. Native app name match (Instagram.app, VS Code.app, etc.)
      2. If it's a browser and we have the real tab URL, match by domain
         (reliable — this is what catches YouTube/Instagram/Facebook used
         *in the browser* rather than as a native app).
      3. If it's a browser but URL wasn't available, fall back to matching
         known title-suffix patterns (e.g. "... - YouTube").
      4. Otherwise: neutral (browser open on some unclassified page).
    """
    cfg = load_app_config()

    if _matches_any(app_name, cfg["distraction_apps"]):
        return "distraction"
    if _matches_any(app_name, cfg["focus_apps"]):
        return "focus"

    if _matches_any(app_name, cfg["browsers"]):
        if url:
            if _matches_any(url, cfg["distraction_sites"]):
                return "distraction"
            if _matches_any(url, cfg["focus_sites"]):
                return "focus"
            return "neutral"
        # No URL available — fall back to title keyword matching
        if _matches_any(window_title, cfg["distraction_title_keywords"]):
            return "distraction"
        if _matches_any(window_title, cfg["focus_title_keywords"]):
            return "focus"
        return "neutral"

    return "neutral"


if __name__ == "__main__":
    tests = [
        ("Instagram", "", None),
        ("Google Chrome", "Home / X", "https://x.com/home"),
        ("Google Chrome", "Learn Python - GeeksforGeeks", "https://geeksforgeeks.org/python"),
        ("Visual Studio Code", "app.py — predictive-maintenance", None),
        ("Safari", "Rick Astley - Never Gonna Give You Up - YouTube", "https://youtube.com/watch?v=xyz"),
        ("Safari", "Some Video - YouTube", None),  # URL fetch failed, title fallback
        ("Finder", "", None),
    ]
    for app, title, url in tests:
        print(f"{app!r:20} {title!r:48} url={url!r:35} -> {classify(app, title, url)}")
