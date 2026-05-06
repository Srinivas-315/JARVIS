"""
JARVIS — skills/notification_watcher.py
Always-On Windows Notification Watcher

Runs as a daemon thread that monitors ALL Windows toast notifications
in real-time and announces them via JARVIS voice.

Strategy 1 (primary):  wpndatabase.db SQLite polling every 10 seconds
Strategy 2 (fallback): winsdk UserNotificationListener — event-driven

Features:
  - App priority system (urgent/normal/silent)
  - Dedup — never announces same notification twice
  - Rate limiting — max 1 announcement per 8 seconds
  - Burst grouping — "5 new WhatsApp messages from Mom"
  - Do Not Disturb mode — "don't disturb me for 30 minutes"
  - Voice queries — "what notifications did I get?"
"""

import asyncio
import hashlib
import os
import re
import shutil
import sqlite3
import tempfile
import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from utils.logger import log

# ─── App Priority Configuration ────────────────────────────────
# Urgent: announce immediately (even if user is speaking)
# Normal: announce when JARVIS is idle
# Silent: log only, never speak
APP_PRIORITY = {
    "urgent": [
        "whatsapp",
        "phone link",
        "your phone",
        "microsoft teams",
        "teams",
        "slack",
        "skype",
        "zoom",
        "telegram",
    ],
    "normal": [
        "gmail",
        "mail",
        "outlook",
        "instagram",
        "youtube",
        "discord",
        "twitter",
        "x",
        "snapchat",
        "linkedin",
        "facebook",
        "messenger",
        "reddit",
    ],
    "silent": [
        "microsoft store",
        "windows security",
        "edge",
        "settings",
        "windows update",
        "cortana",
        "xbox",
        "onedrive",
        "widget",
    ],
}

# Flatten for quick lookup
_URGENT_APPS = {a.lower() for a in APP_PRIORITY["urgent"]}
_NORMAL_APPS = {a.lower() for a in APP_PRIORITY["normal"]}
_SILENT_APPS = {a.lower() for a in APP_PRIORITY["silent"]}

# ─── Rate Limiting ──────────────────────────────────────────────
_MIN_ANNOUNCE_GAP = 3       # seconds between spoken announcements (was 8 — too slow for chat apps)
_BURST_WINDOW = 4           # seconds to group burst notifications
_MAX_RECENT_HISTORY = 50    # max stored notifications for queries


