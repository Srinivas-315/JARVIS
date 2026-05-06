"""
JARVIS — skills/call_monitor.py
Monitors for incoming calls and announces caller via JARVIS voice.

Supports:
  ✅ WhatsApp Desktop  — window title + notification
  ✅ Microsoft Phone Link (Your Phone) — Android calls mirrored to PC
  ✅ Skype — window title
  ✅ Microsoft Teams — window title
  ✅ Auto-answer / Decline by voice command

Voice commands after JARVIS announces a call:
  "Answer"  / "Pick up"  / "Accept"  → auto-answers
  "Decline" / "Reject"   / "Ignore"  → declines/dismisses

How call detection works on Windows:
  1. Window title polling — works for WhatsApp Desktop, Skype, Teams
  2. Phone Link (YourPhone / PhoneExperienceHost) — mirrors Android calls
  3. Windows Toast Notification reader via PowerShell (fallback)
"""

import re
import time
import threading
import subprocess
from pathlib import Path
from utils.logger import log


# ─── Config ───────────────────────────────────────────────────
CHECK_INTERVAL   = 1.2     # seconds between polls
ANNOUNCE_COOLDOWN = 20     # seconds before re-announcing same caller
ANSWER_WINDOW    = 25      # seconds to wait for voice answer/decline command


# ─── Key combos to answer / decline per app ───────────────────
APP_KEYS = {
    "WhatsApp":            {"answer": "%a",   "decline": "%d"},   # Alt+A / Alt+D
    "Phone Link":          {"answer": "{F10}","decline": "{ESC}"},
    "Skype":               {"answer": "%a",   "decline": "%d"},
    "Teams":               {"answer": "%a",   "decline": "%d"},
}


class CallMonitor:
    """
    Background thread that watches for incoming calls across all apps.
    Announces the caller and optionally auto-answers via keyboard shortcut.
    """

    def __init__(self, speak_fn=None, listen_fn=None, on_call_fn=None):
        """
        speak_fn  : jarvis._speak (makes JARVIS talk)
        listen_fn : jarvis.listener.listen (captures voice reply)
        on_call_fn: optional callback(caller, source) for extra logic
        """
        self._speak    = speak_fn
        self._listen   = listen_fn
        self._callback = on_call_fn
        self._running  = False
        self._thread   = None

        # Debounce: track last announced call
        self._last_call      = None
        self._last_call_time = 0

        # Track active call state
        self._active_call    = False

    # ══════════════════════════════════════════════════════════
    # PUBLIC API
    # ══════════════════════════════════════════════════════════

    def start(self):
        """Start background call monitoring thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        log.info("📞 Call monitor started — watching WhatsApp, Phone Link, Skype, Teams")

    def stop(self):
        """Stop monitoring."""
        self._running = False
        log.info("📞 Call monitor stopped")

    # ══════════════════════════════════════════════════════════
    # MAIN POLL LOOP
    # ══════════════════════════════════════════════════════════

    def _loop(self):
        while self._running:
            try:
                detected = (
                    self._check_whatsapp()
                    or self._check_phone_link()
                    or self._check_skype()
                    or self._check_teams()
                    or self._check_toast_notifications()
                )
                if detected:
                    caller, source = detected
                    self._handle_incoming(caller, source)
            except Exception as e:
                log.warning(f"Call monitor poll error: {e}")
            time.sleep(CHECK_INTERVAL)

    # ══════════════════════════════════════════════════════════
    # DETECTORS — one per app
    # ══════════════════════════════════════════════════════════

    def _check_whatsapp(self):
        """
        Detect WhatsApp Desktop incoming calls via window title.
        Titles seen in the wild:
          'Incoming voice call - John Doe'
          'Incoming video call - John Doe'
          'John Doe - Incoming call'
          'WhatsApp - Incoming call from John Doe'
        """
        titles = self._get_titles("WhatsApp")
        for title in titles:
            caller = self._parse_caller(title, [
                r'incoming (?:voice|video) call[\s\-–]+(.+)',
                r'^(.+?)[\s\-–]+incoming',
                r'from\s+(.+?)(?:\s+on\s+whatsapp)?$',
            ])
            if caller:
                return caller, "WhatsApp"

            # Generic — "incoming" in title but no name parsed
            if "incoming" in title.lower():
                return "someone", "WhatsApp"
        return None

    def _check_phone_link(self):
        """
        Detect Android calls mirrored to PC via Microsoft Phone Link.
        Process names: 'YourPhone' or 'PhoneExperienceHost'
        Titles:
          'Incoming call - John Doe'
          'Call from John Doe'
          '+91 98765 43210'
        """
        titles = self._get_titles("YourPhone") + self._get_titles("PhoneExperienceHost")
        for title in titles:
            caller = self._parse_caller(title, [
                r'incoming call[\s\-–]+(.+)',
                r'call from (.+)',
                r'(\+?\d[\d\s\-]{7,})',   # raw phone number
            ])
            if caller:
                return caller, "Phone Link"
        return None

    def _check_skype(self):
        """Detect Skype incoming calls via window title."""
        titles = self._get_titles("Skype")
        for title in titles:
            caller = self._parse_caller(title, [
                r'incoming call[\s\-–]+(.+)',
                r'call from (.+)',
                r'(.+?) is calling',
            ])
            if caller:
                return caller, "Skype"
        return None

    def _check_teams(self):
        """Detect Microsoft Teams calls via window title."""
        titles = self._get_titles("Teams")
        for title in titles:
            caller = self._parse_caller(title, [
                r'incoming call[\s\-–]+(.+)',
                r'(.+?) is calling',
                r'call from (.+)',
            ])
            if caller:
                return caller, "Microsoft Teams"
        return None

    def _check_toast_notifications(self):
        """
        Read Windows Toast Notifications via PowerShell.
        Catches notifications from apps that don't change their window title
        (e.g. WhatsApp minimized to tray).
        """
        try:
            # PowerShell script to read recent notifications from Windows
            ps_script = r"""
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() |
    Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
        $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]

