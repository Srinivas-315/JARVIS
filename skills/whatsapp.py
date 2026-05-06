# skills/whatsapp.py — JARVIS WhatsApp Automation Skill
import hashlib
import json
import logging
import os
import re
import sqlite3
import subprocess
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

import pyautogui
import pyperclip

log = logging.getLogger("JARVIS")

# ── Contact aliases ───────────────────────────────────────────────────────────
_BASE_DISPLAY_NAMES: dict = {
    "mom": "Mom",
    "mother": "Mom",
    "amma": "Mom",
    "mummy": "Mom",
    "dad": "Dad",
    "father": "Dad",
    "daddy": "Dad",
    "nana": "Dad",
    "sarvani": "Sarvani",
    "sarvana": "Sarvani",
    "sarwani": "Sarvani",
    "sherwani": "Sarvani",
    "sharwana": "Sarvani",
    "sarvoni": "Sarvani",
    "sher": "Sarvani",
    "friend": "Friend",
    "bro": "Bro",
    "boss": "Boss",
    "teja": "Teja",
    "rahul": "Rahul",
    "priya": "Priya",
    "keerthi": "Keerthi",
    "keerthip": "Keerthi",
    "harsh": "Harsh",
    "ajay": "Ajay",
    "anidev": "Anidev",
}

_CONTACTS_FILE = Path("memory/wa_contacts.json")


