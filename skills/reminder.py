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
        self._load_recurring_reminders()
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

    def _load_recurring_reminders(self):
        """Reload all recurring reminders from DB to schedule."""
        try:
            with get_connection() as conn:
                rows = conn.execute("SELECT * FROM recurring_reminders").fetchall()
            # Clear only recurring jobs if any (prevent duplicates)
            for job in schedule.get_jobs():
                if "recurring" in job.tags:
                    schedule.cancel_job(job)
            for row in rows:
                self._register_recurring_job(row["id"], row["message"], row["frequency"], row["at_time"])
        except Exception as e:
            log.error(f"Error loading recurring reminders: {e}")

    def _register_recurring_job(self, db_id: int, message: str, frequency: str, at_time: str):
        freq = frequency.lower().strip()
        job_tag = f"recurring_{db_id}"
        def job_func():
            self._fire_reminder(message)
        
        if freq == "hourly":
            schedule.every().hour.tag(job_tag, "recurring").do(job_func)
        elif freq == "daily":
            schedule.every().day.at(at_time).tag(job_tag, "recurring").do(job_func)
        elif freq in ("weekly", "week"):
            schedule.every().week.tag(job_tag, "recurring").do(job_func)
        elif freq == "monday":
            schedule.every().monday.at(at_time).tag(job_tag, "recurring").do(job_func)
        elif freq == "morning":
            schedule.every().day.at("08:00").tag(job_tag, "recurring").do(job_func)
        elif freq == "evening":
            schedule.every().day.at("18:00").tag(job_tag, "recurring").do(job_func)

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

    def _format_time(self, dt_str: str) -> str:
        try:
            dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
            time_str = dt.strftime("%I:%M %p").lstrip("0")
            today = datetime.today().date()
            if dt.date() == today:
                return f"Today at {time_str}"
            elif dt.date() == today + timedelta(days=1):
                return f"Tomorrow at {time_str}"
            else:
                return f"{dt.strftime('%A')} at {time_str}"
        except Exception:
            return dt_str

    def _format_recurring_time(self, time_str: str) -> str:
        try:
            dt = datetime.strptime(time_str, "%H:%M")
            return dt.strftime("%I:%M %p").lstrip("0")
        except Exception:
            return time_str

    def list_reminders(self) -> str:
        """List all upcoming reminders (one-time and recurring)."""
        try:
            result = "Your upcoming reminders:\n\n"
            count = 0
            with get_connection() as conn:
                rows = conn.execute(
                    """SELECT id, message, remind_at FROM reminders WHERE is_done = 0
                       ORDER BY remind_at ASC LIMIT 10"""
                ).fetchall()
                if rows:
                    for row in rows:
                        time_str = self._format_time(row['remind_at'])
                        result += f"{row['message']}\n{time_str}\n\n"
                        count += 1
                
                rec_rows = conn.execute("SELECT id, message, frequency, at_time FROM recurring_reminders").fetchall()
                if rec_rows:
                    for r in rec_rows:
                        freq = r['frequency'].capitalize()
                        t_str = self._format_recurring_time(r['at_time'])
                        result += f"{r['message']}\nEvery {freq} at {t_str}\n\n"
                        count += 1
            
            if count == 0:
                return "You have no upcoming reminders."
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
        Set a recurring reminder.
        """
        try:
            with get_connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO recurring_reminders (message, frequency, at_time) VALUES (?, ?, ?)",
                    (message, frequency, at_time)
                )
                conn.commit()
                db_id = cur.lastrowid
            
            self._register_recurring_job(db_id, message, frequency, at_time)
            return f"Recurring reminder (ID: R-{db_id}) set: {frequency} at {at_time} for '{message}'"
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

    def delete_reminder(self, identifier: str) -> str:
        """Delete a reminder by ID or keyword."""
        try:
            with get_connection() as conn:
                identifier = identifier.strip().upper()
                # If prefixed with O- or R-
                if identifier.startswith("O-") and identifier[2:].isdigit():
                    rid = int(identifier[2:])
                    row_ot = conn.execute("SELECT id, message FROM reminders WHERE is_done = 0 AND id = ?", (rid,)).fetchone()
                    if row_ot:
                        conn.execute("DELETE FROM reminders WHERE id = ?", (rid,))
                        conn.commit()
                        return f"Deleted one-time reminder O-{rid}: '{row_ot['message']}'"
                    return f"No one-time reminder found with ID O-{rid}."
                
                if identifier.startswith("R-") and identifier[2:].isdigit():
                    rid = int(identifier[2:])
                    row_rec = conn.execute("SELECT id, message FROM recurring_reminders WHERE id = ?", (rid,)).fetchone()
                    if row_rec:
                        conn.execute("DELETE FROM recurring_reminders WHERE id = ?", (rid,))
                        conn.commit()
                        schedule.clear(f"recurring_{rid}")
                        return f"Deleted recurring reminder R-{rid}: '{row_rec['message']}'"
                    return f"No recurring reminder found with ID R-{rid}."
                
                # Try to parse as raw integer ID (if user says "delete reminder 2")
                if identifier.isdigit():
                    rid = int(identifier)
                    # Check both tables
                    row_ot = conn.execute("SELECT id, message FROM reminders WHERE is_done = 0 AND id = ?", (rid,)).fetchone()
                    row_rec = conn.execute("SELECT id, message FROM recurring_reminders WHERE id = ?", (rid,)).fetchone()
                    
                    if row_ot and row_rec:
                        return f"Found both a one-time and recurring reminder with ID {rid}. Please specify 'delete reminder O-{rid}' or 'R-{rid}'."
                    elif row_ot:
                        conn.execute("DELETE FROM reminders WHERE id = ?", (rid,))
                        conn.commit()
                        return f"Deleted one-time reminder ID {rid}: '{row_ot['message']}'"
                    elif row_rec:
                        conn.execute("DELETE FROM recurring_reminders WHERE id = ?", (rid,))
                        conn.commit()
                        schedule.clear(f"recurring_{rid}")
                        return f"Deleted recurring reminder ID {rid}: '{row_rec['message']}'"
                    else:
                        return f"No reminder found with ID {rid}."
                
                # Fallback to keyword
                identifier_lower = identifier.lower()
                rows_ot = conn.execute("SELECT id, message FROM reminders WHERE is_done = 0 AND message LIKE ?", (f"%{identifier_lower}%",)).fetchall()
                rows_rec = conn.execute("SELECT id, message FROM recurring_reminders WHERE message LIKE ?", (f"%{identifier_lower}%",)).fetchall()
                
                total = len(rows_ot) + len(rows_rec)
                if total == 0:
                    return f"No reminder found matching '{identifier_lower}'."
                if total > 1:
                    return f"Found {total} reminders matching '{identifier_lower}'. Please list reminders and delete by ID."
                
                if rows_ot:
                    rid = rows_ot[0]["id"]
                    conn.execute("DELETE FROM reminders WHERE id = ?", (rid,))
                    conn.commit()
                    return f"Deleted one-time reminder ID {rid} matching keyword."
                if rows_rec:
                    rid = rows_rec[0]["id"]
                    conn.execute("DELETE FROM recurring_reminders WHERE id = ?", (rid,))
                    conn.commit()
                    schedule.clear(f"recurring_{rid}")
                    return f"Deleted recurring reminder ID {rid} matching keyword."
                    
        except Exception as e:
            return f"Could not delete reminder: {str(e)[:60]}"

    def edit_reminder(self, reminder_id: str, new_time: str = None, new_frequency: str = None) -> str:
        """Edit an existing reminder's time or frequency."""
        try:
            with get_connection() as conn:
                identifier = str(reminder_id).strip().upper()
                target_ot = None
                target_rec = None
                
                if identifier.startswith("O-") and identifier[2:].isdigit():
                    target_ot = int(identifier[2:])
                elif identifier.startswith("R-") and identifier[2:].isdigit():
                    target_rec = int(identifier[2:])
                elif identifier.isdigit():
                    rid = int(identifier)
                    row_ot = conn.execute("SELECT id FROM reminders WHERE is_done = 0 AND id = ?", (rid,)).fetchone()
                    row_rec = conn.execute("SELECT id FROM recurring_reminders WHERE id = ?", (rid,)).fetchone()
                    if row_ot and row_rec:
                        return f"Found both one-time and recurring with ID {rid}. Specify O-{rid} or R-{rid}."
                    if row_ot: target_ot = rid
                    if row_rec: target_rec = rid

                if target_ot is not None:
                    if new_time:
                        today = datetime.now().strftime("%Y-%m-%d")
                        remind_at = datetime.strptime(f"{today} {new_time}", "%Y-%m-%d %H:%M")
                        if remind_at < datetime.now(): remind_at += timedelta(days=1)
                        conn.execute("UPDATE reminders SET remind_at = ? WHERE id = ?", (remind_at.strftime("%Y-%m-%d %H:%M:%S"), target_ot))
                        conn.commit()
                        return f"One-time reminder {target_ot} updated to {remind_at.strftime('%I:%M %p')}."
                    return "No valid edit parameters provided for one-time reminder."
                
                if target_rec is not None:
                    row_rec = conn.execute("SELECT * FROM recurring_reminders WHERE id = ?", (target_rec,)).fetchone()
                    if not row_rec: return f"No recurring reminder found with ID {target_rec}."
                    freq = new_frequency or row_rec["frequency"]
                    at_time = new_time or row_rec["at_time"]
                    conn.execute("UPDATE recurring_reminders SET frequency = ?, at_time = ? WHERE id = ?", (freq, at_time, target_rec))
                    conn.commit()
                    schedule.clear(f"recurring_{target_rec}")
                    self._register_recurring_job(target_rec, row_rec["message"], freq, at_time)
                    return f"Recurring reminder {target_rec} updated to {freq} at {at_time}."
                
                return f"No reminder found with ID {identifier}."
        except Exception as e:
            return f"Could not edit reminder: {str(e)[:60]}"

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