function Await($WinRtTask, $ResultType) {
    $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
    $netTask = $asTask.Invoke($null, @($WinRtTask))
    $netTask.Wait(-1) | Out-Null
    $netTask.Result
}

[Windows.UI.Notifications.Management.UserNotificationListener,
 Windows.UI.Notifications.Management, ContentType = WindowsRuntime] | Out-Null

$listener = [Windows.UI.Notifications.Management.UserNotificationListener]::Current
$notifs = Await $listener.GetNotificationsAsync(
    [Windows.UI.Notifications.NotificationKinds]::Toast
) ([System.Collections.Generic.IReadOnlyList[Windows.UI.Notifications.UserNotification]])

foreach ($n in $notifs) {
    $appName = $n.AppInfo.DisplayInfo.DisplayName
    $binding = $n.Notification.Visual.Bindings | Select-Object -First 1
    if ($binding) {
        $texts = $binding.GetTextElements() | ForEach-Object { $_.Text }
        Write-Output "$appName|$($texts -join '|')"
    }
}
"""
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_script],
                capture_output=True, text=True, timeout=3
            )
            for line in result.stdout.splitlines():
                parts = line.split("|")
                if len(parts) < 2:
                    continue
                app_name = parts[0].strip()
                content  = " ".join(parts[1:]).strip().lower()

                if "incoming" in content or "calling" in content or "call from" in content:
                    # Try to extract caller name from notification text
                    caller = self._parse_caller(" ".join(parts[1:]), [
                        r'incoming (?:voice|video) call[\s\-–]+(.+)',
                        r'(.+?) is calling',
                        r'call from (.+)',
                    ]) or parts[1].strip()
                    source = app_name or "notification"
                    return caller, source
        except Exception as e:
            log.debug(f"Toast notification check failed (non-critical): {e}")
        return None

    # ══════════════════════════════════════════════════════════
    # HANDLE INCOMING CALL
    # ══════════════════════════════════════════════════════════

    def _handle_incoming(self, caller: str, source: str):
        """Announce call and wait for voice command to answer/decline."""
        # Debounce — don't repeat same call
        now = time.time()
        call_id = f"{caller.lower()}_{source.lower()}"
        if call_id == self._last_call and (now - self._last_call_time) < ANNOUNCE_COOLDOWN:
            return

        self._last_call      = call_id
        self._last_call_time = now

        # ── Announce ──────────────────────────────────────────
        msg = f"Sir, incoming call from {caller} on {source}."
        log.info(f"📞 {msg}")
        print(f"\n\033[95m📞  {msg}\033[0m")

        if self._speak:
            self._speak(msg)
            # Give speaker a moment to finish
            time.sleep(0.5)
            self._speak("Say 'answer' to pick up, or 'decline' to reject.")

        # ── Optional callback ─────────────────────────────────
        if self._callback:
            self._callback(caller, source)

        # ── Listen for answer/decline command ─────────────────
        if self._listen:
            self._wait_for_command(caller, source)

    def _wait_for_command(self, caller: str, source: str):
        """Listen for up to ANSWER_WINDOW seconds for answer/decline."""
        deadline = time.time() + ANSWER_WINDOW
        while time.time() < deadline:
            try:
                text = self._listen(timeout=6)
                if not text:
                    continue
                t = text.lower().strip()
                if any(w in t for w in ["answer", "pick up", "accept", "receive", "lift"]):
                    self._answer_call(source)
                    return
                if any(w in t for w in ["decline", "reject", "ignore", "dismiss",
                                         "no", "cut", "don't answer", "hang up"]):
                    self._decline_call(source)
                    return
            except Exception:
                break

    # ══════════════════════════════════════════════════════════
    # ANSWER / DECLINE
    # ══════════════════════════════════════════════════════════

    def _answer_call(self, source: str):
        """Auto-answer the call using keyboard shortcut."""
        log.info(f"📞 Answering {source} call...")
        if self._speak:
            self._speak("Answering the call, sir.")

        # Bring the app window to front then send shortcut
        app_proc = self._source_to_process(source)
        if app_proc:
            self._focus_window(app_proc)
            time.sleep(0.5)

        keys = APP_KEYS.get(source, {}).get("answer", "%a")
        self._send_keys(app_proc, keys)

    def _decline_call(self, source: str):
        """Decline / dismiss the call."""
        log.info(f"📞 Declining {source} call...")
        if self._speak:
            self._speak("Declining the call, sir.")

        app_proc = self._source_to_process(source)
        if app_proc:
            self._focus_window(app_proc)
            time.sleep(0.5)

        keys = APP_KEYS.get(source, {}).get("decline", "{ESC}")
        self._send_keys(app_proc, keys)

    # ══════════════════════════════════════════════════════════
    # WINDOWS HELPERS
    # ══════════════════════════════════════════════════════════

    def _get_titles(self, process_name: str) -> list:
        """Get all window titles for a given process name via PowerShell."""
        try:
            cmd = (
                f"Get-Process '{process_name}' -ErrorAction SilentlyContinue "
                f"| Select-Object -ExpandProperty MainWindowTitle"
            )
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", cmd],
                capture_output=True, text=True, timeout=2
            )
            return [t.strip() for t in result.stdout.splitlines() if t.strip()]
        except Exception:
            return []

    def _focus_window(self, process_name: str):
        """Bring app window to foreground."""
        try:
            ps = (
                f"$p = Get-Process '{process_name}' -ErrorAction SilentlyContinue | "
                f"Select-Object -First 1; "
                f"if ($p) {{ "
                f"  Add-Type -AssemblyName Microsoft.VisualBasic; "
                f"  [Microsoft.VisualBasic.Interaction]::AppActivate($p.Id) "
                f"}}"
            )
            subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                           capture_output=True, timeout=3)
        except Exception as e:
            log.debug(f"Focus window failed: {e}")

    def _send_keys(self, process_name: str, keys: str):
        """Send keyboard shortcut to focused window via PowerShell SendKeys."""
        try:
            ps = (
                f"Add-Type -AssemblyName System.Windows.Forms; "
                f"[System.Windows.Forms.SendKeys]::SendWait('{keys}')"
            )
            subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                           capture_output=True, timeout=3)
            log.info(f"Sent keys '{keys}' to {process_name}")
        except Exception as e:
            log.warning(f"SendKeys failed: {e}")

    def _source_to_process(self, source: str) -> str:
        """Map source name to Windows process name."""
        mapping = {
            "WhatsApp":        "WhatsApp",
            "Phone Link":      "PhoneExperienceHost",
            "Skype":           "Skype",
            "Microsoft Teams": "Teams",
        }
        return mapping.get(source, "")

    def _parse_caller(self, text: str, patterns: list) -> str:
        """Try regex patterns against text, return first match or None."""
        for pattern in patterns:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                name = m.group(1).strip().rstrip("-–—").strip()
                if name and len(name) > 1:
                    return name
        return None


# ─── Standalone test ─────────────────────────────────────────
if __name__ == "__main__":
    def fake_speak(text):
        print(f"🔊 JARVIS: {text}")

    def fake_listen(timeout=6):
        return input("🎤 Your command: ")

    monitor = CallMonitor(speak_fn=fake_speak, listen_fn=fake_listen)
    monitor.start()
    print("📞 Call monitor running — watching for incoming calls...")
    print("    Monitors: WhatsApp, Phone Link, Skype, Teams")
    print("    Press Ctrl+C to stop")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        monitor.stop()
        print("Stopped.")
