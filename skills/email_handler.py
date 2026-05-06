"""
JARVIS — skills/email_handler.py
Full-featured Gmail skill — 20 features matching WhatsApp gold standard.

Features:
  1.  Send email (basic)
  2.  Send with attachment
  3.  AI compose + tone control (Gemini)
  4.  Smart subject generator (AI)
  5.  Undo send (10-second buffer)
  6.  Schedule email (SQLite queue)
  7.  Reply to last email
  8.  Forward email
  9.  Delete email (IMAP)
  10. Search emails
  11. Read recent emails
  12. Check unread count
  13. Morning email brief (AI summary)
  14. Mark as read / unread
  15. Filter by folder
  16. Email templates
  17. Fuzzy contact matching
  18. SQLite sent-log + analytics
  19. Email stats (today / total / top contacts)
  20. Daily summary

Voice commands:
  "Send email to mom saying I'll be late"
  "Email boss formal I'm sick today"
  "Reply to last email from rahul okay noted"
  "Forward last email to dad"
  "Delete last email"
  "Search emails from professor"
  "Schedule email to mom good night at 10 PM"
  "Check unread emails"
  "Morning email brief"
  "Email stats"
  "Send leave request email to boss"
"""

import os, re, smtplib, imaplib, email, sqlite3, time, threading, tempfile
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv
from utils.logger import log
from utils.safe_api import safe_json_extract

load_dotenv()

# ─── Paths ────────────────────────────────────────────────────
_DATA_DIR = Path(__file__).parent.parent / "data"
_DB_PATH  = _DATA_DIR / "email_history.db"

# ─── Config ───────────────────────────────────────────────────
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
IMAP_HOST = "imap.gmail.com"
UNDO_DELAY = 10        # seconds before email actually sends
SCHEDULER_INTERVAL = 30

# ─── Contacts ─────────────────────────────────────────────────
_RAW_CONTACTS = {
    "mom":    os.getenv("CONTACT_MOM",    ""),
    "dad":    os.getenv("CONTACT_DAD",    ""),
    "friend": os.getenv("CONTACT_FRIEND", ""),
    "work":   os.getenv("CONTACT_WORK",   ""),
    "boss":   os.getenv("CONTACT_WORK",   ""),
    "rahul":  os.getenv("CONTACT_RAHUL",  ""),
    "priya":  os.getenv("CONTACT_PRIYA",  ""),
}

# ─── Email Templates ──────────────────────────────────────────
TEMPLATES = {
    "leave request": (
        "Leave Request",
        "Dear Sir/Madam,\n\nI am writing to request a leave of absence. "
        "Kindly grant approval at your earliest convenience.\n\nThank you.\nRegards, Srini"
    ),
    "daily report": (
        "Daily Work Report",
        "Hi,\n\nPlease find my daily work report attached.\n\nTasks completed today:\n- \n\nRegards, Srini"
    ),
    "apology": (
        "Apologies for the inconvenience",
        "Dear,\n\nI sincerely apologize for any inconvenience caused. "
        "I will ensure this does not happen again.\n\nRegards, Srini"
    ),
    "follow up": (
        "Following Up",
        "Hi,\n\nI wanted to follow up on my previous email. "
        "Please let me know if you have any updates.\n\nRegards, Srini"
    ),
    "thank you": (
        "Thank You",
        "Dear,\n\nThank you so much for your time and support. "
        "I truly appreciate it.\n\nBest regards, Srini"
    ),
    "good morning": (
        "Good Morning!",
        "Good morning! Hope you have a wonderful and productive day ahead! 🌟"
    ),
    "good night": (
        "Good Night!",
        "Good night! Rest well and see you tomorrow! 🌙"
    ),
}