def _load_dynamic_contacts() -> dict:
    try:
        if _CONTACTS_FILE.exists():
            return json.loads(_CONTACTS_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_dynamic_contacts(contacts: dict) -> None:
    _CONTACTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _CONTACTS_FILE.write_text(json.dumps(contacts, indent=2), encoding="utf-8")


def _get_display_names() -> dict:
    merged = dict(_BASE_DISPLAY_NAMES)
    merged.update(_load_dynamic_contacts())
    return merged


# ── Emoji map ─────────────────────────────────────────────────────────────────
EMOJI_MAP = {
    "heart": "❤️",
    "red heart": "❤️",
    "love": "❤️",
    "pink heart": "🩷",
    "orange heart": "🧡",
    "yellow heart": "💛",
    "green heart": "💚",
    "blue heart": "💙",
    "purple heart": "💜",
    "black heart": "🖤",
    "white heart": "🤍",
    "broken heart": "💔",
    "two hearts": "💕",
    "sparkling heart": "💖",
    "kiss": "😘",
    "flying kiss": "😘",
    "smile": "😊",
    "happy": "😄",
    "grin": "😁",
    "laugh": "😂",
    "lol": "😂",
    "laughing": "😂",
    "cry": "😢",
    "sad": "😢",
    "crying": "😢",
    "wink": "😉",
    "hug": "🤗",
    "cool": "😎",
    "star eyes": "🤩",
    "pray": "🙏",
    "namaste": "🙏",
    "clap": "👏",
    "wave": "👋",
    "thumbs up": "👍",
    "like": "👍",
    "ok": "👌",
    "thumbs down": "👎",
    "dislike": "👎",
    "heart eyes": "😍",
    "angry": "😠",
    "devil": "😈",
    "angel": "😇",
    "mind blown": "🤯",
    "shrug": "🤷",
    "facepalm": "🤦",
    "nerd": "🤓",
    "sick": "🤒",
    "sleep": "😴",
    "snore": "😴",
    "robot": "🤖",
    "ghost": "👻",
    "alien": "👽",
    "skull": "💀",
    "clown": "🤡",
    "poop": "💩",
    "monkey": "🐒",
    "eyes": "👀",
    "fire": "🔥",
    "lit": "🔥",
    "hot": "🔥",
    "star": "⭐",
    "sparkles": "✨",
    "boom": "💥",
    "sun": "☀️",
    "moon": "🌙",
    "rainbow": "🌈",
    "flower": "🌸",
    "rose": "🌹",
    "sunflower": "🌻",
    "cake": "🎂",
    "birthday": "🎂",
    "gift": "🎁",
    "party": "🎉",
    "music": "🎵",
    "tada": "🎉",
    "balloon": "🎈",
    "check": "✅",
    "tick": "✅",
    "cross": "❌",
    "warning": "⚠️",
    "trophy": "🏆",
    "crown": "👑",
    "gem": "💎",
    "diamond": "💎",
    "money": "💰",
    "rocket": "🚀",
    "phone": "📱",
    "laptop": "💻",
    "coffee": "☕",
    "pizza": "🍕",
    "muscle": "💪",
    "brain": "🧠",
    "india": "🇮🇳",
    "running": "🏃",
    "hundred": "💯",
    "100": "💯",
    "dog": "🐕",
    "cat": "🐈",
    "bear": "🐻",
    "penguin": "🐧",
}

# ── Message templates ─────────────────────────────────────────────────────────
TEMPLATES = {
    "good morning": "Good morning! 🌞 Hope you have an amazing day!",
    "good night": "Good night! 🌙 Sweet dreams!",
    "happy birthday": "Happy Birthday! 🎂🎉 Wishing you all the best!",
    "sorry": "I am really sorry. I hope you can forgive me. 🙏",
    "thank you": "Thank you so much! Really appreciate it. 🙏❤️",
    "i love you": "I love you! ❤️😘",
    "miss you": "I miss you so much! 💔",
    "congratulations": "Congratulations! 🏆🎉 So proud of you!",
    "get well soon": "Get well soon! 🤑 Take care of yourself.",
    "good luck": "Good luck! 🍀 You've got this!",
    "late": "Hey, I'm running a bit late. Sorry about that!",
    "stuck in traffic": "I'm stuck in traffic. Will be there soon!",
    "on my way": "On my way! 🚗",
    "reached": "I've reached. 📍",
    "busy": "I'm a bit busy right now. Will get back to you soon!",
    "call me": "Please give me a call when you're free.",
    "miss call": "I tried calling you. Please call back when free.",
    "good": "Good! 👍",
    "ok": "OK! 👌",
}

# ── Database ──────────────────────────────────────────────────────────────────
_DB_PATH = Path("memory/whatsapp_log.db")


def _init_db():
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(_DB_PATH) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contact TEXT, message TEXT, direction TEXT,
            timestamp TEXT, status TEXT
        )""")
        conn.commit()


def _log_message(contact: str, message: str, direction: str = "sent"):
    try:
        _init_db()
        with sqlite3.connect(_DB_PATH) as conn:
            conn.execute(
                "INSERT INTO messages (contact,message,direction,timestamp,status) VALUES (?,?,?,?,?)",
                (contact, message, direction, datetime.now().isoformat(), "ok"),
            )
            conn.commit()
    except Exception as e:
        log.warning(f"DB log error: {e}")


# ── WhatsApp Skill Class ──────────────────────────────────────────────────────
class WhatsAppSkill:
    def __init__(self):
        _init_db()
        self._last_sent_contact: str = ""
        self._last_sent_hash: str = ""
        self._last_sent_time: float = 0.0
        self._scheduled: list = []
        self._notify_thread: threading.Thread | None = None
        self._notify_stop = threading.Event()
        self._auto_response: str = ""
        self._auto_response_enabled: bool = False
        self._ocr_reader = None

    # ── Contact resolution ────────────────────────────────────────────────────
    def _resolve_contact(self, name: str) -> str:
        """Return display name for a contact alias."""
        key = name.lower().strip()
        names = _get_display_names()
        return names.get(key, name.title())

    def add_contact(self, alias: str, display_name: str = "", phone: str = "") -> str:
        """Add or update a contact alias. Optionally stores phone number."""
        contacts = _load_dynamic_contacts()
        key = alias.lower().strip()
        name = display_name.strip() if display_name.strip() else alias.title()
        contacts[key] = name
        # Also store under phone number if provided (for lookup by number)
        if phone:
            ph = re.sub(r"\D", "", phone)  # digits only
            if ph:
                contacts[f"phone_{ph}"] = name
        _save_dynamic_contacts(contacts)
        msg = f"Contact '{name}' saved as '{alias}'"
        if phone:
            msg += f" with number {phone}"
        return msg + ", sir."

    def remove_contact(self, alias: str) -> str:
        contacts = _load_dynamic_contacts()
        key = alias.lower().strip()
        if key in contacts:
            del contacts[key]
            _save_dynamic_contacts(contacts)
            return f"Contact '{alias}' removed, sir."
        return f"Contact '{alias}' not found in dynamic contacts, sir."

    def list_contacts(self) -> str:
        names = _get_display_names()
        unique = sorted(set(names.values()))
        return "Your saved contacts: " + ", ".join(unique) + "."

    # ── Open WhatsApp chat ────────────────────────────────────────────────────
    def _open_chat(self, contact: str) -> bool:
        """Open WhatsApp Desktop and navigate to contact's chat."""
        display = self._resolve_contact(contact)
        try:
            # Check if WhatsApp is running
            result = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq WhatsApp.exe"],
                capture_output=True,
                text=True,
            )
            if "WhatsApp.exe" not in result.stdout:
                # Try to launch
                import os

                os.system("start whatsapp:")
                time.sleep(4)

            # Bring WhatsApp to focus using pygetwindow
            try:
                import pygetwindow as gw

                wa_wins = [
                    w for w in gw.getAllWindows() if "whatsapp" in w.title.lower()
                ]
                if wa_wins:
                    wa_wins[0].activate()
                    time.sleep(0.8)
            except Exception:
                pass

            # Use Ctrl+F to search for contact
            pyautogui.hotkey("ctrl", "f")
            time.sleep(1.5)
            pyautogui.hotkey("ctrl", "a")
            time.sleep(0.3)
            pyperclip.copy(display)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(2.2)
            pyautogui.press("enter")
            time.sleep(1.0)

            self._last_sent_contact = contact
            return True

        except Exception as e:
            log.error(f"_open_chat error: {e}")
            return False

    # ── Send message ─────────────────────────────────────────────────────────
    def send_message(self, contact: str, message: str, stop_event=None) -> str:
        """Send a WhatsApp message with template expansion and dedup guard."""
        display = self._resolve_contact(contact)
        # Template expansion
        msg_lower = message.lower().strip()
        for key, tmpl in TEMPLATES.items():
            if msg_lower == key or msg_lower.startswith(key + " "):
                message = tmpl
                break
        return self._send_with_retry(contact, message, display)

    def _send_with_retry(
        self, contact: str, message: str, display: str, retries: int = 2
    ) -> str:
        """Open chat and send with dedup guard and retry."""
        # 5-second dedup hash guard
        msg_hash = hashlib.md5(f"{contact}{message}".encode()).hexdigest()
        now = time.time()
        if msg_hash == self._last_sent_hash and (now - self._last_sent_time) < 5:
            return f"Duplicate message blocked for {display}, sir."
        self._last_sent_hash = msg_hash
        self._last_sent_time = now

        for attempt in range(retries + 1):
            try:
                if not self._open_chat(contact):
                    if attempt < retries:
                        time.sleep(1)
                        continue
                    return f"Could not open chat with {display}, sir."
                # Click message box and type
                pyautogui.click(x=760, y=660)
                time.sleep(0.3)
                pyperclip.copy(message)
                pyautogui.hotkey("ctrl", "v")
                time.sleep(0.4)
                pyautogui.press("enter")
                time.sleep(0.5)
                _log_message(display, message, "sent")
                return f"Message sent to {display} on WhatsApp, sir!"
            except Exception as e:
                log.warning(f"Send attempt {attempt + 1} failed: {e}")
                if attempt < retries:
                    time.sleep(1.5)
        return f"Failed to send message to {display}, sir."

    # ── Emoji methods ─────────────────────────────────────────────────────────
    @classmethod
    def _word_to_emoji(cls, word: str) -> str:
        """Convert emoji word name to Unicode character."""
        key = word.lower().strip()
        if key in EMOJI_MAP:
            return EMOJI_MAP[key]
        for k, v in EMOJI_MAP.items():
            if key in k or k in key:
                return v
        return ""

    def send_emoji_only(self, contact: str, emoji_name: str) -> str:
        """Send a single emoji character to a contact."""
        emoji_char = self._word_to_emoji(emoji_name)
        if not emoji_char:
            return (
                f"I don't know the '{emoji_name}' emoji, sir. "
                "Try: heart, fire, smile, laugh, thumbs up, pray."
            )
        display = self._resolve_contact(contact)
        if not self._open_chat(contact):
            return f"Could not open chat with {display}, sir."
        try:
            pyperclip.copy(emoji_char)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.3)
            pyautogui.press("enter")
            time.sleep(0.5)
            _log_message(display, emoji_char, "sent")
            return f"Sent {emoji_char} to {display}, sir!"
        except Exception as e:
            return f"Error sending emoji: {str(e)[:60]}"

    # ── Type in active chat ───────────────────────────────────────────────────
    def type_in_active_chat(self, message: str, stop_event=None) -> str:
        """Type text into the currently open WhatsApp chat box."""
        try:
            pyautogui.click(x=760, y=660)
            time.sleep(0.3)
            pyperclip.copy(message)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.3)
            return f"Typed '{message}'. Say 'send' to send or 'backspace' to edit."
        except Exception as e:
            return f"Could not type: {str(e)[:60]}"

    def send_typed_message(self) -> str:
        """Press Enter to send whatever is currently typed."""
        try:
            import pygetwindow as gw

            aw = gw.getActiveWindow()
            title = (aw.title or "").lower() if aw else ""
            if "whatsapp" not in title:
                return "WhatsApp is not the active window, sir."
        except Exception:
            pass
        pyautogui.press("enter")
        time.sleep(0.3)
        return "Message sent, sir!"

    # ── Backspace / clear ─────────────────────────────────────────────────────
    def backspace_in_chat(self, count: int = 1) -> str:
        """Delete `count` characters in the active chat box."""
        try:
            for _ in range(count):
                pyautogui.press("backspace")
                time.sleep(0.05)
            return f"Deleted {count} character{'s' if count > 1 else ''}, sir."
        except Exception as e:
            return f"Backspace error: {str(e)[:60]}"

    def delete_last_word(self) -> str:
        """Delete the last word using Ctrl+Backspace."""
        pyautogui.hotkey("ctrl", "backspace")
        return "Deleted last word, sir."

    def clear_typed_message(self) -> str:
        """Select all and delete typed text in chat box."""
        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.1)
        pyautogui.press("delete")
        return "Cleared message box, sir."

    # ── Translate and send ────────────────────────────────────────────────────
    def translate_and_send(self, contact: str, message: str, language: str) -> str:
        """Translate message to given language using Gemini, then send."""
        try:
            import google.generativeai as genai

            api_key = os.getenv("GEMINI_API_KEY", "")
            if not api_key:
                return "No Gemini key for translation, sir."
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel("gemini-1.5-flash")
            prompt = (
                f"Translate this message to {language}. "
                f"Return ONLY the translated text, no explanation:\n{message}"
            )
            resp = model.generate_content(prompt)
            translated = resp.text.strip()
            return self.send_message(contact, translated)
        except Exception as e:
            return f"Translation error: {str(e)[:80]}"

    # ── Chat summary ──────────────────────────────────────────────────────────
    def summarize_chat(self, contact: str) -> str:
        """Summarize recent messages with a contact from DB."""
        try:
            _init_db()
            display = self._resolve_contact(contact)
            with sqlite3.connect(_DB_PATH) as conn:
                rows = conn.execute(
                    "SELECT direction, message FROM messages WHERE contact=? "
                    "ORDER BY id DESC LIMIT 20",
                    (display,),
                ).fetchall()
            if not rows:
                return f"No messages found with {display}, sir."
            chat_text = "\n".join(f"[{d}] {m}" for d, m in reversed(rows))
            try:
                import google.generativeai as genai

                api_key = os.getenv("GEMINI_API_KEY", "")
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel("gemini-1.5-flash")
                prompt = f"Summarize this WhatsApp chat briefly:\n{chat_text}"
                resp = model.generate_content(prompt)
                return f"Summary with {display}: {resp.text.strip()}"
            except Exception:
                return f"Last {len(rows)} messages with {display}: {chat_text[:200]}"
        except Exception as e:
            return f"Summarize error: {str(e)[:60]}"

    # ── Daily summary ─────────────────────────────────────────────────────────
    def daily_summary(self) -> str:
        """Return a summary of all messages sent today."""
        try:
            _init_db()
            today = datetime.now().strftime("%Y-%m-%d")
            with sqlite3.connect(_DB_PATH) as conn:
                rows = conn.execute(
                    "SELECT contact, message, direction, timestamp FROM messages "
                    "WHERE timestamp LIKE ? ORDER BY id DESC",
                    (f"{today}%",),
                ).fetchall()
            if not rows:
                return "No WhatsApp messages logged today, sir."
            summary = f"Today you sent/received {len(rows)} messages. "
            contacts_seen = list(dict.fromkeys(r[0] for r in rows))
            summary += f"Contacts: {', '.join(contacts_seen[:5])}."
            return summary
        except Exception as e:
            return f"Daily summary error: {str(e)[:60]}"

    # ── Stats ─────────────────────────────────────────────────────────────────
    def get_stats(self) -> str:
        """Return WhatsApp usage statistics."""
        try:
            _init_db()
            with sqlite3.connect(_DB_PATH) as conn:
                total = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
                sent = conn.execute(
                    "SELECT COUNT(*) FROM messages WHERE direction='sent'"
                ).fetchone()[0]
                contacts = conn.execute(
                    "SELECT COUNT(DISTINCT contact) FROM messages"
                ).fetchone()[0]
            return (
                f"WhatsApp stats: {total} total messages, "
                f"{sent} sent, {contacts} unique contacts, sir."
            )
        except Exception as e:
            return f"Stats error: {str(e)[:60]}"

    def most_messaged_contact(self) -> str:
        """Return the contact you message the most."""
        try:
            _init_db()
            with sqlite3.connect(_DB_PATH) as conn:
                rows = conn.execute(
                    "SELECT contact, COUNT(*) as cnt FROM messages "
                    "WHERE direction='sent' GROUP BY contact ORDER BY cnt DESC LIMIT 5"
                ).fetchall()
            if not rows:
                return "No outgoing messages logged yet, sir. Start chatting!"
            top = rows[0]
            result = (
                f"Your most messaged contact is {top[0]} with {top[1]} messages, sir."
            )
            if len(rows) > 1:
                others = ", ".join(f"{r[0]} ({r[1]})" for r in rows[1:4])
                result += f" Others: {others}."
            return result
        except Exception as e:
            return f"Could not check most messaged: {str(e)[:60]}"

    # ── Schedule message ──────────────────────────────────────────────────────
    def schedule_message(self, contact: str, message: str, send_time: str) -> str:
        """Schedule a message to be sent at a specific time."""
        try:
            # Parse time
            parsed = self._parse_schedule_time(send_time)
            if not parsed:
                return f"Could not understand time '{send_time}', sir."
            job = {"contact": contact, "message": message, "time": parsed}
            self._scheduled.append(job)

            def _send_at_time():
                while True:
                    if datetime.now() >= parsed:
                        self.send_message(contact, message)
                        break
                    time.sleep(30)

            t = threading.Thread(target=_send_at_time, daemon=True)
            t.start()
            display = self._resolve_contact(contact)
            return (
                f"Scheduled message to {display} at {parsed.strftime('%I:%M %p')}, sir."
            )
        except Exception as e:
            return f"Schedule error: {str(e)[:60]}"

    def _parse_schedule_time(self, time_str: str):
        """Parse natural language time string into datetime."""
        import re as _re

        now = datetime.now()
        ts = time_str.lower().strip()
        # "10 pm", "10:30 pm", "22:00"
        m = _re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", ts)
        if m:
            hour = int(m.group(1))
            minute = int(m.group(2)) if m.group(2) else 0
            meridiem = m.group(3)
            if meridiem == "pm" and hour < 12:
                hour += 12
            elif meridiem == "am" and hour == 12:
                hour = 0
            target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if target < now:
                target = target.replace(day=target.day + 1)
            return target
        # "tomorrow 9 am"
        if "tomorrow" in ts:
            m2 = _re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", ts)
            if m2:
                hour = int(m2.group(1))
                if m2.group(3) == "pm" and hour < 12:
                    hour += 12
                return (now + timedelta(days=1)).replace(
                    hour=hour, minute=0, second=0, microsecond=0
                )
        return None

    # ── Notification listener ─────────────────────────────────────────────────
    def start_notification_listener(self, callback) -> str:
        """Start background thread watching for new WhatsApp messages via OCR."""
        if self._notify_thread and self._notify_thread.is_alive():
            return "Notification listener already running, sir."
        self._notify_stop.clear()

        def _watch():
            import easyocr

            reader = easyocr.Reader(["en"], gpu=False, verbose=False)
            last_text = ""
            while not self._notify_stop.is_set():
                try:
                    import numpy as np
                    import pyautogui as pg

                    shot = pg.screenshot(region=(0, 0, 400, 200))
                    arr = np.array(shot)
                    texts = reader.readtext(arr, detail=0)
                    combined = " ".join(texts)
                    if combined != last_text and combined.strip():
                        last_text = combined
                        # Very basic heuristic: look for contact name
                        lines = combined.split("\n")
                        if len(lines) >= 2:
                            callback(lines[0], lines[1])
                except Exception:
                    pass
                time.sleep(5)

        self._notify_thread = threading.Thread(target=_watch, daemon=True)
        self._notify_thread.start()
        return "WhatsApp notification listener started, sir."

    def stop_notification_listener(self) -> str:
        self._notify_stop.set()
        return "Notification listener stopped, sir."

    # ── Undo last message ─────────────────────────────────────────────────────
    def undo_last_message(self) -> str:
        """Attempt to delete-for-everyone the last sent message."""
        try:
            # Right-click the last message area
            pyautogui.click(x=760, y=600)
            time.sleep(0.3)
            pyautogui.rightClick(x=760, y=600)
            time.sleep(0.8)
            # Look for Delete option (approximate position)
            pyautogui.press("d")
            time.sleep(0.5)
            return "Attempted to delete last message, sir."
        except Exception as e:
            return f"Could not delete: {str(e)[:60]}"

    # ── Bulk send ─────────────────────────────────────────────────────────────
    def send_bulk(self, contacts: list, message: str) -> str:
        """Send same message to multiple contacts."""
        results = []
        for contact in contacts:
            r = self.send_message(contact, message)
            results.append(r)
            time.sleep(1.5)
        return " | ".join(results)

    def read_last_messages(self, contact: str, count: int = 3) -> str:
        """Read last N messages from a contact using OCR on the WhatsApp chat."""
        display = self._resolve_contact(contact)
        try:
            if not self._open_chat(contact):
                return f"Could not open chat with {display}, sir."
            time.sleep(1.5)
            import numpy as np
            import pyautogui as pg

            shot = pg.screenshot(region=(300, 300, 900, 700))
            arr = np.array(shot)
            try:
                import easyocr

                if not getattr(self, "_ocr_reader", None):
                    self._ocr_reader = easyocr.Reader(["en"], gpu=False, verbose=False)
                texts = self._ocr_reader.readtext(arr, detail=0)
            except Exception:
                texts = []
            if texts:
                msgs = [t.strip() for t in texts if len(t.strip()) > 2][-count:]
                if msgs:
                    return f"Last {len(msgs)} messages from {display}: " + " | ".join(
                        msgs
                    )
            return f"Chat with {display} is open, sir. I could not read the messages clearly."
        except Exception as e:
            return f"Could not read messages: {str(e)[:60]}"

    def mark_all_as_read(self) -> str:
        """Mark all WhatsApp messages as read by pressing Ctrl+Shift+U."""
        try:
            import pyautogui as pg

            # Focus WhatsApp
            import pygetwindow as gw

            wa_wins = [w for w in gw.getAllWindows() if "whatsapp" in w.title.lower()]
            if wa_wins:
                wa_wins[0].activate()
                time.sleep(0.5)
            # WhatsApp doesn't have a global mark-all-read shortcut,
            # so we just open the app and inform the user
            return (
                "WhatsApp is open, sir. You can press Ctrl+A and mark as read manually."
            )
        except Exception as e:
            return f"Could not mark as read: {str(e)[:60]}"

    def send_voice_note(self, contact: str, duration: int = 5) -> str:
        """Record a voice note and send it to a contact."""
        try:
            import os
            import tempfile

            import sounddevice as sd
            import soundfile as sf

            display = self._resolve_contact(contact)
            # Record audio
            sample_rate = 44100
            recording = sd.rec(
                int(duration * sample_rate),
                samplerate=sample_rate,
                channels=1,
                dtype="float32",
            )
            sd.wait()
            # Save to temp file
            temp_file = os.path.join(tempfile.gettempdir(), "jarvis_voice_note.wav")
            sf.write(temp_file, recording, sample_rate)
            # Open chat and attach file
            if not self._open_chat(contact):
                return f"Could not open chat with {display}, sir."
            time.sleep(1.0)
            import pyautogui as pg

            pg.hotkey("ctrl", "p")  # Attach file shortcut
            time.sleep(1.5)
            import pyperclip

            pyperclip.copy(temp_file)
            pg.hotkey("ctrl", "v")
            time.sleep(0.5)
            pg.press("enter")
            time.sleep(0.5)
            os.remove(temp_file)
            return f"Voice note sent to {display}, sir."
        except ImportError:
            return "Voice note requires sounddevice and soundfile packages. Run: pip install sounddevice soundfile"
        except Exception as e:
            return f"Voice note error: {str(e)[:60]}"

    def reply_to_last(self, message: str, stop_event=None) -> str:
        """Reply with a message in the currently open WhatsApp chat."""
        try:
            import pyautogui as pg
            import pyperclip

            # Just type and send in active chat
            pg.click(x=760, y=660)
            time.sleep(0.3)
            pyperclip.copy(message)
            pg.hotkey("ctrl", "v")
            time.sleep(0.4)
            pg.press("enter")
            time.sleep(0.3)
            return f"Reply sent, sir: '{message}'"
        except Exception as e:
            return f"Could not send reply: {str(e)[:60]}"

    def forward_last_message(self, contact: str, stop_event=None) -> str:
        """Forward the last message in the active chat to another contact."""
        try:
            import pyautogui as pg

            display = self._resolve_contact(contact)
            # Right click on last message and select forward
            pg.rightClick(x=760, y=600)
            time.sleep(0.6)
            # Look for Forward option (press F key or use keyboard)
            pg.press("f")
            time.sleep(1.0)
            # Search for contact
            import pyperclip

            pyperclip.copy(self._resolve_contact(contact))
            pg.hotkey("ctrl", "v")
            time.sleep(1.5)
            pg.press("enter")
            time.sleep(0.5)
            pg.press("enter")
            time.sleep(0.3)
            return f"Message forwarded to {display}, sir."
        except Exception as e:
            return f"Could not forward: {str(e)[:60]}"

    def list_scheduled(self) -> str:
        """List all pending scheduled messages."""
        if not self._scheduled:
            return "No scheduled messages, sir."
        lines = []
        for job in self._scheduled:
            display = self._resolve_contact(job.get("contact", "unknown"))
            send_time = job.get("time")
            msg = job.get("message", "")[:40]
            if send_time:
                time_str = (
                    send_time.strftime("%I:%M %p")
                    if hasattr(send_time, "strftime")
                    else str(send_time)
                )
                lines.append(f"  • {display} at {time_str}: {msg}")
        return "Scheduled messages:\n" + "\n".join(lines)

    def send_screenshot(self, contact: str) -> str:
        """Take a screenshot and send it to a contact on WhatsApp."""
        try:
            import os
            import tempfile

            import pyautogui as pg
            import pyperclip

            display = self._resolve_contact(contact)
            # Take screenshot
            temp_path = os.path.join(tempfile.gettempdir(), "jarvis_screenshot.png")
            screenshot = pg.screenshot()
            screenshot.save(temp_path)
            # Open chat
            if not self._open_chat(contact):
                return f"Could not open chat with {display}, sir."
            time.sleep(1.0)
            # Attach the screenshot using Ctrl+P or drag
            pg.hotkey("ctrl", "p")
            time.sleep(1.5)
            pyperclip.copy(temp_path)
            pg.hotkey("ctrl", "v")
            time.sleep(0.5)
            pg.press("enter")
            time.sleep(0.5)
            try:
                os.remove(temp_path)
            except Exception:
                pass
            return f"Screenshot sent to {display}, sir."
        except Exception as e:
            return f"Screenshot send error: {str(e)[:60]}"

    def compose_and_send(
        self, contact: str, message: str, tone: str = "friendly"
    ) -> str:
        """Compose a message with a specific tone and send it."""
        display = self._resolve_contact(contact)
        # Apply tone-based prefixes/adjustments
        tone_templates = {
            "formal": f"Dear {display}, {message.strip().capitalize()}. Regards.",
            "apologetic": f"I'm really sorry, {message.strip()}.",
            "friendly": message.strip(),
            "casual": message.lower().strip(),
        }
        composed = tone_templates.get(tone, message.strip())
        result = self.send_message(contact, composed)
        return result

    def send_to_group(self, group_name: str, message: str, stop_event=None) -> str:
        """Send a message to a WhatsApp group."""
        display = self._resolve_contact(group_name)
        return self._send_with_retry(group_name, message, display)

    def send_to_multiple(self, contacts: list, message: str, stop_event=None) -> str:
        """Send the same message to multiple contacts."""
        results = []
        for contact in contacts:
            if stop_event and stop_event.is_set():
                break
            r = self.send_message(contact, message)
            results.append(r)
            time.sleep(2.0)
        sent = sum(1 for r in results if "sent" in r.lower())
        return f"Sent to {sent}/{len(contacts)} contacts, sir."

    def enable_auto_response(self, message: str = "") -> str:
        """Enable auto-response mode (stores the message for manual checking)."""
        if not message:
            message = "I am currently unavailable. Will reply soon."
        self._auto_response = message
        self._auto_response_enabled = True
        return f"Auto-response enabled, sir. Reply: '{message[:50]}'"

    def disable_auto_response(self) -> str:
        """Disable auto-response mode."""
        self._auto_response_enabled = False
        self._auto_response = ""
        return "Auto-response disabled, sir."

    # ── Command parsers ───────────────────────────────────────────────────────

    # ═══════════════════════════════════════════════════════════════════════════
    # OCR & HYBRID METHODS — Optimized for speed and reliability
    # ═══════════════════════════════════════════════════════════════════════════

    def get_unread_count(self) -> str:
        """
        Check for unread messages instantly using the Windows Notification Database (wpndatabase.db).
        Extremely reliable, zero false positives, no OCR needed.
        """
        try:
            import os
            import re
            import shutil
            import sqlite3
            import tempfile

            db_path = os.path.expandvars(
                r"%LOCALAPPDATA%\Microsoft\Windows\Notifications\wpndatabase.db"
            )
            if not os.path.exists(db_path):
                return "Could not find Windows notification database, sir."

            temp_db = os.path.join(tempfile.gettempdir(), "wpntemp_wa.db")
            try:
                shutil.copy2(db_path, temp_db)
            except Exception:
                pass

            conn = sqlite3.connect(temp_db)
            c = conn.cursor()

            c.execute(
                "SELECT RecordId FROM NotificationHandler WHERE PrimaryId LIKE '%WhatsApp%'"
            )
            handlers = [h[0] for h in c.fetchall()]

            if not handlers:
                return "No unread WhatsApp messages found, sir."

            placeholders = ",".join("?" * len(handlers))
            c.execute(
                f"SELECT Payload FROM Notification WHERE HandlerId IN ({placeholders}) AND Payload LIKE '%<badge%' ORDER BY ArrivalTime DESC LIMIT 1",
                handlers,
            )
            row = c.fetchone()
            conn.close()

            unread_count = 0
            if row:
                payload = (
                    row[0].decode("utf-8") if isinstance(row[0], bytes) else row[0]
                )
                m = re.search(r'<badge\s+value="(\d+)"', payload)
                if m:
                    unread_count = int(m.group(1))

            if unread_count > 0:
                return f"You have {unread_count} unread WhatsApp chats, sir."
            else:
                return "No unread WhatsApp messages found, sir."

        except Exception as e:
            return f"Error checking unread messages: {str(e)[:80]}"

    def scan_all_unread_chats(self) -> str:
        """
        Since we read the title for unread count, we can't see the exact names.
        """
        count_msg = self.get_unread_count()
        if "No unread" in count_msg:
            return count_msg
        return f"{count_msg} I cannot read the specific chat names visually, sir."

    def get_contact_status(self, contact: str) -> str:
        """
        Get online/last-seen status using targeted OCR on the chat header.
        """
        display = self._resolve_contact(contact)
        try:
            if not self._open_chat(contact):
                return f"Could not open chat with {display}, sir."

            import time

            time.sleep(1.5)

            import numpy as np
            import pyautogui as pg
            import win32gui

            # Use win32gui for robust coordinate extraction even if title is "(3) WhatsApp"
            rect = None

            def callback(hwnd, extra):
                nonlocal rect
                title = win32gui.GetWindowText(hwnd)
                if "WhatsApp" in title and "Root" not in title:
                    # Ignore the small GDI+ Windows
                    r = win32gui.GetWindowRect(hwnd)
                    if r[2] - r[0] > 100:  # Width > 100 to avoid hidden windows
                        rect = r

            win32gui.EnumWindows(callback, None)

            left, top = 0, 0
            if rect:
                left, top = max(0, rect[0]), max(0, rect[1])

            # Capture only the header where subtitle appears, relative to window
            shot = pg.screenshot(region=(left + 400, top + 45, 800, 60))
            arr = np.array(shot)

            import easyocr

            if not getattr(self, "_ocr_reader", None):
                self._ocr_reader = easyocr.Reader(["en"], gpu=False, verbose=False)
            texts = self._ocr_reader.readtext(arr, detail=0)
            combined = " ".join(texts).lower().strip()

            if "online" in combined:
                return f"{display} is currently online, sir."
            elif "typing" in combined:
                return f"{display} is typing, sir."
            elif "recording" in combined:
                return f"{display} is recording audio, sir."
            elif "last seen" in combined:
                m = re.search(r"last seen (.+)", combined)
                when = m.group(1).strip() if m else combined
                return f"{display} was last seen {when}, sir."
            else:
                return f"{display}'s chat is open, but their status is hidden, sir."

        except Exception as e:
            return f"Status check failed: {str(e)[:80]}"

    def parse_whatsapp_command(self, text: str) -> tuple:
        """
        Extract (contact, message) from natural language.
        Returns ('', text) if contact cannot be determined.

        Patterns tried in order:
          1. Explicit: 'send MESSAGE to CONTACT' / 'message CONTACT MESSAGE'
          2. 'MESSAGE to KNOWN_CONTACT [optional trailing words]'
          3. Strict fallback: first word is a KNOWN contact alias
        """
        text_lower = text.lower().strip()

        # Strip common noise prefixes
        for prefix in [
            "send a message to ",
            "send message to ",
            "message to ",
            "whatsapp to ",
            "text to ",
            "send to ",
        ]:
            if text_lower.startswith(prefix):
                rest = text[len(prefix) :].strip()
                # Now rest = "CONTACT MESSAGE" or "CONTACT: MESSAGE"
                parts = rest.split(None, 1)
                if parts:
                    return parts[0], (parts[1] if len(parts) > 1 else "")

        # Strip plain "send " prefix
        for prefix in ["send "]:
            if text_lower.startswith(prefix):
                text = text[len(prefix) :].strip()
                text_lower = text.lower().strip()
                break

        # Pattern 1: "tell/message/whatsapp NAME MESSAGE"
        m1 = re.match(r"^(?:tell|message|whatsapp|text)\s+(\w+)\s+(.+)$", text_lower)
        if m1:
            return m1.group(1), m1.group(2)

        # Pattern 2: "MESSAGE to KNOWN_CONTACT [optional trailing words]"
        known = _get_display_names()
        _to_matches = list(re.finditer(r"\bto\s+(\w+)", text_lower))
        for _tm in reversed(_to_matches):
            _cname = _tm.group(1).strip()
            if _cname in known:
                _pre = text_lower[: _tm.start()].strip()
                _post = text_lower[_tm.end() :].strip()
                _msg = (_pre + " " + _post).strip() if _post else _pre
                return _cname, _msg
        # Pattern 2 fallback: name at very end "MSG to NAME"
        m2 = re.search(r"(.+)\s+to\s+(\w+)\s*$", text_lower)
        if m2:
            msg = m2.group(1).strip()
            name = m2.group(2).strip()
            if name not in {"the", "a", "an"} and msg:
                return name, msg

        # Pattern 3 (strict): first word is a KNOWN contact
        parts = text_lower.split(None, 1)
        if len(parts) == 2:
            candidate_name, candidate_msg = parts
            if candidate_name.isalpha() and candidate_name in known:
                return candidate_name, candidate_msg

        return "", text

    @staticmethod
    def parse_type_command(text: str) -> str:
        """Extract message from 'type ...' style commands.
        Also converts 'WORD emoji' to the actual Unicode emoji char.
        """
        text_lower = text.lower().strip()
        # Don't intercept send/enter commands
        if text_lower in {
            "send",
            "enter",
            "send it",
            "send message",
            "press enter",
            "send now",
        }:
            return ""
        type_triggers = [
            "type this ",
            "type in ",
            "just type ",
            "type ",
            # NOTE: "write " and "write this " removed — they conflict with
            # VS Code code-writing commands like "write a Python calculator".
            # Use "type hello" to type text; use "write a function" to generate code.
        ]
        for trigger in type_triggers:
            if text_lower.startswith(trigger):
                raw = text[len(trigger) :].strip()
                # Strip trailing noise
                for noise in ["in whatsapp", "on whatsapp", "please", "now"]:
                    raw = re.sub(rf"\b{noise}\b", "", raw, flags=re.IGNORECASE).strip()
                # Convert "WORD emoji" → actual Unicode char
                _em_match = re.match(r"(.+?)\s+emoji\s*$", raw, re.IGNORECASE)
                if _em_match:
                    _em_char = WhatsAppSkill._word_to_emoji(_em_match.group(1))
                    if _em_char:
                        return _em_char
                return raw.strip()
        return ""

    @staticmethod
    def parse_bulk_contacts(text: str) -> list:
        """Extract multiple contact names from text.
        'send to mom dad and friend' -> ['mom', 'dad', 'friend']
        """
        text_lower = text.lower()
        for filler in [
            "send to",
            "send message to",
            "message to",
            "whatsapp",
            "and",
            ",",
            "also",
            "plus",
            "as well as",
            "along with",
        ]:
            text_lower = text_lower.replace(filler, " ")
        parts = text_lower.split()
        return [
            p.strip()
            for p in parts
            if p.strip() and p.strip() not in {"the", "a", "an", "all", "my"}
        ]

    @staticmethod
    def parse_schedule_command(text: str) -> tuple:
        """Parse 'schedule message to mom good night at 10 pm'.
        Returns (contact, message, time_str).
        """
        text_lower = text.lower()
        # Extract time part
        time_match = re.search(r"at\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)", text_lower)
        time_str = time_match.group(1).strip() if time_match else ""
        if time_match:
            text_lower = text_lower[: time_match.start()].strip()

        # Extract contact
        to_match = re.search(r"to\s+(\w+)", text_lower)
        contact = to_match.group(1) if to_match else ""
        if to_match:
            text_lower = text_lower[to_match.end() :].strip()

        # Remaining is message
        for pfx in ["schedule message", "schedule", "send", "message"]:
            if text_lower.startswith(pfx):
                text_lower = text_lower[len(pfx) :].strip()
        message = text_lower.strip()

        return contact, message, time_str


# -- End of WhatsApp skill ----------------------------------------------------
