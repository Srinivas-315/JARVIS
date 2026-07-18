"""
JARVIS — skills/app_control.py
Advanced app & window control: minimize/maximize, snap, switch, browser tabs,
media control, smart modes (focus/work/gaming/night/morning), app usage tracker.
"""

import os
import re
import subprocess
import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta

import pyautogui
import pygetwindow as gw
import pyperclip

from utils.logger import log

pyautogui.FAILSAFE = False

# ── App name → process exe mapping ────────────────────────────
PROCESS_MAP = {
    "chrome": "chrome.exe",
    "firefox": "firefox.exe",
    "edge": "msedge.exe",
    "notepad": "notepad.exe",
    "vscode": "Code.exe",
    "code": "Code.exe",
    "spotify": "Spotify.exe",
    "discord": "Discord.exe",
    "slack": "slack.exe",
    "zoom": "Zoom.exe",
    "vlc": "vlc.exe",
    "whatsapp": "WhatsApp.exe",
    "telegram": "Telegram.exe",
    "teams": "Teams.exe",
    "word": "WINWORD.EXE",
    "excel": "EXCEL.EXE",
    "powerpoint": "POWERPNT.EXE",
    "paint": "mspaint.exe",
    "calculator": "CalculatorApp.exe",
    "taskmanager": "Taskmgr.exe",
    "explorer": "explorer.exe",
    "steam": "steam.exe",
    "obs": "obs64.exe",
    "notion": "Notion.exe",
    "figma": "Figma.exe",
    "postman": "Postman.exe",
}

# ── Website shortcuts ──────────────────────────────────────────
SITE_MAP = {
    "youtube": "https://youtube.com",
    "gmail": "https://mail.google.com",
    "whatsapp web": "https://web.whatsapp.com",
    "github": "https://github.com",
    "google": "https://google.com",
    "netflix": "https://netflix.com",
    "instagram": "https://instagram.com",
    "twitter": "https://twitter.com",
    "linkedin": "https://linkedin.com",
    "notion": "https://notion.so",
    "chatgpt": "https://chatgpt.com",
    "stackoverflow": "https://stackoverflow.com",
}

# ── Settings page shortcuts ────────────────────────────────────
SETTINGS_MAP = {
    "wifi": "ms-settings:network-wifi",
    "bluetooth": "ms-settings:bluetooth",
    "display": "ms-settings:display",
    "sound": "ms-settings:sound",
    "apps": "ms-settings:appsfeatures",
    "startup": "ms-settings:startupapps",
    "privacy": "ms-settings:privacy",
    "update": "ms-settings:windowsupdate",
    "battery": "ms-settings:batterysaver",
    "storage": "ms-settings:storagesense",
    "taskbar": "ms-settings:taskbar",
    "notifications": "ms-settings:notifications",
    "accounts": "ms-settings:yourinfo",
    "language": "ms-settings:regionlanguage",
    "mouse": "ms-settings:mousetouchpad",
    "keyboard": "ms-settings:keyboard",
    "power": "ms-settings:powersleep",
    "date": "ms-settings:dateandtime",
    "time": "ms-settings:dateandtime",
    "vpn": "ms-settings:network-vpn",
    "camera": "ms-settings:camera",
    "microphone": "ms-settings:privacy-microphone",
}

# ── Smart mode definitions ─────────────────────────────────────
MODES = {
    "work": {
        "open": ["vscode", "chrome", "notion"],
        "close": ["spotify", "discord", "steam"],
        "sites": ["https://mail.google.com", "https://github.com"],
        "message": "Work mode activated. Opening VS Code, Chrome and Notion. Closing distractions.",
    },
    "focus": {
        "open": [],
        "close": ["youtube", "discord", "steam", "spotify"],
        "sites": [],
        "message": "Focus mode on. All distractions closed. Good luck, sir.",
    },
    "gaming": {
        "open": ["steam", "discord"],
        "close": ["chrome", "vscode", "notion", "slack", "teams"],
        "sites": [],
        "message": "Gaming mode activated. Steam and Discord opening. Background apps closed.",
    },
    "night": {
        "open": [],
        "close": ["vscode", "chrome", "discord", "slack", "teams", "zoom"],
        "sites": [],
        "message": "Night mode. All work apps closed. Rest well, sir.",
    },
    "morning": {
        "open": ["chrome", "spotify"],
        "sites": [
            "https://mail.google.com",
            "https://news.google.com",
            "https://weather.com",
        ],
        "close": [],
        "message": "Good morning, sir! Opening Chrome, Spotify, Gmail, News and Weather.",
    },
}