# ─── Gemini compose helper ────────────────────────────────────
def _gemini_compose(prompt: str) -> str:
    """Call Gemini API to compose text. Returns '' on failure."""
    try:
        import requests
        key = (
            os.getenv("GEMINI_API_KEY") or
            os.getenv("GEMINI_API_KEY_2") or ""
        ).strip()
        if not key:
            return ""
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/"
            f"models/gemini-2.0-flash:generateContent?key={key}"
        )
        body = {"contents": [{"parts": [{"text": prompt}]}]}
        r = requests.post(url, json=body, timeout=10)

        # Check status code and safely extract response
        if r.status_code != 200:
            log.warning(f"Gemini API returned status {r.status_code}")
            return ""

        data = r.json()
        text = safe_json_extract(data, "candidates", 0, "content", "parts", 0, "text", default="")
        return text.strip()
    except Exception as e:
        log.warning(f"Gemini compose failed: {e}")
        return ""

# ─── SQLite setup ─────────────────────────────────────────────
def _init_db():
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS sent_emails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recipient TEXT, email_addr TEXT,
            subject TEXT, body TEXT,
            sent_at TEXT, has_attachment INTEGER DEFAULT 0
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS scheduled_emails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recipient TEXT, email_addr TEXT,
            subject TEXT, body TEXT,
            send_at TEXT, attachment TEXT DEFAULT '',
            status TEXT DEFAULT 'pending'
        )
    """)
    conn.commit()
    conn.close()

def _log_sent(recipient, email_addr, subject, body, attachment=False):
    try:
        _init_db()
        conn = sqlite3.connect(_DB_PATH)
        conn.execute(
            "INSERT INTO sent_emails (recipient,email_addr,subject,body,sent_at,has_attachment) "
            "VALUES (?,?,?,?,?,?)",
            (recipient, email_addr, subject, body[:300],
             datetime.now().isoformat(), int(attachment))
        )
        conn.commit()
        conn.close()
    except Exception as e:
        log.warning(f"Email log error: {e}")


# ══════════════════════════════════════════════════════════════
class EmailHandler:
    """Full-featured Gmail skill — 20 features."""

    def __init__(self):
        self.address  = os.getenv("GMAIL_ADDRESS", "").strip()
        self.password = os.getenv("GMAIL_APP_PASSWORD", "").strip()
        self._ready   = bool(self.address and self.password)
        self._last_received: dict = {}   # for reply/forward
        self._undo_pending: dict  = {}   # for undo send
        _init_db()
        if self._ready:
            log.info(f"EmailHandler ready ✅ ({self.address})")
            self._start_scheduler()
        else:
            log.warning("Email: add GMAIL_ADDRESS + GMAIL_APP_PASSWORD to .env")

    # ──────────────────────────────────────────────────────────
    # HELPER: not configured
    # ──────────────────────────────────────────────────────────
    def _nc(self) -> str:
        return ("Gmail not set up. Add GMAIL_ADDRESS and GMAIL_APP_PASSWORD to .env — "
                "use an App Password from myaccount.google.com → Security → App Passwords.")

    # ══════════════════════════════════════════════════════════
    # 1. FUZZY CONTACT MATCH
    # ══════════════════════════════════════════════════════════
    def _resolve(self, name: str) -> str:
        """Resolve name → email address. Fuzzy-matches contacts."""
        name_l = name.lower().strip()
        if "@" in name:
            return name
        # Exact
        if name_l in _RAW_CONTACTS and _RAW_CONTACTS[name_l]:
            return _RAW_CONTACTS[name_l]
        # Partial
        for key, addr in _RAW_CONTACTS.items():
            if addr and (key in name_l or name_l in key):
                return addr
        # Try fuzzywuzzy
        try:
            from fuzzywuzzy import process
            keys = [k for k, v in _RAW_CONTACTS.items() if v]
            match, score = process.extractOne(name_l, keys)
            if score >= 70:
                return _RAW_CONTACTS[match]
        except ImportError:
            pass
        return ""

    # ══════════════════════════════════════════════════════════
    # 2. CORE SMTP SEND
    # ══════════════════════════════════════════════════════════
    def _smtp_send(self, to_email: str, subject: str, body: str,
                   attachment_path: str = "") -> bool:
        """Send via SMTP. Returns True on success."""
        msg = MIMEMultipart()
        msg["From"]    = self.address
        msg["To"]      = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        if attachment_path and os.path.exists(attachment_path):
            with open(attachment_path, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
            encoders.encode_base64(part)
            fname = os.path.basename(attachment_path)
            part.add_header("Content-Disposition", f"attachment; filename={fname}")
            msg.attach(part)

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
            s.ehlo(); s.starttls()
            s.login(self.address, self.password)
            s.sendmail(self.address, to_email, msg.as_string())
        return True

    # ══════════════════════════════════════════════════════════
    # 3. SEND EMAIL (Feature 1 + Feature 19 undo)
    # ══════════════════════════════════════════════════════════
    def send_email(self, to_name: str, subject: str, body: str,
                   attachment_path: str = "", undo_window: bool = True) -> str:
        """Send email with optional 10-second undo window."""
        if not self._ready: return self._nc()
        to_email = self._resolve(to_name)
        if not to_email:
            return (f"I don't have {to_name}'s email. "
                    f"Add CONTACT_{to_name.upper()} to .env")

        uid = str(time.time())
        self._undo_pending[uid] = True

        if undo_window:
            log.info(f"Email queued — {UNDO_DELAY}s undo window ({to_name})")
            def _send_after_delay():
                time.sleep(UNDO_DELAY)
                if not self._undo_pending.get(uid, False):
                    log.info("Email cancelled by undo.")
                    return
                try:
                    self._smtp_send(to_email, subject, body, attachment_path)
                    _log_sent(to_name, to_email, subject, body, bool(attachment_path))
                    log.info(f"Email sent to {to_name}")
                except Exception as e:
                    log.error(f"Delayed send failed: {e}")
            threading.Thread(target=_send_after_delay, daemon=True).start()
            self._last_uid = uid
            return (f"Email to {to_name} will send in {UNDO_DELAY} seconds. "
                    f"Say 'undo email' to cancel.")
        else:
            try:
                self._smtp_send(to_email, subject, body, attachment_path)
                _log_sent(to_name, to_email, subject, body, bool(attachment_path))
                return f"Email sent to {to_name} successfully!"
            except smtplib.SMTPAuthenticationError:
                return "Gmail auth failed — use an App Password, not your regular password."
            except Exception as e:
                log.error(f"Send error: {e}")
                return f"Couldn't send: {str(e)[:80]}"

    # ══════════════════════════════════════════════════════════
    # 4. UNDO SEND (Feature 19)
    # ══════════════════════════════════════════════════════════
    def undo_send(self) -> str:
        uid = getattr(self, "_last_uid", None)
        if uid and uid in self._undo_pending:
            self._undo_pending[uid] = False
            return "Email cancelled, sir! It will not be sent."
        return "No email to cancel — the send window has already passed."

    # ══════════════════════════════════════════════════════════
    # 5. AI COMPOSE + TONE (Feature 3 + 4)
    # ══════════════════════════════════════════════════════════
    def ai_compose_and_send(self, to_name: str, instruction: str,
                            tone: str = "friendly") -> str:
        """Gemini writes the email body + subject, then sends."""
        if not self._ready: return self._nc()

        prompt = (
            f"Write a short email in a {tone} tone that conveys: {instruction}. "
            f"Format your response as:\nSUBJECT: <subject line>\nBODY: <email body>\n"
            f"Keep body under 4 sentences. No markdown. No quotation marks."
        )
        result = _gemini_compose(prompt)
        if not result:
            # Fallback: send instruction directly
            return self.send_email(to_name, "Message from JARVIS", instruction)

        subject, body = "Message from JARVIS", instruction
        for line in result.splitlines():
            if line.upper().startswith("SUBJECT:"):
                subject = line.split(":", 1)[1].strip()
            elif line.upper().startswith("BODY:"):
                body = line.split(":", 1)[1].strip()

        log.info(f"AI composed email → subject: {subject[:50]}")
        return self.send_email(to_name, subject, body)

    # ══════════════════════════════════════════════════════════
    # 6. SEND WITH ATTACHMENT (Feature 2)
    # ══════════════════════════════════════════════════════════
    def send_with_attachment(self, to_name: str, subject: str,
                             body: str, file_path: str) -> str:
        if not self._ready: return self._nc()
        if not os.path.exists(file_path):
            return f"File not found: {file_path}"
        fname = os.path.basename(file_path)
        return self.send_email(to_name, subject, body,
                               attachment_path=file_path, undo_window=False)

    # ══════════════════════════════════════════════════════════
    # 7. EMAIL TEMPLATES (Feature 16)
    # ══════════════════════════════════════════════════════════
    def send_template(self, to_name: str, template_name: str) -> str:
        """Send a pre-built template email."""
        if not self._ready: return self._nc()
        t = template_name.lower().strip()
        matched = None
        for key in TEMPLATES:
            if key in t or t in key:
                matched = key
                break
        if not matched:
            keys = ", ".join(TEMPLATES.keys())
            return f"Template '{template_name}' not found. Available: {keys}"
        subject, body = TEMPLATES[matched]
        return self.send_email(to_name, subject, body, undo_window=False)

    # ══════════════════════════════════════════════════════════
    # 8. SCHEDULE EMAIL (Feature 6)
    # ══════════════════════════════════════════════════════════
    def schedule_email(self, to_name: str, subject: str,
                       body: str, send_at: str) -> str:
        """Schedule an email. send_at = 'HH:MM' or 'YYYY-MM-DD HH:MM'."""
        if not self._ready: return self._nc()
        to_email = self._resolve(to_name)
        if not to_email:
            return f"I don't have {to_name}'s email."

        # Parse send_at time
        send_dt = self._parse_schedule_time(send_at)
        if not send_dt:
            return f"Couldn't understand the time '{send_at}'. Try '10:30 PM' or '22:30'."

        try:
            _init_db()
            conn = sqlite3.connect(_DB_PATH)
            conn.execute(
                "INSERT INTO scheduled_emails "
                "(recipient,email_addr,subject,body,send_at) VALUES (?,?,?,?,?)",
                (to_name, to_email, subject, body, send_dt.isoformat())
            )
            conn.commit(); conn.close()
            t_str = send_dt.strftime("%I:%M %p")
            log.info(f"Email scheduled to {to_name} at {t_str}")
            return f"Email to {to_name} scheduled for {t_str}, sir!"
        except Exception as e:
            return f"Couldn't schedule: {str(e)[:60]}"

    def _parse_schedule_time(self, text: str):
        """Parse time string into datetime."""
        t = text.lower().strip()
        now = datetime.now()
        # HH:MM am/pm
        m = re.search(r"(\d{1,2}):?(\d{2})?\s*(am|pm)", t)
        if m:
            hour = int(m.group(1))
            minute = int(m.group(2)) if m.group(2) else 0
            if m.group(3) == "pm" and hour != 12: hour += 12
            elif m.group(3) == "am" and hour == 12: hour = 0
            dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if dt < now: dt += timedelta(days=1)
            return dt
        # 24h HH:MM
        m = re.search(r"(\d{1,2}):(\d{2})", t)
        if m:
            hour, minute = int(m.group(1)), int(m.group(2))
            dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if dt < now: dt += timedelta(days=1)
            return dt
        return None

    def cancel_scheduled(self, to_name: str = "") -> str:
        """Cancel a scheduled email."""
        try:
            _init_db()
            conn = sqlite3.connect(_DB_PATH)
            if to_name:
                conn.execute(
                    "UPDATE scheduled_emails SET status='cancelled' "
                    "WHERE status='pending' AND recipient LIKE ?",
                    (f"%{to_name}%",)
                )
            else:
                conn.execute(
                    "UPDATE scheduled_emails SET status='cancelled' "
                    "WHERE status='pending'"
                )
            conn.commit(); conn.close()
            return f"Scheduled email{'s' if not to_name else ''} cancelled, sir."
        except Exception as e:
            return f"Couldn't cancel: {str(e)[:60]}"

    def list_scheduled(self) -> str:
        """Show all pending scheduled emails."""
        try:
            _init_db()
            conn = sqlite3.connect(_DB_PATH)
            rows = conn.execute(
                "SELECT recipient, subject, send_at FROM scheduled_emails "
                "WHERE status='pending' ORDER BY send_at"
            ).fetchall()
            conn.close()
            if not rows:
                return "No scheduled emails, sir."
            parts = [f"{r[0]} at {r[2][:16]} — '{r[1]}'" for r in rows]
            return f"Scheduled: " + "; ".join(parts)
        except Exception as e:
            return f"Couldn't list scheduled: {str(e)[:60]}"

    def _start_scheduler(self):
        """Background thread that sends scheduled emails."""
        def _loop():
            while True:
                try:
                    _init_db()
                    conn = sqlite3.connect(_DB_PATH)
                    now  = datetime.now().isoformat()
                    rows = conn.execute(
                        "SELECT id,recipient,email_addr,subject,body,attachment "
                        "FROM scheduled_emails WHERE status='pending' AND send_at<=?",
                        (now,)
                    ).fetchall()
                    for row in rows:
                        rid, to_name, to_email, subj, body, att = row
                        try:
                            self._smtp_send(to_email, subj, body, att or "")
                            _log_sent(to_name, to_email, subj, body)
                            conn.execute(
                                "UPDATE scheduled_emails SET status='sent' WHERE id=?",
                                (rid,)
                            )
                            log.info(f"Scheduled email sent to {to_name}")
                        except Exception as e:
                            log.error(f"Scheduled send fail: {e}")
                            conn.execute(
                                "UPDATE scheduled_emails SET status='failed' WHERE id=?",
                                (rid,)
                            )
                    conn.commit(); conn.close()
                except Exception as e:
                    log.warning(f"Scheduler error: {e}")
                time.sleep(SCHEDULER_INTERVAL)
        threading.Thread(target=_loop, daemon=True).start()
        log.info("Email scheduler started ✅")

    # ══════════════════════════════════════════════════════════
    # 9. IMAP HELPER — connect
    # ══════════════════════════════════════════════════════════
    def _imap_connect(self, folder: str = "inbox"):
        mail = imaplib.IMAP4_SSL(IMAP_HOST)
        mail.login(self.address, self.password)
        mail.select(folder)
        return mail

    def _parse_msg(self, raw) -> dict:
        """Parse raw email bytes into dict."""
        msg = email.message_from_bytes(raw)
        sender  = msg.get("From", "")
        subject = msg.get("Subject", "No subject")
        date    = msg.get("Date", "")
        # Get plain text body
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    try:
                        body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                        break
                    except Exception:
                        pass
        else:
            try:
                body = msg.get_payload(decode=True).decode("utf-8", errors="ignore")
            except Exception:
                pass
        name = re.sub(r"<.+>", "", sender).strip().strip('"')
        return {"from": name, "from_raw": sender, "subject": subject,
                "body": body[:500], "date": date, "msg_obj": msg}

    # ══════════════════════════════════════════════════════════
    # 10. READ RECENT EMAILS (Feature 11)
    # ══════════════════════════════════════════════════════════
    def read_recent_emails(self, count: int = 5, folder: str = "inbox") -> str:
        if not self._ready: return self._nc()
        try:
            mail = self._imap_connect(folder)
            _, data = mail.search(None, "ALL")
            ids = data[0].split()
            recent = ids[-count:] if len(ids) >= count else ids
            results = []
            for uid in reversed(recent):
                _, msg_data = mail.fetch(uid, "(RFC822)")
                parsed = self._parse_msg(msg_data[0][1])
                results.append(f"From {parsed['from']}: {parsed['subject']}")
            mail.logout()
            if results:
                return (f"Last {len(results)} emails: " +
                        ". ".join(results[:5]))
            return "Your inbox is empty, sir."
        except imaplib.IMAP4.error:
            return "Gmail login failed — check App Password in .env"
        except Exception as e:
            log.error(f"read_recent error: {e}")
            return f"Couldn't read emails: {str(e)[:80]}"

    # ══════════════════════════════════════════════════════════
    # 11. CHECK UNREAD (Feature 12)
    # ══════════════════════════════════════════════════════════
    def check_unread(self, folder: str = "inbox") -> str:
        if not self._ready: return self._nc()
        try:
            mail = self._imap_connect(folder)
            _, data = mail.search(None, "UNSEEN")
            count = len(data[0].split()) if data[0] else 0
            mail.logout()
            if count == 0:
                return "No unread emails. Inbox all clear, sir! ✅"
            return f"You have {count} unread email{'s' if count > 1 else ''}, sir."
        except Exception as e:
            log.error(f"unread check error: {e}")
            return "Couldn't check unread emails."

    # ══════════════════════════════════════════════════════════
    # 12. SEARCH EMAILS (Feature 10)
    # ══════════════════════════════════════════════════════════
    def search_emails(self, query: str, folder: str = "inbox") -> str:
        """Search by sender name, subject keyword, or body keyword."""
        if not self._ready: return self._nc()
        try:
            mail = self._imap_connect(folder)
            # Try FROM search, then SUBJECT
            results = []
            for criteria in [f'FROM "{query}"', f'SUBJECT "{query}"']:
                _, data = mail.search(None, criteria)
                ids = data[0].split()
                for uid in reversed(ids[-5:]):
                    _, msg_data = mail.fetch(uid, "(RFC822)")
                    parsed = self._parse_msg(msg_data[0][1])
                    entry = f"From {parsed['from']}: {parsed['subject']}"
                    if entry not in results:
                        results.append(entry)
                if results:
                    break
            mail.logout()
            if results:
                return f"Found {len(results)} email(s): " + ". ".join(results[:5])
            return f"No emails found matching '{query}', sir."
        except Exception as e:
            log.error(f"search error: {e}")
            return f"Search failed: {str(e)[:80]}"

    # ══════════════════════════════════════════════════════════
    # 13. REPLY TO LAST EMAIL (Feature 7)
    # ══════════════════════════════════════════════════════════
    def reply_to_last(self, sender_filter: str, reply_body: str,
                      ai_compose: bool = False) -> str:
        """Fetch last email from sender and reply to it."""
        if not self._ready: return self._nc()
        try:
            mail = self._imap_connect()
            criteria = f'FROM "{sender_filter}"' if sender_filter else "ALL"
            _, data = mail.search(None, criteria)
            ids = data[0].split()
            if not ids:
                mail.logout()
                return f"No emails from '{sender_filter}' found."
            _, msg_data = mail.fetch(ids[-1], "(RFC822)")
            parsed = self._parse_msg(msg_data[0][1])
            mail.logout()
            self._last_received = parsed

            # AI compose reply
            if ai_compose and not reply_body:
                prompt = (
                    f"Write a brief, polite email reply to this message. "
                    f"Original: {parsed['body'][:200]}. "
                    f"Reply with ONLY the body text."
                )
                reply_body = _gemini_compose(prompt) or "Thank you for your email."

            to_raw   = parsed["from_raw"]
            subject  = "Re: " + parsed["subject"]
            # Extract sender email
            m = re.search(r"<(.+?)>", to_raw)
            to_email = m.group(1) if m else to_raw.strip()

            self._smtp_send(to_email, subject, reply_body)
            _log_sent(parsed["from"], to_email, subject, reply_body)
            return (f"Reply sent to {parsed['from']}, sir! "
                    f"Subject: {subject}")
        except Exception as e:
            log.error(f"reply error: {e}")
            return f"Couldn't reply: {str(e)[:80]}"

    # ══════════════════════════════════════════════════════════
    # 14. FORWARD EMAIL (Feature 8)
    # ══════════════════════════════════════════════════════════
    def forward_last(self, original_sender: str, to_name: str,
                     note: str = "") -> str:
        """Forward last email from original_sender to to_name."""
        if not self._ready: return self._nc()
        to_email = self._resolve(to_name)
        if not to_email:
            return f"I don't have {to_name}'s email."
        try:
            mail = self._imap_connect()
            criteria = f'FROM "{original_sender}"' if original_sender else "ALL"
            _, data = mail.search(None, criteria)
            ids = data[0].split()
            if not ids:
                mail.logout()
                return "No emails to forward."
            _, msg_data = mail.fetch(ids[-1], "(RFC822)")
            parsed = self._parse_msg(msg_data[0][1])
            mail.logout()

            fwd_body = (
                f"{note}\n\n--- Forwarded Message ---\n"
                f"From: {parsed['from']}\nSubject: {parsed['subject']}\n\n"
                f"{parsed['body']}"
            )
            subject = "Fwd: " + parsed["subject"]
            self._smtp_send(to_email, subject, fwd_body)
            _log_sent(to_name, to_email, subject, fwd_body)
            return f"Forwarded to {to_name}, sir!"
        except Exception as e:
            log.error(f"forward error: {e}")
            return f"Couldn't forward: {str(e)[:80]}"

    # ══════════════════════════════════════════════════════════
    # 15. DELETE EMAIL (Feature 9)
    # ══════════════════════════════════════════════════════════
    def delete_last_email(self, sender_filter: str = "") -> str:
        """Delete last matching email (moves to Trash)."""
        if not self._ready: return self._nc()
        try:
            mail = self._imap_connect()
            criteria = f'FROM "{sender_filter}"' if sender_filter else "ALL"
            _, data = mail.search(None, criteria)
            ids = data[0].split()
            if not ids:
                mail.logout()
                return "No emails to delete, sir."
            uid = ids[-1]
            mail.store(uid, "+FLAGS", "\\Deleted")
            mail.expunge()
            mail.logout()
            return f"Email deleted, sir."
        except Exception as e:
            log.error(f"delete error: {e}")
            return f"Couldn't delete: {str(e)[:80]}"

    # ══════════════════════════════════════════════════════════
    # 16. MARK AS READ / UNREAD (Feature 14)
    # ══════════════════════════════════════════════════════════
    def mark_all_read(self, folder: str = "inbox") -> str:
        if not self._ready: return self._nc()
        try:
            mail = self._imap_connect(folder)
            _, data = mail.search(None, "UNSEEN")
            ids = data[0].split()
            if ids:
                mail.store(",".join(i.decode() for i in ids), "+FLAGS", "\\Seen")
            mail.logout()
            return f"Marked {len(ids)} email(s) as read, sir."
        except Exception as e:
            return f"Couldn't mark read: {str(e)[:60]}"

    def mark_unread(self, count: int = 1, folder: str = "inbox") -> str:
        if not self._ready: return self._nc()
        try:
            mail = self._imap_connect(folder)
            _, data = mail.search(None, "SEEN")
            ids = data[0].split()
            to_mark = ids[-count:]
            if to_mark:
                mail.store(",".join(i.decode() for i in to_mark),
                           "-FLAGS", "\\Seen")
            mail.logout()
            return f"Marked {len(to_mark)} email(s) as unread, sir."
        except Exception as e:
            return f"Couldn't mark unread: {str(e)[:60]}"

    # ══════════════════════════════════════════════════════════
    # 17. MORNING EMAIL BRIEF — AI Summary (Feature 13)
    # ══════════════════════════════════════════════════════════
    def morning_brief(self) -> str:
        """Read unread count + top 5 senders + AI summary."""
        if not self._ready: return self._nc()
        try:
            mail = self._imap_connect()
            _, data = mail.search(None, "UNSEEN")
            ids = data[0].split()
            count = len(ids)
            senders = []
            for uid in ids[-5:]:
                _, msg_data = mail.fetch(uid, "(RFC822)")
                parsed = self._parse_msg(msg_data[0][1])
                senders.append(f"{parsed['from']}: {parsed['subject']}")
            mail.logout()
            if count == 0:
                return "Good morning, sir! Your inbox is all clear. No unread emails."
            brief = f"Good morning, sir! You have {count} unread email(s). "
            brief += "Top messages: " + ". ".join(senders[:3])
            # AI summary if Gemini available
            if senders:
                prompt = (
                    f"Summarise these email subjects in one sentence for a morning briefing: "
                    + "; ".join(senders)
                )
                summary = _gemini_compose(prompt)
                if summary:
                    brief += f". AI summary: {summary}"
            return brief
        except Exception as e:
            log.error(f"morning brief error: {e}")
            return f"Couldn't get email brief: {str(e)[:80]}"

    # ══════════════════════════════════════════════════════════
    # 18. EMAIL STATS (Feature 19)
    # ══════════════════════════════════════════════════════════
    def get_stats(self) -> str:
        """Show email analytics from SQLite log."""
        try:
            _init_db()
            conn = sqlite3.connect(_DB_PATH)
            total = conn.execute("SELECT COUNT(*) FROM sent_emails").fetchone()[0]
            today = conn.execute(
                "SELECT COUNT(*) FROM sent_emails WHERE sent_at >= date('now')"
            ).fetchone()[0]
            top = conn.execute(
                "SELECT recipient, COUNT(*) as cnt FROM sent_emails "
                "GROUP BY recipient ORDER BY cnt DESC LIMIT 3"
            ).fetchall()
            conn.close()
            top_str = ", ".join(f"{r[0]} ({r[1]})" for r in top) or "none"
            return (f"Email stats, sir: Total sent: {total}. "
                    f"Today: {today}. Most emailed: {top_str}.")
        except Exception as e:
            return f"Couldn't get stats: {str(e)[:60]}"

    # ══════════════════════════════════════════════════════════
    # 19. DAILY SUMMARY (Feature 20)
    # ══════════════════════════════════════════════════════════
    def daily_summary(self) -> str:
        """Summary of today's sent emails."""
        try:
            _init_db()
            conn = sqlite3.connect(_DB_PATH)
            rows = conn.execute(
                "SELECT recipient, subject, sent_at FROM sent_emails "
                "WHERE sent_at >= date('now') ORDER BY sent_at DESC LIMIT 10"
            ).fetchall()
            conn.close()
            if not rows:
                return "No emails sent today, sir."
            lines = []
            for r, s, t in rows:
                ts = datetime.fromisoformat(t).strftime("%I:%M %p")
                lines.append(f"'{s[:30]}' to {r} at {ts}")
            return "Today's email summary: " + ". ".join(lines[:5])
        except Exception as e:
            return f"Couldn't get summary: {str(e)[:60]}"

    # ══════════════════════════════════════════════════════════
    # 20. COMMAND PARSER
    # ══════════════════════════════════════════════════════════
    def parse_email_command(self, text: str) -> tuple:
        """
        Parse voice → (action, to_name, subject, body, extra).
        Returns (action_str, to, subject, body, tone/file/time)
        """
        t = text.lower().strip()

        # Detect tone
        tone = "friendly"
        for tk in ["formal", "casual", "apologetic", "professional"]:
            if tk in t:
                tone = tk
                t = t.replace(tk, "").strip()

        # Template triggers
        for tmpl in TEMPLATES:
            if tmpl in t:
                m = re.search(r"(?:to|email|mail)\s+(\w+)", t)
                to = m.group(1) if m else ""
                return ("template", to, tmpl, "", "")

        # Schedule: "schedule email to X ... at HH:MM"
        if "schedule" in t:
            m = re.search(r"(?:to\s+)?(\w+)\s+(.+?)\s+at\s+(.+)", t)
            if m:
                return ("schedule", m.group(1), "", m.group(2), m.group(3))

        # Reply: "reply to last email from X saying ..."
        m = re.search(r"reply.+?from\s+(\w+)\s+(?:saying\s+)?(.+)?", t)
        if m:
            return ("reply", m.group(1), "", m.group(2) or "", tone)

        # Forward: "forward last email to X"
        m = re.search(r"forward.+?to\s+(\w+)", t)
        if m:
            return ("forward", m.group(1), "", "", "")

        # Delete
        if "delete" in t:
            m = re.search(r"(?:from\s+)?(\w+)", t)
            to = m.group(1) if m else ""
            return ("delete", to, "", "", "")

        # Search
        if "search" in t:
            q = t.replace("search", "").replace("email", "").replace("emails", "").strip()
            return ("search", q, "", "", "")

        # Standard send: "email NAME saying ..."
        m = re.search(r"(?:email|mail|send email?)\s+(?:to\s+)?(\w+)\s+(?:saying|that|:|,)?\s*(.*)", t)
        if m:
            body = m.group(2).strip()
            if body:
                return ("ai_compose" if not body else "send", m.group(1), "", body, tone)

        return ("chat", "", "", text, "")


# ─── Quick test ───────────────────────────────────────────────
if __name__ == "__main__":
    handler = EmailHandler()
    print("Email ready:", handler._ready)
    if handler._ready:
        print(handler.check_unread())
        print(handler.get_stats())
    else:
        print("Set GMAIL_ADDRESS + GMAIL_APP_PASSWORD in .env first!")