class NotificationWatcher:
    """
    Always-on background notification monitor.
    Watches ALL Windows toast notifications and announces them via JARVIS voice.
    """

    def __init__(self, speak_fn=None, is_speaking_fn=None):
        """
        Args:
            speak_fn:       Callable(str) — JARVIS speak function
            is_speaking_fn: Callable() -> bool — returns True if JARVIS is currently speaking
        """
        self._speak = speak_fn or (lambda msg: print(f"🔔 {msg}"))
        self._is_speaking = is_speaking_fn or (lambda: False)

        # Thread control
        self._thread = None
        self._stop_event = threading.Event()
        self._active = False

        # Dedup: set of notification hashes we've already announced
        self._seen_hashes = set()
        self._seen_lock = threading.Lock()

        # Rate limiting
        self._last_announce_time = 0
        self._announce_lock = threading.Lock()

        # Burst grouping: app_name → list of (title, body, timestamp)
        self._burst_buffer = defaultdict(list)
        self._burst_lock = threading.Lock()
        self._burst_timer = None

        # Do Not Disturb
        self._dnd_until = None
        self._dnd_lock = threading.Lock()

        # Muted apps
        self._muted_apps = set()

        # Recent notifications log (for "what did I get?")
        self._recent = []
        self._recent_lock = threading.Lock()

        # Which strategy succeeded
        self._strategy = "none"

    # ═══════════════════════════════════════════════════════════
    # LIFECYCLE
    # ═══════════════════════════════════════════════════════════

    def start(self):
        """Launch the background notification watcher."""
        if self._thread and self._thread.is_alive():
            log.info("Notification watcher already running.")
            return

        self._stop_event.clear()
        self._active = True
        self._thread = threading.Thread(
            target=self._run_loop,
            name="NotifWatcher",
            daemon=True,
        )
        self._thread.start()
        log.info("🔔 Notification watcher started (background daemon)")

    def stop(self):
        """Gracefully shut down the watcher."""
        self._stop_event.set()
        self._active = False
        if self._burst_timer:
            self._burst_timer.cancel()
        log.info("🔔 Notification watcher stopped.")

    def is_active(self) -> bool:
        return self._active and self._thread and self._thread.is_alive()

    # ═══════════════════════════════════════════════════════════
    # DO NOT DISTURB
    # ═══════════════════════════════════════════════════════════

    def set_dnd(self, minutes: int = 30) -> str:
        """Enable Do Not Disturb for N minutes."""
        with self._dnd_lock:
            self._dnd_until = datetime.now() + timedelta(minutes=minutes)
        log.info(f"🔕 DND enabled for {minutes} minutes")
        return f"Do not disturb mode on for {minutes} minutes, sir. I'll stay quiet."

    def resume(self) -> str:
        """Disable Do Not Disturb."""
        with self._dnd_lock:
            self._dnd_until = None
        log.info("🔔 DND disabled — notifications resumed")
        return "Notifications resumed, sir. I'll keep you updated."

    def _is_dnd(self) -> bool:
        with self._dnd_lock:
            if self._dnd_until is None:
                return False
            if datetime.now() >= self._dnd_until:
                self._dnd_until = None
                return False
            return True

    # ═══════════════════════════════════════════════════════════
    # APP MUTING
    # ═══════════════════════════════════════════════════════════

    def mute_app(self, app_name: str) -> str:
        """Mute notifications from a specific app."""
        self._muted_apps.add(app_name.lower().strip())
        return f"{app_name} notifications muted, sir."

    def unmute_app(self, app_name: str) -> str:
        """Unmute a previously muted app."""
        self._muted_apps.discard(app_name.lower().strip())
        return f"{app_name} notifications unmuted, sir."

    # ═══════════════════════════════════════════════════════════
    # RECENT NOTIFICATIONS QUERY
    # ═══════════════════════════════════════════════════════════

    def get_recent(self, count: int = 5) -> str:
        """Return a spoken summary of recent notifications."""
        with self._recent_lock:
            if not self._recent:
                return "No notifications since I started watching, sir."

            items = self._recent[-count:]

        parts = []
        for n in reversed(items):
            app = n.get("app", "Unknown")
            title = n.get("title", "")
            body = n.get("body", "")
            time_str = n.get("time", "")

            if title and body:
                parts.append(f"{app}: {title} — {body}")
            elif title:
                parts.append(f"{app}: {title}")
            elif body:
                parts.append(f"{app}: {body}")
            else:
                parts.append(f"Notification from {app}")

        if len(parts) == 1:
            return f"You got 1 notification. {parts[0]}."

        summary = f"You got {len(parts)} recent notifications. "
        summary += ". ".join(parts) + "."
        return summary

    # ═══════════════════════════════════════════════════════════
    # MAIN LOOP — tries winsdk, falls back to DB polling
    # ═══════════════════════════════════════════════════════════

    def _run_loop(self):
        """Main background loop. Tries DB polling first (reliable), then winsdk."""
        db_path = os.path.expandvars(
            r"%LOCALAPPDATA%\Microsoft\Windows\Notifications\wpndatabase.db"
        )

        # Strategy 1 (primary): wpndatabase.db polling — works on all Windows
        if os.path.exists(db_path):
            self._strategy = "db_poll"
            log.info("🔔 Using wpndatabase.db polling (10s interval)")
            self._poll_wpn_database()
            return

        # Strategy 2 (fallback): winsdk event-driven — requires packaged app
        if self._try_winsdk():
            self._strategy = "winsdk"
            log.info("🔔 Using winsdk UserNotificationListener (event-driven)")
            return

        log.warning("🔔 No notification strategy available!")
        self._strategy = "none"

    # ═══════════════════════════════════════════════════════════
    # STRATEGY 1: winsdk UserNotificationListener
    # ═══════════════════════════════════════════════════════════

    def _try_winsdk(self) -> bool:
        """Attempt to set up winsdk event-driven notification listening."""
        try:
            import winsdk.windows.ui.notifications.management as mgmt
            import winsdk.windows.ui.notifications as notifs
        except ImportError:
            log.warning("winsdk not installed — skipping Strategy 1")
            return False

        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            success = loop.run_until_complete(self._winsdk_setup(mgmt, notifs))
            if not success:
                loop.close()
                return False

            # Run event loop until stopped
            try:
                loop.run_until_complete(self._winsdk_event_loop())
            except Exception as e:
                log.warning(f"winsdk event loop ended: {e}")
            finally:
                loop.close()
            return True

        except Exception as e:
            log.warning(f"winsdk setup failed: {e}")
            return False

    async def _winsdk_setup(self, mgmt, notifs):
        """Request notification access and register event handler."""
        try:
            # Try get_current() first (newer winsdk), then _from(User) fallback
            listener = None
            try:
                listener = mgmt.UserNotificationListener.get_current()
            except AttributeError:
                pass
            except Exception:
                pass

            if listener is None:
                try:
                    from winsdk.windows.system import User
                    users = await User.find_all_async()
                    if users.size > 0:
                        listener = mgmt.UserNotificationListener._from(users.get_at(0))
                except Exception as e:
                    log.debug(f"winsdk _from(User) failed: {e}")

            if listener is None:
                log.warning("Could not obtain UserNotificationListener instance")
                return False

            self._winsdk_listener = listener

            access = await self._winsdk_listener.request_access_async()
            # 0 = Unspecified, 1 = Allowed, 2 = Denied
            if access.value != 1:
                log.warning(f"winsdk access denied (status={access.value})")
                return False

            log.info("🔔 winsdk notification access GRANTED ✅")

            # Store reference to notifs module for content extraction
            self._winsdk_notifs = notifs

            # Get initial notification IDs so we don't announce old ones
            try:
                existing = await self._winsdk_listener.get_notifications_async(
                    notifs.NotificationKinds.TOAST
                )
                for n in existing:
                    h = self._hash_notification(
                        str(n.id), "", str(n.creation_time)
                    )
                    self._seen_hashes.add(h)
                log.info(f"🔔 Marked {len(self._seen_hashes)} existing notifications as seen")
            except Exception as e:
                log.warning(f"Could not pre-scan notifications: {e}")

            # Register event handler
            self._winsdk_listener.add_notification_changed(
                self._on_winsdk_notification_changed
            )

            return True
        except Exception as e:
            log.warning(f"winsdk setup error: {e}")
            return False

    def _on_winsdk_notification_changed(self, sender, args):
        """Called by winsdk when any notification changes (added/removed)."""
        try:
            # We only care about new notifications
            # Fetch the notification by ID
            notif = self._winsdk_listener.get_notification(
                args.user_notification_id
            )
            if not notif:
                return

            # Extract app name
            try:
                app_name = notif.app_info.display_info.display_name
            except Exception:
                app_name = "Unknown"

            # Extract text content
            title, body = "", ""
            try:
                visual = notif.notification.visual
                if visual:
                    # Try to get the toast generic binding
                    from winsdk.windows.ui.notifications import (
                        KnownNotificationBindings,
                    )
                    binding = visual.get_binding(
                        KnownNotificationBindings.get_toast_generic()
                    )
                    if binding:
                        text_elems = binding.get_text_elements()
                        texts = []
                        for i in range(text_elems.size):
                            t = text_elems.get_at(i).text
                            if t:
                                texts.append(t)
                        if len(texts) >= 1:
                            title = texts[0]
                        if len(texts) >= 2:
                            body = texts[1]
            except Exception as e:
                log.debug(f"Could not extract notification text: {e}")

            self._process_notification(app_name, title, body)

        except Exception as e:
            log.debug(f"winsdk notification handler error: {e}")

    async def _winsdk_event_loop(self):
        """Keep the async loop alive while waiting for events."""
        while not self._stop_event.is_set():
            await asyncio.sleep(1)

    # ═══════════════════════════════════════════════════════════
    # STRATEGY 2: wpndatabase.db polling
    # ═══════════════════════════════════════════════════════════

    def _poll_wpn_database(self):
        """Poll the Windows Notification Database every 3 seconds.

        Uses snapshot-diff approach: on each poll, reads ALL rows and compares
        against a saved snapshot.  Detects:
          • New rows   (ROWID not in snapshot)
          • Updated rows (ArrivalTime or payload hash changed)

        This is critical because apps like WhatsApp UPDATE existing rows
        instead of inserting new ones, so the old `ROWID > max` approach
        missed them entirely.
        """
        db_path = os.path.expandvars(
            r"%LOCALAPPDATA%\Microsoft\Windows\Notifications\wpndatabase.db"
        )

        if not os.path.exists(db_path):
            log.warning(f"wpndatabase.db not found at {db_path}")
            return

        # ── Pre-load existing notifications into _recent ──────
        # So "what notifications did I get" works immediately
        try:
            existing = self._read_recent_notifications(db_path, limit=10)
            for notif in existing:
                app = notif.get("app", "Unknown")
                title = notif.get("title", "")
                body = notif.get("body", "")
                if title or body:  # Skip empty notifications
                    entry = {
                        "app": app,
                        "title": title,
                        "body": body,
                        "time": datetime.now().strftime("%H:%M"),
                        "timestamp": time.time(),
                    }
                    with self._recent_lock:
                        self._recent.append(entry)
            if existing:
                log.info(f"🔔 Pre-loaded {len(existing)} existing notifications into history")
        except Exception as e:
            log.debug(f"Pre-load failed: {e}")

        # ── Build initial snapshot of ALL rows ─────────────────
        # snapshot = {rowid: (arrival_time, payload_hash)}
        snapshot = self._snapshot_all_notifications(db_path)
        log.info(f"🔔 DB polling started — snapshot has {len(snapshot)} rows")

        _consecutive_failures = 0

        while not self._stop_event.is_set():
            try:
                current = self._snapshot_all_notifications(db_path)
                if current is None:
                    # DB copy failed
                    _consecutive_failures += 1
                    if _consecutive_failures % 10 == 1:  # Log every ~30s
                        log.warning("🔔 DB copy failing — notifications may be missed")
                else:
                    _consecutive_failures = 0

                    # ── Detect NEW and UPDATED rows ───────────────
                    changed = []
                    for rowid, (arrival, p_hash, handler_id, payload) in current.items():
                        prev = snapshot.get(rowid)
                        if prev is None:
                            # Brand-new row
                            changed.append((rowid, handler_id, payload, "new"))
                        elif prev[0] != arrival or prev[1] != p_hash:
                            # Existing row was updated (new message in same slot)
                            changed.append((rowid, handler_id, payload, "updated"))

                    # ── Process detected changes ──────────────────
                    for rowid, handler_id, payload, change_type in changed:
                        app_name = self._resolve_handler_name(db_path, handler_id)
                        title, body = self._parse_toast_xml(payload)

                        log.info(
                            f"🔔 {change_type.upper()} notification [{rowid}] "
                            f"from {app_name}: {title[:40] if title else '(empty)'}"
                        )

                        # Use a unique dedup key combining rowid + arrival
                        # so updated rows get re-announced
                        arr = current[rowid][0]
                        dedup_id = f"row_{rowid}_arr_{arr}"
                        self._process_notification(
                            app_name, title, body, row_id=0,
                            _override_hash=dedup_id
                        )

                    if changed:
                        log.debug(f"🔔 Processed {len(changed)} notification changes")

                    # Update snapshot to current state
                    snapshot = current

            except Exception as e:
                log.warning(f"DB poll error: {e}")

            # Sleep in small increments so stop_event is responsive
            # 6 × 0.5 = 3 seconds between polls (was 5s — too slow)
            for _ in range(6):
                if self._stop_event.is_set():
                    return
                time.sleep(0.5)

    def _snapshot_all_notifications(self, db_path: str) -> dict:
        """Read ALL notification rows and return a snapshot dict.

        Returns:
            {rowid: (arrival_time, payload_hash, handler_id, payload_bytes)}
            or None if DB copy failed.
        """
        tmp = self._copy_db(db_path)
        if not tmp:
            return None

        snapshot = {}
        try:
            conn = sqlite3.connect(tmp)
            c = conn.cursor()
            c.execute(
                "SELECT ROWID, HandlerId, Payload, ArrivalTime "
                "FROM Notification"
            )
            for row in c.fetchall():
                rowid, handler_id, payload, arrival = row
                # Hash the payload for change detection
                if payload:
                    if isinstance(payload, bytes):
                        p_hash = hashlib.md5(payload).hexdigest()
                    else:
                        p_hash = hashlib.md5(str(payload).encode()).hexdigest()
                else:
                    p_hash = "empty"
                snapshot[rowid] = (arrival, p_hash, handler_id, payload)
            conn.close()
        except Exception as e:
            log.warning(f"Snapshot read error: {e}")
            return None
        finally:
            self._cleanup_tmp(tmp)

        return snapshot

    def _resolve_handler_name(self, db_path: str, handler_id: int) -> str:
        """Look up the human-readable app name for a handler ID.

        Uses a cache to avoid re-reading the DB on every notification.
        """
        # Check cache first
        if not hasattr(self, '_handler_cache'):
            self._handler_cache = {}
            self._handler_cache_time = 0

        now = time.time()
        # Refresh cache every 60 seconds
        if now - self._handler_cache_time > 60 or handler_id not in self._handler_cache:
            tmp = self._copy_db(db_path)
            if tmp:
                try:
                    conn = sqlite3.connect(tmp)
                    c = conn.cursor()
                    c.execute("SELECT RecordId, PrimaryId FROM NotificationHandler")
                    self._handler_cache = {r[0]: r[1] for r in c.fetchall()}
                    self._handler_cache_time = now
                    conn.close()
                except Exception:
                    pass
                finally:
                    self._cleanup_tmp(tmp)

        raw_name = self._handler_cache.get(handler_id, "Unknown")
        return self._clean_app_name(raw_name)

    def _get_max_notification_id(self, db_path: str) -> int:
        """Get the highest notification row ID from the DB."""
        try:
            tmp = self._copy_db(db_path)
            if not tmp:
                return 0
            conn = sqlite3.connect(tmp)
            c = conn.cursor()
            c.execute("SELECT MAX(ROWID) FROM Notification")
            row = c.fetchone()
            conn.close()
            self._cleanup_tmp(tmp)
            return row[0] or 0
        except Exception:
            return 0

    def _read_recent_notifications(self, db_path: str, limit: int = 10) -> list:
        """Read the most recent N notifications from DB (for startup pre-load)."""
        results = []
        tmp = self._copy_db(db_path)
        if not tmp:
            return results

        try:
            conn = sqlite3.connect(tmp)
            c = conn.cursor()

            # Get handler names for app identification
            c.execute("SELECT RecordId, PrimaryId FROM NotificationHandler")
            handlers = {row[0]: row[1] for row in c.fetchall()}

            # Get most recent notifications (ordered newest first)
            c.execute(
                "SELECT ROWID, HandlerId, Payload, ArrivalTime FROM Notification "
                "ORDER BY ROWID DESC LIMIT ?",
                (limit,),
            )

            for row in c.fetchall():
                rowid, handler_id, payload, arrival = row
                app_name = handlers.get(handler_id, "Unknown")
                app_name = self._clean_app_name(app_name)
                title, body = self._parse_toast_xml(payload)

                # Skip empty notifications
                if not title and not body:
                    continue

                results.append({
                    "id": rowid,
                    "app": app_name,
                    "title": title,
                    "body": body,
                    "time": str(arrival) if arrival else "",
                })

            conn.close()
        except Exception as e:
            log.debug(f"Recent DB read error: {e}")
        finally:
            self._cleanup_tmp(tmp)

        # Reverse so oldest is first (natural order)
        results.reverse()
        return results

    def _copy_db(self, db_path: str) -> str:
        """Copy the locked DB to a temp file for safe reading.

        Uses a unique temp filename and retries once on failure
        (the Windows Notification service can hold brief locks).
        """
        import uuid
        tmp = os.path.join(
            tempfile.gettempdir(),
            f"jarvis_wpn_{uuid.uuid4().hex[:8]}.db"
        )
        for attempt in range(2):
            try:
                shutil.copy2(db_path, tmp)
                return tmp
            except PermissionError:
                if attempt == 0:
                    time.sleep(0.3)  # Brief wait, then retry
                else:
                    log.debug("wpndatabase.db locked — skipping this poll cycle")
            except Exception as e:
                log.debug(f"DB copy error: {e}")
                break
        return ""

    def _cleanup_tmp(self, tmp_path: str):
        """Remove temp DB copy."""
        try:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass

    def _clean_app_name(self, primary_id: str) -> str:
        """Extract human-readable app name from handler PrimaryId.

        Real examples from this machine:
          '5319275A.WhatsAppDesktop_cv1g1gvanyjgm!App' → 'WhatsApp'
          'Microsoft.Todos_8wekyb3d8bbwe!App'          → 'Todos'
          'MicrosoftWindows.Client.WebExperience_cw5n1h2txyewy!Widgets' → 'Widgets'
          'AdobeNotificationClient_enpm4xejd91yc!CreativeCloud' → 'Adobe CreativeCloud'
          '7EE7776C.LinkedInforWindows_w1wdnht996qgy!App' → 'LinkedIn'
        """
        if not primary_id:
            return "Unknown"

        name = primary_id

        # Known mappings for common apps (exact prefix match)
        _KNOWN = {
            "5319275A.WhatsApp": "WhatsApp",
            "Microsoft.Todos": "Microsoft Todos",
            "Microsoft.WindowsTerminal": "Terminal",
            "Microsoft.Windows.Photos": "Photos",
            "Microsoft.MicrosoftEdge": "Edge",
            "Microsoft.OutlookForWindows": "Outlook",
            "Microsoft.Office.OneNote": "OneNote",
            "Microsoft.ScreenSketch": "Snipping Tool",
            "Microsoft.WindowsAlarms": "Alarms",
            "Microsoft.People": "People",
            "Microsoft.BingWeather": "Weather",
            "Microsoft.BingNews": "News",
            "SpotifyAB.SpotifyMusic": "Spotify",
            "FACEBOOK.FACEBOOK": "Facebook",
            "Facebook.InstagramBeta": "Instagram",
            "TelegramMessengerLLC": "Telegram",
            "DiscordInc.Discord": "Discord",
        }
        for prefix, friendly in _KNOWN.items():
            if prefix.lower() in name.lower():
                return friendly

        # Extract app name after '!' if present (e.g. '...!CreativeCloud' → 'CreativeCloud')
        bang_part = ""
        if "!" in name:
            bang_part = name.split("!")[-1]
            name = name.split("!")[0]

        # Remove package hash suffixes like '_cv1g1gvanyjgm'
        name = re.sub(r"_[a-z0-9]{8,}$", "", name, flags=re.IGNORECASE)
        # Remove leading hex IDs like '5319275A.'
        name = re.sub(r"^[0-9A-Fa-f]{6,}\.", "", name)
        # Remove 'MicrosoftWindows.Client.' prefix
        name = re.sub(r"^MicrosoftWindows\.Client\.", "", name)
        # Remove 'Microsoft.' prefix
        name = re.sub(r"^Microsoft\.", "", name)
        # Remove 'AcerIncorporated.' prefix
        name = re.sub(r"^AcerIncorporated\.", "Acer ", name)
        # Remove 'com.xxx.xxx.' prefixes
        name = re.sub(r"^com\.\w+\.\w+\.", "", name)
        name = re.sub(r"^com\.\w+\.", "", name)

        # Take the last meaningful segment if dots remain
        if "." in name:
            parts = [p for p in name.split(".") if p]
            name = parts[-1] if parts else name

        # Clean noise words
        name = name.replace("Desktop", "").replace("forWindows", "").strip()

        # If bang_part is more descriptive than 'App', use it
        if bang_part and bang_part not in ("App", "app"):
            if name:
                name = f"{name} {bang_part}"
            else:
                name = bang_part

        return name.strip() if name.strip() else "Unknown"

    def _parse_toast_xml(self, payload) -> tuple:
        """Extract title and body text from a toast notification XML payload."""
        title, body = "", ""
        if not payload:
            return title, body

        try:
            # Payload can be bytes or string
            if isinstance(payload, bytes):
                try:
                    text = payload.decode("utf-8", errors="ignore")
                except Exception:
                    text = str(payload)
            else:
                text = str(payload)

            # Extract <text> elements from the XML
            texts = re.findall(r"<text[^>]*>(.*?)</text>", text, re.DOTALL)

            if len(texts) >= 1:
                title = self._clean_xml_text(texts[0])
            if len(texts) >= 2:
                body = self._clean_xml_text(texts[1])

        except Exception:
            pass

        return title, body

    def _clean_xml_text(self, text: str) -> str:
        """Strip XML entities and clean text."""
        text = re.sub(r"&amp;", "&", text)
        text = re.sub(r"&lt;", "<", text)
        text = re.sub(r"&gt;", ">", text)
        text = re.sub(r"&quot;", '"', text)
        text = re.sub(r"&#\d+;", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    # ═══════════════════════════════════════════════════════════
    # NOTIFICATION PROCESSING PIPELINE
    # ═══════════════════════════════════════════════════════════

    def _process_notification(self, app_name: str, title: str, body: str,
                              row_id: int = 0, _override_hash: str = ""):
        """
        Central pipeline for all notifications (from any strategy).
        Handles: dedup → priority check → DND → rate limit → announce.

        Args:
            _override_hash: If provided, use this as the dedup key instead of
                            computing one from row_id or content.  The snapshot-
                            diff poller passes ``row_{id}_arr_{arrival}`` so that
                            updated rows (same ROWID, new ArrivalTime) are
                            treated as fresh notifications.
        """
        app_lower = app_name.lower().strip()
        now = time.time()

        # ── 1. Dedup: skip if we've seen this exact notification ──
        if _override_hash:
            n_hash = _override_hash
        elif row_id:
            n_hash = f"row_{row_id}"
        else:
            n_hash = self._hash_notification(app_name, title, body)

        with self._seen_lock:
            if n_hash in self._seen_hashes:
                return
            self._seen_hashes.add(n_hash)

            # Prune old hashes to prevent memory growth
            if len(self._seen_hashes) > 500:
                self._seen_hashes = set(list(self._seen_hashes)[-250:])

        # ── 2. Store in recent log ────────────────────────────────
        entry = {
            "app": app_name,
            "title": title,
            "body": body,
            "time": datetime.now().strftime("%H:%M"),
            "timestamp": now,
        }
        with self._recent_lock:
            self._recent.append(entry)
            if len(self._recent) > _MAX_RECENT_HISTORY:
                self._recent = self._recent[-_MAX_RECENT_HISTORY:]

        # ── 3. Check if muted ─────────────────────────────────────
        if app_lower in self._muted_apps:
            log.debug(f"🔇 Muted notification from {app_name}")
            return

        # ── 4. Determine priority ─────────────────────────────────
        priority = self._get_priority(app_lower)

        if priority == "silent":
            log.debug(f"🔇 Silent notification from {app_name}: {title}")
            return

        # ── 5. Check DND ──────────────────────────────────────────
        if self._is_dnd():
            log.debug(f"🔕 DND active — skipping {app_name}: {title}")
            return

        # ── 6. Burst grouping for non-urgent ──────────────────────
        if priority == "normal":
            self._add_to_burst(app_name, title, body, now)
            return

        # ── 7. Urgent: announce immediately (with rate limit) ─────
        self._announce_notification(app_name, title, body, urgent=True)

    def _get_priority(self, app_lower: str) -> str:
        """Determine notification priority from app name."""
        # Check each priority level
        for app in _URGENT_APPS:
            if app in app_lower or app_lower in app:
                return "urgent"
        for app in _NORMAL_APPS:
            if app in app_lower or app_lower in app:
                return "normal"
        for app in _SILENT_APPS:
            if app in app_lower or app_lower in app:
                return "silent"

        # Default: normal
        return "normal"

    def _hash_notification(self, app: str, title: str, body: str) -> str:
        """Create a dedup hash for a notification."""
        raw = f"{app}|{title}|{body}".lower().strip()
        return hashlib.md5(raw.encode()).hexdigest()

    # ═══════════════════════════════════════════════════════════
    # BURST GROUPING
    # ═══════════════════════════════════════════════════════════

    def _add_to_burst(self, app: str, title: str, body: str, timestamp: float):
        """Buffer a notification for burst grouping."""
        with self._burst_lock:
            self._burst_buffer[app].append({
                "title": title,
                "body": body,
                "time": timestamp,
            })

        # Schedule flush after burst window
        if self._burst_timer:
            self._burst_timer.cancel()
        self._burst_timer = threading.Timer(
            _BURST_WINDOW, self._flush_bursts
        )
        self._burst_timer.daemon = True
        self._burst_timer.start()

    def _flush_bursts(self):
        """Flush the burst buffer — group notifications per app."""
        with self._burst_lock:
            buffer_copy = dict(self._burst_buffer)
            self._burst_buffer.clear()

        for app, notifs in buffer_copy.items():
            if not notifs:
                continue

            if len(notifs) == 1:
                # Single notification — announce normally
                n = notifs[0]
                self._announce_notification(app, n["title"], n["body"])
            else:
                # Multiple notifications from same app — group them
                titles = [n["title"] for n in notifs if n["title"]]
                unique_titles = list(dict.fromkeys(titles))  # Preserve order, remove dupes

                if len(unique_titles) <= 2:
                    msg = f"{len(notifs)} notifications from {app}. {'. '.join(unique_titles)}."
                else:
                    msg = f"{len(notifs)} notifications from {app}. Latest: {unique_titles[-1]}."

                self._announce_notification(app, msg, "", grouped=True)

    # ═══════════════════════════════════════════════════════════
    # ANNOUNCEMENT ENGINE
    # ═══════════════════════════════════════════════════════════

    def _announce_notification(
        self, app: str, title: str, body: str,
        urgent: bool = False, grouped: bool = False
    ):
        """Build and speak the notification announcement.

        Idle-aware: For non-urgent notifications, waits up to 15s for
        JARVIS to finish speaking before announcing.
        """
        now = time.time()

        # Rate limiting (skip for urgent)
        with self._announce_lock:
            if not urgent and (now - self._last_announce_time) < _MIN_ANNOUNCE_GAP:
                log.debug(f"Rate-limited: {app}: {title}")
                return
            self._last_announce_time = now

        # Build spoken message
        if grouped:
            message = f"Sir, {title}"
        elif title and body:
            message = f"Sir, {app} notification. {title}: {body}"
        elif title:
            message = f"Sir, notification from {app}: {title}"
        elif body:
            message = f"Sir, notification from {app}: {body}"
        else:
            message = f"Sir, new notification from {app}."

        # Truncate very long messages
        if len(message) > 200:
            message = message[:197] + "..."

        log.info(f"🔔 Announcing: {message}")

        # Idle-aware announcement:
        #   Urgent  → speak immediately (even over user)
        #   Normal  → wait up to 15s for JARVIS to stop speaking
        if not urgent:
            waited = 0
            while self._is_speaking() and waited < 15:
                time.sleep(0.5)
                waited += 0.5
                if self._stop_event.is_set():
                    return
            if self._is_speaking():
                log.debug(f"Still speaking after 15s wait — skipping: {app}")
                return

        try:
            self._speak(message)
        except Exception as e:
            log.warning(f"Could not announce notification: {e}")

    # ═══════════════════════════════════════════════════════════
    # STATUS
    # ═══════════════════════════════════════════════════════════

    def status(self) -> str:
        """Return watcher status for diagnostics."""
        state = "active" if self.is_active() else "stopped"
        strategy = self._strategy
        dnd = "ON" if self._is_dnd() else "OFF"
        muted = ", ".join(self._muted_apps) if self._muted_apps else "none"
        count = len(self._recent)
        return (
            f"Notification watcher: {state} (strategy: {strategy}). "
            f"DND: {dnd}. Muted: {muted}. "
            f"Notifications seen: {count}."
        )


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    def test_speak(msg):
        print(f"🤖 JARVIS: {msg}")

    watcher = NotificationWatcher(speak_fn=test_speak)
    print("Starting notification watcher...")
    print("(Press Ctrl+C to stop)\n")
    watcher.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        watcher.stop()
        print("\nStopped.")