# ─── Chrome Profile Mapping ─────────────────────────────────
CHROME_PROFILES = {
    "person 1": ("Default", "Person 1 (Srinivasa)"),
    "srinivasa": ("Default", "Person 1 (Srinivasa)"),
    "srinivas": ("Default", "Person 1 (Srinivasa)"),
    "my profile": ("Default", "Person 1 (Srinivasa)"),
    "ben": ("Profile 5", "Ben"),
    "aww": ("Profile 10", "AWW"),
    "damn bhai": ("Profile 1", "DAMN BHAI"),
    "sarvani": ("Profile 14", "Sarvani"),
    "sai sarvani": ("Profile 17", "Sai Sarvani Baisetti"),
    "mudavath": ("Profile 1", "Mudavath Ganesh"),
    "ganesh": ("Profile 1", "Mudavath Ganesh"),
}

CHROME_PROFILE_LIST = [
    ("Person 1 (Srinivasa)", "Default"),
    ("Ben", "Profile 5"),
    ("AWW", "Profile 10"),
    ("Sarvani", "Profile 14"),
    ("Sai Sarvani", "Profile 17"),
]


def _paste_type(text: str, delay: float = 0.05):
    try:
        pyperclip.copy(text)
        time.sleep(0.2)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(delay)
        return
    except Exception:
        pass
    safe = "".join(c for c in text if ord(c) < 128)
    pyautogui.typewrite(safe, interval=0.07)


