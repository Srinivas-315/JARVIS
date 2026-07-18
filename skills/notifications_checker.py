"""
JARVIS — skills/notifications_checker.py
Checks unread messages from Gmail, WhatsApp (window badge),
and Windows notification center.

Trigger: "any unread messages", "check messages", "what did I miss"
"""

import os
import imaplib
import email
import subprocess
import re
import time
from email.header import decode_header
from utils.logger import log
from dotenv import load_dotenv

load_dotenv()


class NotificationsChecker:
    """
    Checks unread messages across:
      1. Gmail (IMAP — reads subject + sender)
      2. WhatsApp Desktop (window title badge count)
      3. Windows Notification Center (via PowerShell)
    """

    def __init__(self):
        self._gmail_addr = os.getenv("GMAIL_ADDRESS", "")
        self._gmail_pass = os.getenv("GMAIL_APP_PASSWORD", "")

    # ═══════════════════════════════════════════════════════════
    #  Main entry — call this from voice command
    # ═══════════════════════════════════════════════════════════

    def check_all(self) -> str:
        """
        Check all sources and return a spoken summary.
        Called when user says 'any unread messages' or 'what did I miss'.
        """
        parts = []

        # 1. Gmail
        try:
            gmail_result = self._check_gmail()
            if gmail_result:
                parts.append(gmail_result)
        except Exception as e:
            log.error(f"Gmail checker raised an unexpected error: {e}")

        # 2. WhatsApp
        try:
            wa_result = self._check_whatsapp_badge()
            if wa_result:
                parts.append(wa_result)
        except Exception as e:
            log.error(f"WhatsApp checker raised an unexpected error: {e}")

        # 3. Windows notifications
        try:
            notif_result = self._check_windows_notifications()
            if notif_result:
                parts.append(notif_result)
        except Exception as e:
            log.error(f"Windows notifications checker raised an unexpected error: {e}")

        if not parts:
            return "All clear, sir. No unread messages anywhere."

        return "Here's what you missed. " + " Also, ".join(parts)

    def check_all_structured(self) -> list:
        """
        Check all sources and return structured data (list of dicts).
        Usable by notification_watcher or other modules that need raw data.

        Returns:
            List of dicts with keys: source, count, details, raw_text
        """
        results = []

        # 1. Gmail
        try:
            gmail_text = self._check_gmail()
            if gmail_text:
                results.append({
                    "source": "gmail",
                    "raw_text": gmail_text,
                })
        except Exception as e:
            log.error(f"Gmail checker raised an unexpected error: {e}")

        # 2. WhatsApp
        try:
            wa_text = self._check_whatsapp_badge()
            if wa_text:
                results.append({
                    "source": "whatsapp",
                    "raw_text": wa_text,
                })
        except Exception as e:
            log.error(f"WhatsApp checker raised an unexpected error: {e}")

        # 3. Windows notifications
        try:
            notif_text = self._check_windows_notifications()
            if notif_text:
                results.append({
                    "source": "windows",
                    "raw_text": notif_text,
                })
        except Exception as e:
            log.error(f"Windows notifications checker raised an unexpected error: {e}")

        return results

    def check_gmail_only(self) -> str:
        """Check only Gmail."""
        return self._check_gmail() or "No unread emails, sir."

    def check_whatsapp_only(self) -> str:
        """Check only WhatsApp Desktop app."""
        result = self._check_whatsapp_badge()
        if result:
            return result
        return (
            "WhatsApp Desktop isn't open, sir. "
            "Please open it so I can check your messages."
        )


    # ═══════════════════════════════════════════════════════════
    #  Gmail via IMAP
    # ═══════════════════════════════════════════════════════════

    def _check_gmail(self) -> str:
        """
        Connect to Gmail via IMAP and get unread message summary.
        Returns spoken string or empty string on failure.
        """
        if not self._gmail_addr or not self._gmail_pass:
            log.warning("Gmail credentials not set in .env")
            return ""

        try:
            mail = imaplib.IMAP4_SSL("imap.gmail.com", timeout=8)
            mail.login(self._gmail_addr, self._gmail_pass.replace(" ", ""))
            mail.select("inbox")

            # Get unread message IDs
            _, data = mail.search(None, "UNSEEN")
            unread_ids = data[0].split()
            count = len(unread_ids)

            if count == 0:
                mail.logout()
                return ""

            # Read latest 3 unread emails for context
            senders  = []
            subjects = []
            latest   = unread_ids[-3:]  # Last 3

            for uid in reversed(latest):
                try:
                    _, msg_data = mail.fetch(uid, "(RFC822.HEADER)")
                    raw = msg_data[0][1]
                    msg = email.message_from_bytes(raw)

                    # Decode sender
                    sender = self._decode_header_value(msg.get("From", "Unknown"))
                    sender = re.sub(r"<.*?>", "", sender).strip().strip('"')

                    # Decode subject
                    subject = self._decode_header_value(msg.get("Subject", "No subject"))

                    senders.append(sender)
                    subjects.append(subject)
                except Exception:
                    pass

            mail.logout()

            # Build spoken summary
            if count == 1:
                reply = f"You have 1 unread email"
                if senders:
                    reply += f" from {senders[0]}"
                if subjects:
                    reply += f", about '{subjects[0]}'"
                reply += "."
            else:
                reply = f"You have {count} unread emails."
                if senders:
                    recent = ", ".join(senders[:3])
                    reply += f" Most recent from {recent}."

            log.info(f"Gmail: {count} unread")
            return reply

        except imaplib.IMAP4.error as e:
            log.warning(f"Gmail IMAP auth error: {e}")
            return ""
        except Exception as e:
            log.warning(f"Gmail check failed: {e}")
            return ""

    def _decode_header_value(self, value: str) -> str:
        """Decode email header (handles UTF-8, base64 encoding)."""
        try:
            parts = decode_header(value)
            decoded = ""
            for part, charset in parts:
                if isinstance(part, bytes):
                    decoded += part.decode(charset or "utf-8", errors="ignore")
                else:
                    decoded += str(part)
            return decoded.strip()
        except Exception:
            return str(value)

    # ═══════════════════════════════════════════════════════════
    #  WhatsApp badge via window title
    # ═══════════════════════════════════════════════════════════

    def _check_whatsapp_badge(self) -> str:
        """
        WhatsApp Desktop app unread detection.
        Uses the Windows Notification Database (via WhatsAppSkill).
        """
        try:
            try:
                from skills.whatsapp import WhatsAppSkill
            except ImportError:
                from whatsapp import WhatsAppSkill
            wa = WhatsAppSkill()
            result = wa.get_unread_count()
            if "No unread" in result or "Could not find" in result or "Error" in result:
                return ""
            return result
        except Exception as e:
            log.warning(f"WA DB check failed: {e}")
            return ""




    # ═══════════════════════════════════════════════════════════
    #  Windows Notification Center
    # ═══════════════════════════════════════════════════════════

    def _check_windows_notifications(self) -> str:
        """
        Read Windows notification database to find unread notifications
        from apps like Teams, Outlook, Slack, etc.
        """
        try:
            # PowerShell reads from Windows notification SQLite DB
            ps_script = r"""
$db = "$env:LOCALAPPDATA\Microsoft\Windows\Notifications\wpndatabase.db"
if (Test-Path $db) {
    Add-Type -Path "C:\Windows\System32\System.Data.SQLite.dll" -ErrorAction SilentlyContinue
    # Fallback: use notification COM API
}
# Simpler: just get toast notification count from ActionCenter
[Windows.UI.Notifications.ToastNotificationManager,Windows.UI.Notifications,ContentType=WindowsRuntime] | Out-Null
$listeners = [Windows.UI.Notifications.ToastNotificationManager]::History.GetHistory()
$listeners | Select-Object -ExpandProperty Content | ForEach-Object { $_.OuterXml } | Measure-Object | Select-Object -ExpandProperty Count
"""
            result = subprocess.run(
                ["powershell", "-Command", ps_script],
                capture_output=True, text=True, timeout=5
            )
            count_str = result.stdout.strip()
            if count_str.isdigit():
                count = int(count_str)
                if count > 0:
                    return f"{count} notifications in the Windows notification center."
            return ""
        except Exception:
            return ""


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    checker = NotificationsChecker()
    print("Checking all notifications...")
    result = checker.check_all()
    print(f"\n🤖 JARVIS: {result}")
