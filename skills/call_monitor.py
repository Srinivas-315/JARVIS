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

import os
import tempfile
import re
import time
import threading
import subprocess
import ctypes
from pathlib import Path
from utils.logger import log
import win32gui
import win32process
import win32con
import win32ui
import psutil
from PIL import Image


# ─── Config ───────────────────────────────────────────────────
CHECK_INTERVAL   = 1.2     # seconds between polls
ANNOUNCE_COOLDOWN = 20     # seconds before re-announcing same caller
ANSWER_WINDOW    = 25      # seconds to wait for voice answer/decline command


# ─── Key combos to answer / decline per app ───────────────────
APP_KEYS = {
    "WhatsApp":            {"answer": "ctrl+alt+shift+a",   "decline": "ctrl+alt+shift+d"},
    "Phone Link":          {"answer": "{F10}","decline": "{ESC}"},
    "Skype":               {"answer": "%a",   "decline": "%d"},
    "Teams":               {"answer": "%a",   "decline": "%d"},
}


class CallMonitor:
    """
    Background thread that watches for incoming calls across all apps.
    Announces the caller and optionally auto-answers via keyboard shortcut.
    """

    def __init__(self, speak_fn=None, listen_fn=None, on_call_fn=None, recent_notifs_fn=None, is_speaking_fn=None):
        """
        speak_fn  : jarvis._speak (makes JARVIS talk)
        listen_fn : jarvis.listener.listen (captures voice reply)
        on_call_fn: optional callback(caller, source) for extra logic
        recent_notifs_fn: optional callback returning list of recent notifications
        """
        self._speak    = speak_fn
        self._listen   = listen_fn
        self._callback = on_call_fn
        self._recent_notifs_fn = recent_notifs_fn
        self._is_speaking_fn = is_speaking_fn
        self._running  = False
        self._thread   = None

        # Debounce: track last announced call
        self._last_call      = None
        self._last_call_time = 0

        # Track active call state
        self._active_call    = False
        self._ocr_reader     = None

        self.monitor_stats = {
            "alive": False,
            "last_call": None,
            "last_caller": None,
            "voice_count": 0,
            "video_count": 0,
            "announcements": 0,
        }

    def feed_native_call(self, caller: str, source: str, classification: str, notif_title: str, notif_body: str):
        self.monitor_stats["alive"] = self._running
        self.monitor_stats["last_call"] = time.time()
        self.monitor_stats["last_caller"] = caller
        if "video" in classification.lower():
            self.monitor_stats["video_count"] += 1
        else:
            self.monitor_stats["voice_count"] += 1
            
        print(f"\n[CALL]\ntimestamp: {time.time()}\nwindow title: N/A (native)\nnotification title: {notif_title}\nnotification body: {notif_body}\nparsed caller: {caller}\nvoice/video classification: {classification}\ncallback invoked: True\nspeaker invoked: True\n")
        
        self.monitor_stats["announcements"] += 1
        self._handle_incoming(caller, source)

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
        import sys
        sys.coinit_flags = 2
        try:
            import comtypes
            comtypes.CoInitialize()
        except Exception as e:
            log.warning(f"Failed to CoInitialize in CallMonitor thread: {e}")
            
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
        Detect WhatsApp Desktop incoming calls via window title or UIA.
        Titles seen in the wild:
          'Incoming voice call - John Doe'
          'Incoming video call - John Doe'
          'John Doe - Incoming call'
          'WhatsApp - Incoming call from John Doe'
        """
        titles = self._get_titles("WhatsApp")
        for title in titles:
            classification = "voice"
            if "video" in title.lower():
                classification = "video"
            caller = self._parse_caller(title, [
                r'incoming (?:voice|video) call[\s\-–]+(.+)',
                r'^(.+?)[\s\-–]+incoming',
                r'from\s+(.+?)(?:\s+on\s+whatsapp)?$',
            ])
            if caller:
                print(f"\n[CALL]\ntimestamp: {time.time()}\nwindow title: {title}\nnotification title: N/A\nnotification body: N/A\nparsed caller: {caller}\nvoice/video classification: {classification}\ncallback invoked: True\nspeaker invoked: True\n")
                if hasattr(self, "monitor_stats"):
                    self.monitor_stats["last_call"] = time.time()
                    self.monitor_stats["last_caller"] = caller
                    if classification == "video":
                        self.monitor_stats["video_count"] += 1
                    else:
                        self.monitor_stats["voice_count"] += 1
                    self.monitor_stats["announcements"] += 1
                return caller, "WhatsApp"

            # Strict fallback — only trigger if it explicitly mentions an incoming call
            title_lower = title.lower()
            if "incoming call" in title_lower or "incoming voice call" in title_lower or "incoming video call" in title_lower:
                print(f"\n[CALL]\ntimestamp: {time.time()}\nwindow title: {title}\nnotification title: N/A\nnotification body: N/A\nparsed caller: someone\nvoice/video classification: {classification}\ncallback invoked: True\nspeaker invoked: True\n")
                if hasattr(self, "monitor_stats"):
                    self.monitor_stats["last_call"] = time.time()
                    self.monitor_stats["last_caller"] = "someone"
                    if classification == "video":
                        self.monitor_stats["video_count"] += 1
                    else:
                        self.monitor_stats["voice_count"] += 1
                    self.monitor_stats["announcements"] += 1
                return "someone", "WhatsApp"

        # Fallback: OCR-based detection for WhatsApp WebView2 calls
        # SAFETY: Only scans the WhatsApp window (not full screen) and
        # requires strict spatial + contextual validation to prevent
        # false positives from desktop text.
        try:
            import psutil
            import asyncio
            from winsdk.windows.media.ocr import OcrEngine
            from winsdk.windows.graphics.imaging import SoftwareBitmap, BitmapPixelFormat
            from winsdk.windows.security.cryptography import CryptographicBuffer

            # ── Gate 1: WhatsApp process must exist ────────────
            whatsapp_pids = set(
                p.pid for p in psutil.process_iter(['name'])
                if p.info['name'] and 'whatsapp' in p.info['name'].lower()
            )
            if not whatsapp_pids:
                return None

            # ── Gate 2: WhatsApp must be the foreground window ─
            fg_hwnd = win32gui.GetForegroundWindow()
            if not fg_hwnd:
                return None
            _, fg_pid = win32process.GetWindowThreadProcessId(fg_hwnd)
            if fg_pid not in whatsapp_pids:
                # WhatsApp is not in the foreground — skip OCR entirely
                return None

            # ── Gate 3: Capture only the WhatsApp window ───────
            rect = win32gui.GetWindowRect(fg_hwnd)
            wa_left, wa_top, wa_right, wa_bottom = rect
            wa_width = wa_right - wa_left
            wa_height = wa_bottom - wa_top
            if wa_width < 100 or wa_height < 100:
                return None  # Window too small / minimized

            # Try PrintWindow capture first (works even with WebView2)
            img = self._capture_window_crop(fg_hwnd, wa_width, wa_height)
            if img is None:
                # Fallback: crop screen grab to WhatsApp window bounds only
                from PIL import ImageGrab
                full = ImageGrab.grab().convert("RGBA")
                img = full.crop((wa_left, wa_top, wa_right, wa_bottom))

            # Convert to RGBA for OCR
            img = img.convert("RGBA")

            async def _ocr_whatsapp_window():
                try:
                    buf = img.tobytes()
                    crypto_buf = CryptographicBuffer.create_from_byte_array(buf)
                    bitmap = SoftwareBitmap.create_copy_from_buffer(
                        crypto_buf, BitmapPixelFormat.RGBA8, img.width, img.height
                    )
                    engine = OcrEngine.try_create_from_user_profile_languages()
                    if not engine:
                        return None
                    return await engine.recognize_async(bitmap)
                except Exception:
                    return None

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(_ocr_whatsapp_window())
            loop.close()

            if not result:
                return None

            # ── Collect OCR words with bounding boxes ──────────
            accept_word = None
            decline_word = None
            call_label_found = False
            call_label_text = ""
            caller = "someone"
            classification = "voice"

            _CALL_KEYWORDS = [
                "incoming voice call", "incoming video call",
                "voice call", "video call",
                "whatsapp audio", "whatsapp video",
            ]

            lines_text = []
            for line in result.lines:
                line_str = line.text.strip()
                if not line_str:
                    continue
                lines_text.append(line_str)
                line_lower = line_str.lower()

                # Find Accept / Decline words with positions
                for word in line.words:
                    wt = word.text.strip().lower()
                    if wt in ("accept", "answer") and accept_word is None:
                        accept_word = word
                    elif wt in ("decline", "reject") and decline_word is None:
                        decline_word = word

                # Find call-type label
                if not call_label_found:
                    for kw in _CALL_KEYWORDS:
                        if kw in line_lower:
                            call_label_found = True
                            call_label_text = line_str
                            classification = "video" if "video" in line_lower else "voice"
                            break

            # ── Spatial proximity check ────────────────────────
            # Accept and Decline buttons should be within ~300px
            # vertically of each other (same call UI region)
            buttons_proximate = False
            if accept_word and decline_word:
                ay = accept_word.bounding_rect.y
                dy = decline_word.bounding_rect.y
                ax = accept_word.bounding_rect.x
                dx = decline_word.bounding_rect.x
                vert_dist = abs(ay - dy)
                horiz_dist = abs(ax - dx)
                # Both buttons in the same vertical band (< 200px apart vertically)
                # and not too far horizontally (< 600px — they're typically side by side)
                buttons_proximate = vert_dist < 200 and horiz_dist < 600

            # ── Extract caller name ────────────────────────────
            # Caller is typically the line just above the call-type label
            if call_label_found and call_label_text:
                for i, lt in enumerate(lines_text):
                    if lt == call_label_text and i > 0:
                        potential = lines_text[i - 1]
                        if potential.lower() not in [
                            "whatsapp", "incoming", "accept", "decline",
                            "answer", "reject", "video call", "voice call",
                        ]:
                            caller = potential
                        break

            # ── Confidence scoring ─────────────────────────────
            score = 0
            checks = {
                "whatsapp_foreground": True,          # Already passed Gate 2
                "accept_button": accept_word is not None,
                "decline_button": decline_word is not None,
                "buttons_proximate": buttons_proximate,
                "call_label": call_label_found,
            }
            score = sum(1 for v in checks.values() if v)

            # ── Diagnostic output ──────────────────────────────
            diag = (
                f"\n[CALL VALIDATION]\n"
                f"whatsapp process found: True\n"
                f"whatsapp foreground: {checks['whatsapp_foreground']}\n"
                f"accept button found: {checks['accept_button']}\n"
                f"decline button found: {checks['decline_button']}\n"
                f"buttons proximate: {checks['buttons_proximate']}\n"
                f"call label found: {checks['call_label']} ({call_label_text})\n"
                f"caller found: {caller}\n"
                f"confidence score: {score}/5\n"
            )

            # ── Decision gate: require >= 4 out of 5 checks ───
            if score >= 4:
                print(diag + f"validation result: PASS\n")
                log.info(f"OCR call detection PASSED (score {score}/5, caller={caller})")

                if hasattr(self, "monitor_stats"):
                    self.monitor_stats["last_call"] = time.time()
                    self.monitor_stats["last_caller"] = caller
                    if classification == "video":
                        self.monitor_stats["video_count"] += 1
                    else:
                        self.monitor_stats["voice_count"] += 1
                    self.monitor_stats["announcements"] += 1

                return caller, "WhatsApp"
            else:
                # Suppress — not enough evidence
                log.debug(f"OCR call detection REJECTED (score {score}/5)")
                log.debug(diag.replace("\n", " | "))
                return None

        except Exception as e:
            log.warning(f"WhatsApp OCR check failed: {e}")

        return None

    def _find_whatsapp_webview_hwnd(self) -> int:
        """Find the WhatsApp WebView2 window handle dynamically."""
        hwnd = None
        def callback(h, extra):
            nonlocal hwnd
            classname = win32gui.GetClassName(h)
            title = win32gui.GetWindowText(h)
            if classname == "Chrome_WidgetWin_1" and title == "WhatsApp":
                hwnd = h
                return False
            return True
        try:
            win32gui.EnumWindows(callback, None)
        except Exception:
            pass
        return hwnd

    def _capture_window_crop(self, hwnd, w, h):
        """Capture the top-middle part of the window in the background."""
        try:
            hwndDC = win32gui.GetWindowDC(hwnd)
            mfcDC  = win32ui.CreateDCFromHandle(hwndDC)
            saveDC = mfcDC.CreateCompatibleDC()

            saveBitMap = win32ui.CreateBitmap()
            saveBitMap.CreateCompatibleBitmap(mfcDC, w, h)
            saveDC.SelectObject(saveBitMap)

            # Enable DPI awareness
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(2)
            except Exception:
                try:
                    ctypes.windll.user32.SetProcessDPIAware()
                except Exception:
                    pass

            result = ctypes.windll.user32.PrintWindow(hwnd, saveDC.GetSafeHdc(), 3)

            bmpinfo = saveBitMap.GetInfo()
            bmpstr = saveBitMap.GetBitmapBits(True)
            im = Image.frombuffer(
                'RGB',
                (bmpinfo['bmWidth'], bmpinfo['bmHeight']),
                bmpstr, 'raw', 'BGRX', 0, 1)

            saveDC.DeleteDC()
            mfcDC.DeleteDC()
            win32gui.ReleaseDC(hwnd, hwndDC)
            win32gui.DeleteObject(saveBitMap.GetHandle())

            if result == 1:
                crop_box = (int(w * 0.1), int(h * 0.1), int(w * 0.9), int(h * 0.55))
                return im.crop(crop_box)
        except Exception as e:
            log.warning(f"Failed to capture window in background: {e}")
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
        Check for call notifications in recent notification logs.
        Avoids slow PowerShell toast checking by reading from the watcher callback.
        """
        if not self._recent_notifs_fn:
            return None

        try:
            recent_logs = self._recent_notifs_fn()
            if not recent_logs:
                return None

            now = time.time()
            for entry in reversed(recent_logs):
                # Only check notifications within the last 5 seconds
                if now - entry.get("timestamp", 0) > 5.0:
                    break

                app_name = entry.get("app", "")
                title = entry.get("title", "")
                body = entry.get("body", "")

                # If app is WhatsApp, check for call markers and extract caller directly
                if "whatsapp" in app_name.lower():
                    t_clean = title.lower()
                    b_clean = body.lower()
                    if any(kw in t_clean for kw in ["incoming voice call", "incoming video call", "incoming call"]):
                        caller = body
                        if caller:
                            return caller, "WhatsApp"
                    elif any(kw in b_clean for kw in ["incoming voice call", "incoming video call", "incoming call"]):
                        caller = title
                        if caller:
                            return caller, "WhatsApp"

                # Strict fallback for non-WhatsApp apps or generic notifications
                content = f"{title} {body}".lower()
                call_markers = ["incoming voice call", "incoming video call", "incoming call"]
                if any(marker in content for marker in call_markers):
                    caller = self._parse_caller(f"{title} {body}", [
                        r'incoming (?:voice|video) call[\s\-–]+(.+)',
                        r'(.+?) is calling',
                        r'call from (.+)',
                    ]) or title or body
                    source = app_name or "notification"
                    return caller, source
        except Exception as e:
            log.warning(f"Error checking recent notifications callback: {e}")
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
            print("\n[TTS]\nannouncement started")
            self._speak(msg)
            # Give speaker a moment to finish
            time.sleep(1.0)
            self._speak("Would you like to lift or decline, sir?")
            if self._is_speaking_fn:
                time.sleep(1.5) # Give engine time to switch to True
                while self._is_speaking_fn():
                    time.sleep(0.2)
            print("speaker idle confirmed")
            print("announcement completed")

        # ── Optional callback ─────────────────────────────────
        if self._callback:
            self._callback(caller, source)

        # ── Listen for answer/decline command ─────────────────
        if self._listen:
            self._wait_for_command(caller, source)

    def _wait_for_command(self, caller: str, source: str):
        """Listen for up to ANSWER_WINDOW seconds for answer/decline."""
        import msvcrt
        print("voice capture started\n")
        deadline = time.time() + 15  # 15 seconds timeout
        
        print("\n[VOICE COMMAND]\nmicrophone selected: default\nambient calibration started: skipped\nambient calibration complete: skipped\nlisten started: True")
        
        while time.time() < deadline:
            # Keyboard fallback check
            if msvcrt.kbhit():
                key = msvcrt.getch().decode('utf-8', 'ignore').lower()
                if key == 'a':
                    print("recognized: lift (keyboard A)\ncall action: accept\n")
                    self._answer_call(source)
                    return
                elif key == 'd':
                    print("recognized: decline (keyboard D)\ncall action: decline\n")
                    self._decline_call(source)
                    return
            try:
                text = self._listen(timeout=3)
                if not text:
                    continue
                t = text.lower().strip()
                print(f"audio captured length: >0\nspeech recognized text: {t}\nconfidence: N/A\ntimeout reason: None")
                
                if any(w in t for w in ["answer", "pick up", "accept", "receive", "lift"]):
                    print("recognized: lift\ncall action: accept\n")
                    self._answer_call(source)
                    return
                if any(w in t for w in ["decline", "reject", "ignore", "dismiss",
                                         "no", "cut", "don't answer", "hang up"]):
                    print("recognized: decline\ncall action: decline\n")
                    self._decline_call(source)
                    return
            except Exception as e:
                if str(e) == "timeout":
                    continue
                break
        print("timeout reason: 15s deadline reached without valid command\n")

    # ══════════════════════════════════════════════════════════
    # ANSWER / DECLINE
    # ══════════════════════════════════════════════════════════

    def _answer_call(self, source: str):
        """Auto-answer the call using keyboard shortcut or OCR click."""
        log.info(f"📞 Answering {source} call...")
        if self._speak:
            self._speak("Answering the call, sir.")

        # Bring the app window to front then send shortcut/click
        app_proc = self._source_to_process(source)
        if app_proc:
            self._focus_window(app_proc)
            time.sleep(0.5)

        clicked = False
        result = "N/A"
        if source.lower() == "whatsapp":
            clicked, result = self._click_ocr_button("accept")
            if not clicked:
                # Some versions use "Answer" instead of "Accept"
                clicked, result = self._click_ocr_button("answer")
                
        if not clicked:
            keys = APP_KEYS.get(source, {}).get("answer", "%a")
            self._send_keys(app_proc, keys)
            result = f"Sent fallback shortcut: {keys}"
            
        print(f"\n[CALL ACTION]\ncommand received: lift\ntarget button found: {clicked}\nbutton coordinates: {result}\nclick executed: {clicked}\nsuccess/failure: {'success' if clicked else 'failure'}\n")

    def _decline_call(self, source: str):
        """Decline / dismiss the call using OCR click or shortcut."""
        log.info(f"📞 Declining {source} call...")
        if self._speak:
            self._speak("Declining the call, sir.")

        app_proc = self._source_to_process(source)
        if app_proc:
            self._focus_window(app_proc)
            time.sleep(0.5)

        clicked = False
        result = "N/A"
        if source.lower() == "whatsapp":
            clicked, result = self._click_ocr_button("decline")
            if not clicked:
                clicked, result = self._click_ocr_button("reject")

        if not clicked:
            keys = APP_KEYS.get(source, {}).get("decline", "{ESC}")
            self._send_keys(app_proc, keys)
            result = f"Sent fallback shortcut: {keys}"
            
        print(f"\n[CALL ACTION]\ncommand received: decline\ntarget button found: {clicked}\nbutton coordinates: {result}\nclick executed: {clicked}\nsuccess/failure: {'success' if clicked else 'failure'}\n")

    # ══════════════════════════════════════════════════════════
    # WINDOWS HELPERS
    # ══════════════════════════════════════════════════════════

    def _click_ocr_button(self, button_text: str):
        """Finds a button on screen by text using WinSDK OCR and clicks it."""
        try:
            import asyncio
            from winsdk.windows.media.ocr import OcrEngine
            from winsdk.windows.graphics.imaging import SoftwareBitmap, BitmapPixelFormat
            from winsdk.windows.security.cryptography import CryptographicBuffer
            from PIL import ImageGrab
            import pyautogui

            async def get_ocr_result():
                img = ImageGrab.grab().convert("RGBA")
                buf = img.tobytes()
                crypto_buf = CryptographicBuffer.create_from_byte_array(buf)
                bitmap = SoftwareBitmap.create_copy_from_buffer(
                    crypto_buf, BitmapPixelFormat.RGBA8, img.width, img.height
                )
                engine = OcrEngine.try_create_from_user_profile_languages()
                if not engine:
                    return None
                return await engine.recognize_async(bitmap)

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(get_ocr_result())
            loop.close()

            if result:
                for line in result.lines:
                    for word in line.words:
                        if button_text.lower() in word.text.lower():
                            rect = word.bounding_rect
                            center_x = rect.x + (rect.width / 2)
                            center_y = rect.y + (rect.height / 2)
                            pyautogui.click(center_x, center_y)
                            return True, f"Found '{word.text}' at ({center_x}, {center_y})"
            return False, "Text not found on screen via OCR"
        except Exception as e:
            return False, f"OCR Click Error: {e}"

    def _get_titles(self, process_name: str) -> list:
        """Get all window titles for a given process name using native Win32 APIs."""
        target_pids = set()
        proc_lower = process_name.lower()

        if proc_lower == "whatsapp":
            proc_names = ["whatsapp", "whatsapp.root"]
        elif proc_lower == "yourphone" or proc_lower == "phoneexperiencehost":
            proc_names = ["yourphone", "phoneexperiencehost", "phonelink"]
        elif proc_lower == "teams":
            proc_names = ["teams", "ms-teams"]
        else:
            proc_names = [proc_lower]

        for proc in psutil.process_iter(['pid', 'name']):
            try:
                name_lower = proc.info['name'].lower()
                if any(p in name_lower for p in proc_names):
                    target_pids.add(proc.info['pid'])
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

        if not target_pids:
            return []

        titles = []
        def enum_windows_callback(hwnd, extra):
            if win32gui.IsWindowVisible(hwnd):
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                if pid in target_pids:
                    title = win32gui.GetWindowText(hwnd)
                    if title:
                        titles.append(title)
            return True

        try:
            win32gui.EnumWindows(enum_windows_callback, None)
        except Exception as e:
            log.warning(f"Error enumerating windows for {process_name}: {e}")
        return titles

    def _focus_window(self, process_name: str):
        """Bring app window to foreground using native Win32 APIs."""
        proc_lower = process_name.lower()
        if proc_lower == "whatsapp":
            proc_names = ["whatsapp", "whatsapp.root"]
        elif proc_lower == "yourphone" or proc_lower == "phoneexperiencehost":
            proc_names = ["yourphone", "phoneexperiencehost", "phonelink"]
        elif proc_lower == "teams":
            proc_names = ["teams", "ms-teams"]
        else:
            proc_names = [proc_lower]

        target_pids = set()
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                name_lower = proc.info['name'].lower()
                if any(p in name_lower for p in proc_names):
                    target_pids.add(proc.info['pid'])
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

        if not target_pids:
            return

        def enum_windows_callback(hwnd, extra):
            if win32gui.IsWindowVisible(hwnd):
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                if pid in target_pids:
                    if win32gui.GetWindowText(hwnd):
                        try:
                            if win32gui.IsIconic(hwnd):
                                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                            else:
                                win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
                            win32gui.SetForegroundWindow(hwnd)
                            log.info(f"Focused window for process {process_name} (hwnd: {hwnd})")
                        except Exception:
                            try:
                                import pyautogui
                                pyautogui.press('alt')
                                win32gui.SetForegroundWindow(hwnd)
                            except Exception as ex:
                                log.debug(f"SetForegroundWindow failed for {process_name}: {ex}")
                        return False
            return True

        try:
            win32gui.EnumWindows(enum_windows_callback, None)
        except Exception:
            pass

    def _send_keys(self, process_name: str, keys: str):
        """Send keyboard shortcut using PyAutoGUI instead of slow PowerShell."""
        try:
            import pyautogui
            if keys == "%a":
                pyautogui.hotkey('alt', 'a')
            elif keys == "%d":
                pyautogui.hotkey('alt', 'd')
            elif keys == "{F10}":
                pyautogui.press('f10')
            elif keys == "{ESC}":
                pyautogui.press('esc')
            elif "+" in keys:
                # Support "ctrl+alt+shift+a"
                parts = keys.split('+')
                pyautogui.hotkey(*parts)
            else:
                if keys.startswith("%") and len(keys) == 2:
                    pyautogui.hotkey('alt', keys[1])
                elif keys.startswith("{") and keys.endswith("}"):
                    key_name = keys[1:-1].lower()
                    pyautogui.press(key_name)
                else:
                    pyautogui.write(keys)
            log.info(f"Natively sent keys '{keys}' to {process_name}")
        except Exception as e:
            log.warning(f"pyautogui SendKeys failed: {e}")

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
                if name.lower() in ('whatsapp', 'whatsapp desktop', 'skype', 'teams', 'microsoft teams'):
                    continue
                if name and len(name) > 1:
                    return name
        return None

    def get_call_monitor_status(self) -> str:
        """Returns verbose diagnostic string for whatsapp call monitor status."""
        if not hasattr(self, "monitor_stats"):
            return "Call monitor is initialized but has no stats yet."
        
        alive_str = "alive" if self.monitor_stats.get("alive", False) else "dead"
        last_c = self.monitor_stats.get("last_call")
        last_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(last_c)) if last_c else "None"
        
        s = f"Call Monitor is {alive_str}.\n"
        s += f"Last call detected: {last_time}\n"
        s += f"Last caller: {self.monitor_stats.get('last_caller', 'None')}\n"
        s += f"Voice calls detected count: {self.monitor_stats.get('voice_count', 0)}\n"
        s += f"Video calls detected count: {self.monitor_stats.get('video_count', 0)}\n"
        s += f"Announcements count: {self.monitor_stats.get('announcements', 0)}\n"
        return s

    def get_current_call_status(self) -> str:
        """Returns the current real-time call status for Telegram queries.

        Uses the same hardened OCR pipeline as _check_whatsapp():
        - WhatsApp must be the foreground window
        - Only scans the WhatsApp window (not full screen)
        - Requires spatial proximity of Accept/Decline buttons
        - Confidence score >= 4/5 to report call as active
        """
        _NO_CALL = "call active: False\ncaller: None\nclassification: None\naccept button visible: False"
        try:
            import asyncio
            from winsdk.windows.media.ocr import OcrEngine
            from winsdk.windows.graphics.imaging import SoftwareBitmap, BitmapPixelFormat
            from winsdk.windows.security.cryptography import CryptographicBuffer
            import psutil

            # Gate 1: WhatsApp process must exist
            whatsapp_pids = set(
                p.pid for p in psutil.process_iter(['name'])
                if p.info['name'] and 'whatsapp' in p.info['name'].lower()
            )
            if not whatsapp_pids:
                return _NO_CALL

            # Gate 2: WhatsApp must be the foreground window
            fg_hwnd = win32gui.GetForegroundWindow()
            if not fg_hwnd:
                return _NO_CALL
            _, fg_pid = win32process.GetWindowThreadProcessId(fg_hwnd)
            if fg_pid not in whatsapp_pids:
                return _NO_CALL

            # Gate 3: Capture only the WhatsApp window
            rect = win32gui.GetWindowRect(fg_hwnd)
            wa_left, wa_top, wa_right, wa_bottom = rect
            wa_width = wa_right - wa_left
            wa_height = wa_bottom - wa_top
            if wa_width < 100 or wa_height < 100:
                return _NO_CALL

            img = self._capture_window_crop(fg_hwnd, wa_width, wa_height)
            if img is None:
                from PIL import ImageGrab
                full = ImageGrab.grab().convert("RGBA")
                img = full.crop((wa_left, wa_top, wa_right, wa_bottom))

            img = img.convert("RGBA")

            async def _ocr_wa():
                try:
                    buf = img.tobytes()
                    crypto_buf = CryptographicBuffer.create_from_byte_array(buf)
                    bitmap = SoftwareBitmap.create_copy_from_buffer(
                        crypto_buf, BitmapPixelFormat.RGBA8, img.width, img.height
                    )
                    engine = OcrEngine.try_create_from_user_profile_languages()
                    if not engine:
                        return None
                    return await engine.recognize_async(bitmap)
                except Exception:
                    return None

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(_ocr_wa())
            loop.close()

            if not result:
                return _NO_CALL

            # Collect OCR words with positions
            accept_word = None
            decline_word = None
            call_label_found = False
            classification = "voice"
            caller = "Unknown"

            _CALL_KEYWORDS = [
                "incoming voice call", "incoming video call",
                "voice call", "video call",
                "whatsapp audio", "whatsapp video",
            ]

            lines_text = []
            for line in result.lines:
                line_str = line.text.strip()
                if not line_str:
                    continue
                lines_text.append(line_str)
                line_lower = line_str.lower()

                for word in line.words:
                    wt = word.text.strip().lower()
                    if wt in ("accept", "answer") and accept_word is None:
                        accept_word = word
                    elif wt in ("decline", "reject") and decline_word is None:
                        decline_word = word

                if not call_label_found:
                    for kw in _CALL_KEYWORDS:
                        if kw in line_lower:
                            call_label_found = True
                            classification = "video" if "video" in line_lower else "voice"
                            # Extract caller from preceding line
                            idx = len(lines_text) - 1
                            if idx > 0:
                                potential = lines_text[idx - 1]
                                if potential.lower() not in [
                                    "whatsapp", "incoming", "accept", "decline",
                                    "answer", "reject", "video call", "voice call",
                                ]:
                                    caller = potential
                            break

            # Spatial proximity
            buttons_proximate = False
            if accept_word and decline_word:
                vert_dist = abs(accept_word.bounding_rect.y - decline_word.bounding_rect.y)
                horiz_dist = abs(accept_word.bounding_rect.x - decline_word.bounding_rect.x)
                buttons_proximate = vert_dist < 200 and horiz_dist < 600

            # Confidence scoring
            checks = {
                "whatsapp_foreground": True,
                "accept_button": accept_word is not None,
                "decline_button": decline_word is not None,
                "buttons_proximate": buttons_proximate,
                "call_label": call_label_found,
            }
            score = sum(1 for v in checks.values() if v)

            if score >= 4:
                accept_visible = accept_word is not None
                return (
                    f"call active: True\n"
                    f"caller: {caller}\n"
                    f"classification: {classification}\n"
                    f"accept button visible: {accept_visible}\n"
                    f"confidence: {score}/5"
                )
            else:
                return _NO_CALL

        except Exception as e:
            return f"Error getting call status: {e}"

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