class AppControl:
    """Advanced app, window, browser, and smart-mode controller."""

    # ════════════════════════════════════════════════════════
    #  APP LIFECYCLE
    # ════════════════════════════════════════════════════════

    def open_app(self, app_name: str) -> str:
        app_lower = app_name.lower().strip()

        if "chrome" in app_lower:
            profile_dir = None
            profile_name = None
            for key, (pdir, pname) in CHROME_PROFILES.items():
                if key in app_lower:
                    profile_dir = pdir
                    profile_name = pname
                    break
            return self._launch_chrome(profile_dir, profile_name)

        if "spotify" in app_lower:
            return self._launch_spotify(app_lower)

        for mode_key in MODES.keys():
            if mode_key in app_lower:
                return self.activate_mode(mode_key)

        # ── Direct App Launchers ─────────────────────────────
        # WhatsApp
        if "whatsapp" in app_lower:
            try:
                os.startfile("whatsapp://")
                log.info("Launched WhatsApp via protocol URI")
                return "Opening WhatsApp for you now, sir."
            except Exception:
                local_app_data = os.environ.get("LOCALAPPDATA", "")
                wa_path = os.path.join(local_app_data, "WhatsApp", "WhatsApp.exe")
                if os.path.exists(wa_path):
                    subprocess.Popen([wa_path])
                    log.info("Launched WhatsApp via local exe")
                    return "Opening WhatsApp for you now, sir."
                else:
                    import webbrowser
                    webbrowser.open("https://web.whatsapp.com")
                    log.info("Launched WhatsApp Web in browser")
                    return "Opening WhatsApp Web for you now, sir."

        # VS Code
        if any(w in app_lower for w in ["vscode", "vs code", "visual studio code"]):
            try:
                subprocess.Popen("code", shell=True)
                log.info("Launched VS Code")
                return "VS Code initialized, sir."
            except Exception:
                pass

        # Notepad
        if "notepad" in app_lower:
            try:
                subprocess.Popen("notepad.exe")
                log.info("Launched Notepad")
                return "Notepad opened, sir."
            except Exception:
                pass

        # Calculator
        if any(w in app_lower for w in ["calculator", "calc"]):
            try:
                os.startfile("calculator://")
                log.info("Launched Calculator via protocol")
                return "Calculator opened, sir."
            except Exception:
                try:
                    subprocess.Popen("calc.exe")
                    log.info("Launched Calculator via calc.exe")
                    return "Calculator opened, sir."
                except Exception:
                    pass

        # File Explorer
        if any(w in app_lower for w in ["explorer", "file explorer", "my computer", "this pc", "files"]):
            try:
                subprocess.Popen("explorer.exe")
                log.info("Launched File Explorer")
                return "Opening File Explorer, sir."
            except Exception:
                pass

        # Terminal
        if any(w in app_lower for w in ["terminal", "cmd", "command prompt", "powershell"]):
            try:
                subprocess.Popen("start cmd", shell=True)
                log.info("Launched Command Prompt")
                return "Terminal initialized, sir."
            except Exception:
                pass

        # Discord
        if "discord" in app_lower:
            try:
                os.startfile("discord://")
                log.info("Launched Discord via protocol")
                return "Opening Discord, sir."
            except Exception:
                local_app_data = os.environ.get("LOCALAPPDATA", "")
                discord_path = os.path.join(local_app_data, "Discord", "Update.exe")
                if os.path.exists(discord_path):
                    subprocess.Popen([discord_path, "--processStart", "Discord.exe"])
                    log.info("Launched Discord via local exe")
                    return "Opening Discord, sir."
                else:
                    import webbrowser
                    webbrowser.open("https://discord.com/app")
                    return "Opening Discord in browser, sir."

        # Telegram
        if "telegram" in app_lower:
            try:
                os.startfile("tg://")
                log.info("Launched Telegram via protocol")
                return "Opening Telegram, sir."
            except Exception:
                app_data = os.environ.get("APPDATA", "")
                tg_path = os.path.join(app_data, "Telegram Desktop", "Telegram.exe")
                if os.path.exists(tg_path):
                    subprocess.Popen([tg_path])
                    log.info("Launched Telegram via local exe")
                    return "Opening Telegram, sir."
                else:
                    import webbrowser
                    webbrowser.open("https://web.telegram.org")
                    return "Opening Telegram in browser, sir."

        search_name = app_name.strip()
        for filler in ["open ", "launch ", "start ", "the ", "app "]:
            search_name = search_name.lower().replace(filler, "").strip()

        log.info(f"Opening via Windows Search: '{search_name}'")
        try:
            pyautogui.press("win")
            time.sleep(1.5)
            _paste_type(search_name)
            time.sleep(2.0)
            pyautogui.press("enter")
            time.sleep(0.5)
            log.info(f"Launched '{search_name}' via Windows Search")
            return f"Opened {app_name}!"
        except Exception as e:
            log.error(f"Windows Search launch error: {e}")
            return f"Couldn't open {app_name}."

    def close_app(self, app_name: str) -> str:
        app_lower = app_name.lower().strip()
        app_nospace = app_lower.replace(" ", "")

        target = None
        for key, proc in PROCESS_MAP.items():
            if key in app_nospace or app_nospace in key:
                target = proc
                break
        if not target:
            target = f"{app_nospace}.exe"

        log.info(f"Closing '{app_name}' → {target}")
        try:
            result = subprocess.run(
                ["taskkill", "/IM", target, "/F"], capture_output=True, text=True
            )
            if result.returncode == 0:
                return f"Closed {app_name}!"
        except Exception as e:
            log.warning(f"taskkill error: {e}")

        try:
            for title in gw.getAllTitles():
                if title and (
                    app_lower in title.lower()
                    or app_nospace in title.lower().replace(" ", "")
                ):
                    wins = gw.getWindowsWithTitle(title)
                    for win in wins:
                        try:
                            win.close()
                        except Exception:
                            pass
                    return f"Closed {app_name}!"
        except Exception as e:
            log.warning(f"Window close error: {e}")

        return f"Couldn't find {app_name} running."

    def list_running_apps(self) -> str:
        try:
            windows = gw.getAllTitles()
            apps = [w for w in windows if w.strip()][:10]
            if apps:
                return "Currently open: " + ", ".join(apps)
            return "No windows found."
        except Exception:
            return "Couldn't list running apps."

    def _launch_chrome(self, profile_dir: str = None, profile_name: str = None) -> str:
        from pathlib import Path

        exe = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        if not os.path.exists(exe):
            exe = r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
        if not os.path.exists(exe):
            subprocess.Popen("chrome", shell=True)
            return "Opening Chrome!"

        if not profile_dir:
            names = [name for name, _ in CHROME_PROFILE_LIST]
            return "CHOOSE_PROFILE:" + ",".join(names)

        args = [exe, f"--profile-directory={profile_dir}"]
        subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return f"Opened Chrome — {profile_name or profile_dir}!"

    def _launch_spotify(self, command_text: str) -> str:
        from pathlib import Path

        exe = Path.home() / "AppData" / "Roaming" / "Spotify" / "Spotify.exe"
        if not exe.exists():
            subprocess.Popen("spotify", shell=True)
        else:
            subprocess.Popen(
                [str(exe)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        if any(w in command_text for w in ["play", "resume", "start"]):
            time.sleep(4)
            try:
                pyautogui.hotkey("ctrl", "alt", "space")
                return "Opened Spotify and started playing!"
            except Exception:
                return "Opened Spotify! Press Play to start music."
        return "Opened Spotify!"

    def __init__(self):
        self._usage: dict[str, float] = defaultdict(float)  # app → seconds today
        self._usage_start: dict[str, datetime] = {}
        self._auto_close_timers: list[threading.Timer] = []
        self._usage_lock = threading.Lock()

    # ════════════════════════════════════════════════════════
    #  WINDOW CONTROL
    # ════════════════════════════════════════════════════════

    def _find_window(self, app_name: str):
        """Find the best matching window for an app name."""
        name = app_name.lower().strip()
        # Exact title match first
        for w in gw.getAllWindows():
            if w.title and name in w.title.lower() and w.width > 10:
                return w
        return None

    def minimize_app(self, app_name: str) -> str:
        w = self._find_window(app_name)
        if not w:
            return f"Can't find {app_name} window, sir."
        try:
            w.minimize()
            return f"Minimized {app_name}."
        except Exception as e:
            return f"Couldn't minimize {app_name}: {e}"

    def maximize_app(self, app_name: str) -> str:
        w = self._find_window(app_name)
        if not w:
            return f"Can't find {app_name} window, sir."
        try:
            w.maximize()
            return f"Maximized {app_name}."
        except Exception as e:
            return f"Couldn't maximize {app_name}: {e}"

    def fullscreen_app(self, app_name: str) -> str:
        w = self._find_window(app_name)
        if not w:
            return f"Can't find {app_name} window, sir."
        try:
            w.activate()
            time.sleep(0.3)
            pyautogui.press("f11")
            return f"{app_name} toggled fullscreen."
        except Exception as e:
            return f"Couldn't fullscreen {app_name}: {e}"

    def switch_to_app(self, app_name: str) -> str:
        """Bring an app window to the foreground."""
        w = self._find_window(app_name)
        if not w:
            return f"Can't find {app_name} open, sir."
        try:
            w.restore()
            w.activate()
            return f"Switched to {app_name}."
        except Exception as e:
            # Fallback: Alt+Tab loop
            return f"Couldn't switch to {app_name}."

    def snap_window(self, app_name: str, direction: str) -> str:
        """Snap window left/right/fullscreen using Win+Arrow."""
        dir_map = {
            "left": "left",
            "right": "right",
            "up": "up",
            "down": "down",
            "fullscreen": "up",
            "maximize": "up",
        }
        key = dir_map.get(direction.lower(), "left")
        w = self._find_window(app_name)
        if not w:
            return f"Can't find {app_name} window, sir."
        try:
            w.activate()
            time.sleep(0.3)
            pyautogui.hotkey("win", key)
            return f"Snapped {app_name} to the {direction}."
        except Exception as e:
            return f"Couldn't snap {app_name}."

    def move_to_side(self, app_name: str, side: str) -> str:
        """Move window to left or right half of screen."""
        return self.snap_window(app_name, side)

    def always_on_top(self, app_name: str) -> str:
        """Pin a window always on top using PowerShell."""
        w = self._find_window(app_name)
        if not w:
            return f"Can't find {app_name} window, sir."
        try:
            hwnd = w._hWnd
            script = (
                f"Add-Type -TypeDefinition @'\n"
                f"using System;\nusing System.Runtime.InteropServices;\n"
                f"public class WinAPI {{\n"
                f'  [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h,IntPtr i,int x,int y,int w,int ht,uint f);\n'
                f"}}\n'@\n"
                f"[WinAPI]::SetWindowPos({hwnd},[IntPtr](-1),0,0,0,0,3)"
            )
            subprocess.run(
                ["powershell", "-Command", script], capture_output=True, timeout=5
            )
            return f"{app_name} is now always on top, sir."
        except Exception as e:
            return f"Couldn't pin {app_name}: {e}"

    def kill_frozen_app(self, app_name: str = None) -> str:
        """Detect and force-kill unresponsive (Not Responding) apps."""
        try:
            import psutil

            killed = []
            for proc in psutil.process_iter(["name", "status"]):
                try:
                    name = proc.info["name"] or ""
                    status = proc.info["status"]
                    if status == psutil.STATUS_ZOMBIE:
                        if app_name is None or app_name.lower() in name.lower():
                            proc.kill()
                            killed.append(name)
                except Exception:
                    pass

            # PowerShell approach for "Not Responding" windows
            if not killed:
                cmd = (
                    "Get-Process | Where-Object {$_.Responding -eq $false} "
                    "| Select-Object -ExpandProperty Name"
                )
                result = subprocess.run(
                    ["powershell", "-Command", cmd],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                frozen = [l.strip() for l in result.stdout.splitlines() if l.strip()]
                if app_name:
                    frozen = [f for f in frozen if app_name.lower() in f.lower()]
                for name in frozen:
                    subprocess.run(["taskkill", "/IM", name, "/F"], capture_output=True)
                    killed.append(name)

            if killed:
                return f"Killed frozen app{'s' if len(killed) > 1 else ''}: {', '.join(killed)}."
            return "No frozen apps found, sir."
        except Exception as e:
            return f"Couldn't check for frozen apps: {e}"

    def restart_app(self, app_name: str) -> str:
        """Close then reopen an app."""
        ctrl = self
        ctrl.close_app(app_name)
        time.sleep(2)
        return ctrl.open_app(app_name)

    # ════════════════════════════════════════════════════════
    #  BROWSER CONTROL
    # ════════════════════════════════════════════════════════

    def open_url(self, url: str, browser: str = None) -> str:
        """Open a URL in the default or specified browser."""
        import webbrowser

        if not url.startswith("http"):
            # Check site map first
            for key, full_url in SITE_MAP.items():
                if key in url.lower():
                    url = full_url
                    break
            else:
                url = "https://" + url

        if browser:
            exe_map = {
                "chrome": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                "edge": r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                "firefox": r"C:\Program Files\Mozilla Firefox\firefox.exe",
            }
            exe = exe_map.get(browser.lower())
            if exe and os.path.exists(exe):
                subprocess.Popen([exe, url])
                return f"Opening {url} in {browser}."

        webbrowser.open(url)
        return f"Opening {url}."

    def open_multiple_sites(self, sites: list[str]) -> str:
        """Open multiple websites at once."""
        import webbrowser

        opened = []
        for site in sites:
            url = SITE_MAP.get(site.lower().strip(), "https://" + site.strip())
            if not url.startswith("http"):
                url = "https://" + url
            webbrowser.open(url)
            opened.append(site)
            time.sleep(0.5)
        return f"Opened {', '.join(opened)}."

    def open_incognito(self, browser: str = "chrome", url: str = "") -> str:
        """Open browser in private/incognito mode."""
        exe_map = {
            "chrome": (
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                "--incognito",
            ),
            "edge": (
                r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                "--inprivate",
            ),
            "firefox": (
                r"C:\Program Files\Mozilla Firefox\firefox.exe",
                "--private-window",
            ),
        }
        exe, flag = exe_map.get(browser.lower(), exe_map["chrome"])
        if not os.path.exists(exe):
            subprocess.Popen(f"{browser} {flag}", shell=True)
        else:
            args = [exe, flag]
            if url:
                args.append(url)
            subprocess.Popen(args)
        return f"Opened {browser} in private mode."

    def open_chrome_profile(self, profile_key: str, url: str = "") -> str:
        """Open Chrome with a specific profile."""
        pdir, pname = CHROME_PROFILES.get(profile_key.lower(), ("Default", "Default"))
        exe = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        args = [exe, f"--profile-directory={pdir}"]
        if url:
            args.append(url)
        subprocess.Popen(args)
        return f"Opened Chrome with {pname} profile."

    def new_tab(self) -> str:
        """Open a new browser tab."""
        pyautogui.hotkey("ctrl", "t")
        return "New tab opened."

    def close_tab(self) -> str:
        """Close the current browser tab."""
        pyautogui.hotkey("ctrl", "w")
        return "Tab closed."

    def next_tab(self) -> str:
        pyautogui.hotkey("ctrl", "tab")
        return "Switched to next tab."

    def prev_tab(self) -> str:
        pyautogui.hotkey("ctrl", "shift", "tab")
        return "Switched to previous tab."

    # ════════════════════════════════════════════════════════
    #  SYSTEM APPS
    # ════════════════════════════════════════════════════════

    def open_settings(self, page: str = "") -> str:
        """Open Windows Settings, optionally to a specific page."""
        page_lower = page.lower().strip()
        for key, uri in SETTINGS_MAP.items():
            if key in page_lower:
                subprocess.Popen(["start", uri], shell=True)
                return f"Opened {key} settings."
        subprocess.Popen(["start", "ms-settings:"], shell=True)
        return "Opened Windows Settings."

    def open_task_manager(self) -> str:
        subprocess.Popen(["taskmgr"])
        return "Task Manager opened."

    def open_device_manager(self) -> str:
        subprocess.Popen(["devmgmt.msc"], shell=True)
        return "Device Manager opened."

    def open_startup_apps(self) -> str:
        subprocess.Popen(["start", "ms-settings:startupapps"], shell=True)
        return "Startup Apps settings opened."

    def open_control_panel(self, section: str = "") -> str:
        section_map = {
            "programs": "appwiz.cpl",
            "uninstall": "appwiz.cpl",
            "sound": "mmsys.cpl",
            "network": "ncpa.cpl",
            "firewall": "firewall.cpl",
            "display": "desk.cpl",
            "system": "sysdm.cpl",
        }
        for key, cpl in section_map.items():
            if key in section.lower():
                subprocess.Popen(["control", cpl])
                return f"Opened {key} control panel."
        subprocess.Popen(["control"])
        return "Control Panel opened."

    def kill_by_cpu(self, threshold: int = 80) -> str:
        """Kill the process using the most CPU above threshold%."""
        try:
            import psutil

            top = sorted(
                psutil.process_iter(["name", "cpu_percent"]),
                key=lambda p: p.info.get("cpu_percent") or 0,
                reverse=True,
            )[:5]
            killed = []
            for proc in top:
                cpu = proc.info.get("cpu_percent") or 0
                if cpu >= threshold:
                    name = proc.info["name"]
                    proc.kill()
                    killed.append(f"{name} ({cpu:.0f}%)")
            if killed:
                return f"Killed high-CPU processes: {', '.join(killed)}."
            return f"No process exceeding {threshold}% CPU."
        except Exception as e:
            return f"CPU kill failed: {e}"

    # ════════════════════════════════════════════════════════
    #  MEDIA CONTROL
    # ════════════════════════════════════════════════════════

    def pause_all_media(self) -> str:
        """Press media pause key to pause whatever is playing."""
        pyautogui.press("playpause")
        return "Paused all media."

    def vlc_play_pause(self) -> str:
        w = self._find_window("vlc")
        if w:
            w.activate()
            time.sleep(0.2)
        pyautogui.press("space")
        return "VLC play/pause toggled."

    def vlc_next(self) -> str:
        w = self._find_window("vlc")
        if w:
            w.activate()
            time.sleep(0.2)
        pyautogui.press("n")
        return "VLC next track."

    def youtube_search_play(self, query: str) -> str:
        """Open YouTube and search for a video."""
        import urllib.parse
        import webbrowser

        url = (
            f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}"
        )
        webbrowser.open(url)
        return f"Searching YouTube for '{query}'."

    # ════════════════════════════════════════════════════════
    #  APP USAGE TRACKER
    # ════════════════════════════════════════════════════════

    def start_usage_tracking(self):
        """Start background thread to track active window usage."""
        t = threading.Thread(target=self._track_usage_loop, daemon=True)
        t.start()
        log.info("App usage tracking started.")

    def stop_usage_tracking(self):
        """Stop the usage tracking (daemon thread stops on exit, this is a clean signal)."""
        log.info("App usage tracking stopped.")

    def _track_usage_loop(self):
        last_title = ""
        last_time = datetime.now()
        while True:
            try:
                import pygetwindow as gw

                active = gw.getActiveWindow()
                title = active.title if active else "Desktop"
                now = datetime.now()
                if title != last_title:
                    elapsed = (now - last_time).total_seconds()
                    with self._usage_lock:
                        self._usage[last_title] += elapsed
                    last_title = title
                    last_time = now
            except Exception:
                pass
            time.sleep(2)

    def get_usage_report(self) -> str:
        """Return today's app usage summary."""
        with self._usage_lock:
            data = dict(self._usage)
        if not data:
            return "No app usage data yet, sir."
        # Sort by time descending, skip empty
        sorted_apps = sorted(
            [(k, v) for k, v in data.items() if v > 30 and k.strip()],
            key=lambda x: x[1],
            reverse=True,
        )[:8]
        lines = []
        for name, secs in sorted_apps:
            mins = int(secs // 60)
            short = name[:40] + "..." if len(name) > 40 else name
            lines.append(f"{short}: {mins} min")
        return (
            "App usage today:\n" + "\n".join(lines)
            if lines
            else "No significant usage yet."
        )

    def get_recent_apps(self) -> str:
        """Return recently active windows."""
        try:
            wins = [w.title for w in gw.getAllWindows() if w.title and w.width > 100][
                :10
            ]
            return "Recent open apps: " + ", ".join(wins) if wins else "No apps found."
        except Exception as e:
            return f"Couldn't list apps: {e}"

    # ════════════════════════════════════════════════════════
    #  AUTO-CLOSE TIMER
    # ════════════════════════════════════════════════════════

    def auto_close_after(self, app_name: str, minutes: int) -> str:
        """Schedule an app to close after N minutes."""

        def _close():
            AppController().close_app(app_name)
            log.info(f"Auto-closed {app_name} after {minutes} min")

        t = threading.Timer(minutes * 60, _close)
        t.daemon = True
        t.start()
        self._auto_close_timers.append(t)
        return f"Got it, sir. I'll close {app_name} in {minutes} minutes."

    # ════════════════════════════════════════════════════════
    #  SMART MODES
    # ════════════════════════════════════════════════════════

    def activate_mode(self, mode_name: str) -> str:
        """Activate a smart mode (work/focus/gaming/night/morning)."""
        key = mode_name.lower().strip()
        mode = MODES.get(key)
        if not mode:
            return f"Unknown mode '{mode_name}'. Available: {', '.join(MODES.keys())}."

        ctrl = self
        import webbrowser

        # Close distracting apps
        for app in mode.get("close", []):
            try:
                ctrl.close_app(app)
            except Exception:
                pass

        time.sleep(1)

        # Open work apps
        for app in mode.get("open", []):
            try:
                ctrl.open_app(app)
                time.sleep(1.5)
            except Exception:
                pass

        # Open websites
        for url in mode.get("sites", []):
            webbrowser.open(url)
            time.sleep(0.5)

        return mode.get("message", f"{mode_name.title()} mode activated.")

    # ════════════════════════════════════════════════════════
    #  APP SUGGESTION
    # ════════════════════════════════════════════════════════

    def suggest_app(self, task: str) -> str:
        """Suggest the best app for a given task."""
        task = task.lower()
        suggestions = {
            "pdf": "Adobe Acrobat or your browser's built-in PDF viewer",
            "code": "VS Code — the best for coding",
            "video": "VLC for local files, or YouTube in Chrome",
            "music": "Spotify for streaming",
            "image": "Paint for quick edits, Photoshop for advanced work",
            "note": "Notepad for quick notes, Notion for organized notes",
            "spreadsheet": "Excel or Google Sheets",
            "presentation": "PowerPoint or Google Slides",
            "chat": "WhatsApp Desktop, Discord, or Slack",
            "meeting": "Zoom or Microsoft Teams",
            "design": "Figma for UI, Canva for quick graphics",
            "terminal": "Windows Terminal or PowerShell",
            "zip": "7-Zip or WinRAR",
        }
        for key, suggestion in suggestions.items():
            if key in task:
                return f"For {task}, I'd suggest: {suggestion}."
        return f"I'm not sure of the best app for '{task}', sir. Try searching online."
