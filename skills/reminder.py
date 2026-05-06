"""
JARVIS — skills/reminder.py
Set reminders, timers and alarms with desktop notifications.
"""

import threading
import time
from datetime import datetime, timedelta
from typing import Optional

import schedule
from plyer import notification

from memory.database import get_connection
from utils.logger import log


class ReminderSkill:
    """Handles reminders, timers, and alarms."""

    def __init__(self, speak_callback=None):
        """
        speak_callback → function to call when reminder fires (speaks out loud)
        """
        self._speak = speak_callback
        self._scheduler_thread = None
        self._running = False

    def start_scheduler(self):
        """Start the background reminder scheduler."""
        self._running = True
        self._scheduler_thread = threading.Thread(
            target=self._run_scheduler, daemon=True
        )
        self._scheduler_thread.start()
        log.info("Reminder scheduler started ✅")

    def stop_scheduler(self):
        """Stop the background reminder scheduler."""
        self._running = False
        if self._scheduler_thread and self._scheduler_thread.is_alive():
            self._scheduler_thread.join(timeout=2)
        log.info("Reminder scheduler stopped.")

    def clear_all(self):
        """Cancel all pending schedule jobs (used on stop/cancel commands)."""
        schedule.clear()
        log.info("All pending schedule jobs cleared.")

    def _run_scheduler(self):
        """Background loop that checks reminders every 30 seconds."""
        while self._running:
            self._check_db_reminders()
            schedule.run_pending()
            time.sleep(30)

    def _check_db_reminders(self):
        """Check SQLite for due reminders."""
        try:
            with get_connection() as conn:
                rows = conn.execute(
                    """SELECT * FROM reminders
                       WHERE is_done = 0
                       AND remind_at <= datetime('now', 'localtime')"""
                ).fetchall()

                for row in rows:
                    self._fire_reminder(row["message"])
                    conn.execute(
                        "UPDATE reminders SET is_done = 1 WHERE id = ?", (row["id"],)
                    )
                conn.commit()
        except Exception as e:
            log.error(f"Reminder check error: {e}")

    def _fire_reminder(self, message: str):
        """Fire a reminder: desktop notification + voice."""
        log.info(f"🔔 Reminder firing: {message}")

        # Desktop notification
        try:
            notification.notify(
                title="⏰ JARVIS Reminder",
                message=message,
                timeout=10,
                app_name="JARVIS",
            )
        except Exception as e:
            log.error(f"Notification error: {e}")

        # Speak the reminder
        if self._speak:
            self._speak(f"Reminder! {message}")

    def set_timer(self, seconds: int, message: str = "Timer complete!") -> str:
        """Set a countdown timer."""

        def timer_callback():
            self._fire_reminder(message)

        timer = threading.Timer(seconds, timer_callback)
        timer.daemon = True
        timer.start()

        if seconds >= 60:
            mins = seconds // 60
            secs = seconds % 60
            duration = f"{mins} minute{'s' if mins > 1 else ''}"
            if secs:
                duration += f" and {secs} seconds"
        else:
            duration = f"{seconds} second{'s' if seconds > 1 else ''}"

        log.info(f"Timer set for {duration}")
        return f"Timer set for {duration}. I'll remind you!"

    def set_reminder(
        self, message: str, minutes: Optional[int] = None, at_time: Optional[str] = None
    ) -> str:
        """
        Set a reminder.
        minutes → relative (e.g., 30 minutes from now)
        at_time → absolute time string e.g., "18:30"
        """
        try:
            if minutes:
                remind_at = datetime.now() + timedelta(minutes=minutes)
            elif at_time:
                today = datetime.now().strftime("%Y-%m-%d")
                remind_at = datetime.strptime(f"{today} {at_time}", "%Y-%m-%d %H:%M")
            else:
                return "Please specify when to remind you."

            # If reminder time is in the past today, schedule for tomorrow
            if remind_at < datetime.now():
                remind_at += timedelta(days=1)

            with get_connection() as conn:
                conn.execute(
                    "INSERT INTO reminders (message, remind_at) VALUES (?, ?)",
                    (message, remind_at.strftime("%Y-%m-%d %H:%M:%S")),
                )
                conn.commit()

            time_str = remind_at.strftime("%I:%M %p")
            log.info(f"Reminder set: '{message}' at {time_str}")
            return f"Reminder set for {time_str}: {message}"

        except Exception as e:
            log.error(f"Set reminder error: {e}")
            return "Couldn't set that reminder. Try again."

    def list_reminders(self) -> str:
        """List all upcoming reminders."""
        try:
            with get_connection() as conn:
                rows = conn.execute(
                    """SELECT * FROM reminders WHERE is_done = 0
                       ORDER BY remind_at ASC LIMIT 10"""
                ).fetchall()

            if not rows:
                return "You have no upcoming reminders."

            result = "Your upcoming reminders:\n"
            for row in rows:
                dt = row["remind_at"]
                result += f"• {dt}: {row['message']}\n"
            return result.strip()

        except Exception as e:
            return "Couldn't fetch reminders."

    def parse_time_from_text(self, text: str) -> tuple:
        """
        Extract time info from natural language.
        Returns (minutes, at_time, message)
        """
        text_lower = text.lower()
        minutes = None
        at_time = None
        message = text

        # "in X minutes"
        import re

        m = re.search(r"in (\d+) minute", text_lower)
        if m:
            minutes = int(m.group(1))
            message = re.sub(r"in \d+ minutes?", "", text, flags=re.IGNORECASE).strip()

        # "in X hours"
        m = re.search(r"in (\d+) hour", text_lower)
        if m:
            minutes = int(m.group(1)) * 60
            message = re.sub(r"in \d+ hours?", "", text, flags=re.IGNORECASE).strip()

        # "at HH:MM" or "at X pm/am"
        m = re.search(r"at (\d{1,2}):(\d{2})", text_lower)
        if m:
            at_time = f"{m.group(1)}:{m.group(2)}"
            message = re.sub(r"at \d{1,2}:\d{2}", "", text, flags=re.IGNORECASE).strip()

        # Clean "remind me to" prefix
        for prefix in [
            "remind me to ",
            "remind me ",
            "set reminder to ",
            "set alarm to ",
        ]:
            if prefix in message.lower():
                message = message.lower().split(prefix, 1)[-1].strip()
                break

        return minutes, at_time, message

    def set_recurring_reminder(
        self, message: str, frequency: str = "daily", at_time: str = "09:00"
    ) -> str:
        """
        Set a recurring reminder: daily, weekly, or hourly.
        Say: 'remind me every day at 9 AM to drink water'
             'weekly reminder on Monday at 10 AM meeting'
        """
        try:
            freq = frequency.lower().strip()
            if freq == "hourly":
                schedule.every().hour.do(lambda: self._fire_reminder(message))
                return f"Hourly reminder set: '{message}', sir."
            elif freq == "daily":
                schedule.every().day.at(at_time).do(
                    lambda: self._fire_reminder(message)
                )
                return f"Daily reminder set at {at_time}: '{message}', sir."
            elif freq in ("weekly", "week"):
                schedule.every().week.do(lambda: self._fire_reminder(message))
                return f"Weekly reminder set: '{message}', sir."
            elif freq == "monday":
                schedule.every().monday.at(at_time).do(
                    lambda: self._fire_reminder(message)
                )
                return f"Every Monday at {at_time}: '{message}', sir."
            elif freq == "morning":
                schedule.every().day.at("08:00").do(
                    lambda: self._fire_reminder(message)
                )
                return f"Morning reminder set at 8:00 AM: '{message}', sir."
            elif freq == "evening":
                schedule.every().day.at("18:00").do(
                    lambda: self._fire_reminder(message)
                )
                return f"Evening reminder set at 6:00 PM: '{message}', sir."
            else:
                return f"Frequency '{frequency}' not recognized. Try: daily, weekly, hourly, morning, evening."
        except Exception as e:
            log.error(f"Recurring reminder error: {e}")
            return f"Could not set recurring reminder: {str(e)[:60]}"

    def snooze_reminder(self, minutes: int = 10) -> str:
        """Snooze the last reminder by N minutes."""
        try:
            # Get last fired reminder from DB
            with get_connection() as conn:
                row = conn.execute(
                    "SELECT id, message FROM reminders WHERE is_done = 1 ORDER BY remind_at DESC LIMIT 1"
                ).fetchone()
            if not row:
                return "No recent reminder to snooze, sir."
            # Re-schedule it
            self.set_reminder(row["message"], minutes=minutes)
            return f"Reminder snoozed for {minutes} minutes, sir."
        except Exception as e:
            return f"Snooze failed: {str(e)[:60]}"

    def delete_reminder(self, keyword: str) -> str:
        """Delete a reminder containing a keyword."""
        try:
            with get_connection() as conn:
                rows = conn.execute(
                    "SELECT id, message FROM reminders WHERE is_done = 0 AND message LIKE ?",
                    (f"%{keyword}%",),
                ).fetchall()
                if not rows:
                    return f"No pending reminder found matching '{keyword}', sir."
                for row in rows:
                    conn.execute("DELETE FROM reminders WHERE id = ?", (row["id"],))
                conn.commit()
            return f"Deleted {len(rows)} reminder(s) matching '{keyword}', sir."
        except Exception as e:
            return f"Could not delete reminder: {str(e)[:60]}"

    def get_timer_status(self) -> str:
        """Check if any timers are running."""
        import threading

        active = [t for t in threading.enumerate() if "Timer" in type(t).__name__]
        if active:
            return f"{len(active)} timer(s) currently running, sir."
        return "No active timers, sir."


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":

    def mock_speak(text):
        print(f"[SPEAK] {text}")

    r = ReminderSkill(speak_callback=mock_speak)
    r.start_scheduler()
    print(r.set_timer(5, "Test timer done!"))
    print("Waiting 6 seconds...")
    time.sleep(6)
