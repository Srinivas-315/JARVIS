"""
JARVIS — skills/calendar_skill.py
Smart Calendar — add, view, and manage events by voice.

Fully LOCAL — no Google account needed.
Events saved to: JARVIS/data/calendar.json

Voice commands:
  "Add meeting tomorrow at 3pm"
  "Add exam on Monday at 9am called Data Structures"
  "What's my schedule today?"
  "What's happening this week?"
  "Do I have anything tomorrow?"
  "What's my next event?"
  "Cancel my 3pm meeting"
  "Show all events"
"""

import json
import os
import re
from datetime import datetime, date, timedelta
from utils.logger import log

# Storage
DATA_DIR      = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
CALENDAR_FILE = os.path.join(DATA_DIR, "calendar.json")

# Days of week
DAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
    "mon": 0, "tue": 1, "wed": 2, "thu": 3,
    "fri": 4, "sat": 5, "sun": 6,
}

# Month names
MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


class CalendarSkill:
    """Voice-controlled local calendar — add, view, manage events."""

    def __init__(self):
        self._events = []
        self._load()
        log.info(f"Calendar ready ✅ ({len(self._events)} events loaded)")

    # ═══════════════════════════════════════════════════════════
    # ADD EVENTS
    # ═══════════════════════════════════════════════════════════

    def add_event(self, text: str) -> str:
        """
        Parse and add an event from natural language.
        Examples:
          "meeting tomorrow at 3pm"
          "exam on Monday at 9am called Data Structures"
          "dentist appointment on April 20th at 2pm"
          "birthday party on 25th April"
        """
        text_lower = text.lower().strip()

        # Remove trigger words
        for remove in ["add event", "add a", "schedule a", "schedule",
                       "create event", "put", "set up", "book", "add"]:
            text_lower = text_lower.replace(remove, "", 1).strip()

        # Parse date and time
        event_date = self._parse_date(text_lower)
        event_time = self._parse_time(text_lower)
        event_name = self._parse_event_name(text_lower)

        if not event_date:
            return ("I need a date. Say something like: "
                    "'Add meeting tomorrow at 3pm' or 'Add exam on Monday'")

        if not event_name:
            event_name = "Event"

        # Build event
        event = {
            "id":   self._new_id(),
            "name": event_name,
            "date": event_date.strftime("%Y-%m-%d"),
            "time": event_time or "",
            "created": datetime.now().isoformat(),
        }

        self._events.append(event)
        self._save()

        # Format response
        date_str = self._friendly_date(event_date)
        time_str = f" at {event_time}" if event_time else ""
        log.info(f"Event added: {event_name} on {event['date']} {event_time}")
        return f"Done! '{event_name}' added for {date_str}{time_str}."

    # ═══════════════════════════════════════════════════════════
    # VIEW EVENTS
    # ═══════════════════════════════════════════════════════════

    def get_today(self) -> str:
        """What's on today's schedule?"""
        today = date.today()
        events = self._events_on(today)

        if not events:
            return "Nothing scheduled for today. Enjoy your free day!"

        parts = [f"Today you have {len(events)} event(s):"]
        for e in events:
            time_str = f" at {e['time']}" if e["time"] else ""
            parts.append(f"  • {e['name']}{time_str}")
        return "\n".join(parts)

    def get_tomorrow(self) -> str:
        """What's happening tomorrow?"""
        tomorrow = date.today() + timedelta(days=1)
        events = self._events_on(tomorrow)

        if not events:
            return "Nothing scheduled for tomorrow."

        parts = [f"Tomorrow you have {len(events)} event(s):"]
        for e in events:
            time_str = f" at {e['time']}" if e["time"] else ""
            parts.append(f"  • {e['name']}{time_str}")
        return "\n".join(parts)

    def get_this_week(self) -> str:
        """What's happening this week?"""
        today = date.today()
        week_end = today + timedelta(days=7)

        events = [e for e in self._events
                  if today <= self._parse_stored_date(e["date"]) <= week_end]
        events.sort(key=lambda e: (e["date"], e["time"]))

        if not events:
            return "Nothing scheduled for this week."

        parts = [f"This week you have {len(events)} event(s):"]
        for e in events:
            d = self._parse_stored_date(e["date"])
            day_name = d.strftime("%A")
            time_str = f" at {e['time']}" if e["time"] else ""
            parts.append(f"  • {day_name}: {e['name']}{time_str}")
        return "\n".join(parts)

    def get_next_event(self) -> str:
        """What's the next upcoming event?"""
        today = date.today()
        now_str = datetime.now().strftime("%H:%M")

        upcoming = []
        for e in self._events:
            d = self._parse_stored_date(e["date"])
            if d > today:
                upcoming.append(e)
            elif d == today and e["time"] > now_str:
                upcoming.append(e)

        if not upcoming:
            return "No upcoming events in your calendar."

        upcoming.sort(key=lambda e: (e["date"], e["time"]))
        next_e = upcoming[0]
        d = self._parse_stored_date(next_e["date"])
        date_str = self._friendly_date(d)
        time_str = f" at {next_e['time']}" if next_e["time"] else ""
        return f"Your next event is '{next_e['name']}' on {date_str}{time_str}."

    def get_schedule_for_day(self, text: str) -> str:
        """Get schedule for a specific day mentioned in text."""
        text_lower = text.lower()
        target_date = self._parse_date(text_lower)

        if not target_date:
            return "Which day? Say like 'schedule for Monday' or 'schedule for April 20th'."

        events = self._events_on(target_date)
        date_str = self._friendly_date(target_date)

        if not events:
            return f"Nothing scheduled for {date_str}."

        parts = [f"On {date_str} you have:"]
        for e in events:
            time_str = f" at {e['time']}" if e["time"] else ""
            parts.append(f"  • {e['name']}{time_str}")
        return "\n".join(parts)

    def list_all_events(self) -> str:
        """List all upcoming events."""
        today = date.today()
        upcoming = [e for e in self._events
                    if self._parse_stored_date(e["date"]) >= today]
        upcoming.sort(key=lambda e: (e["date"], e["time"]))

        if not upcoming:
            return "Your calendar is empty."

        parts = [f"You have {len(upcoming)} upcoming event(s):"]
        for e in upcoming[:10]:  # Max 10
            d = self._parse_stored_date(e["date"])
            date_str = self._friendly_date(d)
            time_str = f" at {e['time']}" if e["time"] else ""
            parts.append(f"  • {date_str}: {e['name']}{time_str}")
        return "\n".join(parts)

    # ═══════════════════════════════════════════════════════════
    # DELETE EVENTS
    # ═══════════════════════════════════════════════════════════

    def cancel_event(self, text: str) -> str:
        """Cancel/delete an event by name or time."""
        text_lower = text.lower()
        for remove in ["cancel", "delete", "remove", "my"]:
            text_lower = text_lower.replace(remove, "").strip()

        # Try to match by name
        search = text_lower.strip()
        removed = []

        for event in self._events[:]:
            if (search in event["name"].lower() or
                    event["time"] == self._parse_time(text_lower)):
                removed.append(event)
                self._events.remove(event)

        if removed:
            self._save()
            names = ", ".join(e["name"] for e in removed)
            return f"Removed: {names}."
        else:
            return f"Couldn't find an event matching '{search}'. Say 'show all events' to see your schedule."

    # ═══════════════════════════════════════════════════════════
    # DATE / TIME PARSERS
    # ═══════════════════════════════════════════════════════════

    def _parse_date(self, text: str) -> date | None:
        """Parse date from natural language text."""
        today = date.today()
        t = text.lower()

        # Relative dates
        if "today" in t:
            return today
        if "tomorrow" in t:
            return today + timedelta(days=1)
        if "day after tomorrow" in t:
            return today + timedelta(days=2)
        if "next week" in t:
            return today + timedelta(days=7)

        # "this monday" / "next friday" / "on monday"
        for day_name, day_num in DAYS.items():
            patterns = [f"this {day_name}", f"next {day_name}",
                       f"on {day_name}", f" {day_name} "]
            for pat in patterns:
                if pat in t or t.startswith(day_name):
                    today_num = today.weekday()
                    days_ahead = (day_num - today_num) % 7
                    if days_ahead == 0:
                        days_ahead = 7  # Next week's same day
                    return today + timedelta(days=days_ahead)

        # "on April 20" / "April 20th" / "20th April"
        # Pattern: month day
        for month_name, month_num in MONTHS.items():
            # "April 20" or "April 20th"
            m = re.search(rf"{month_name}\s+(\d{{1,2}})(st|nd|rd|th)?", t)
            if m:
                day = int(m.group(1))
                year = today.year
                try:
                    d = date(year, month_num, day)
                    if d < today:
                        d = date(year + 1, month_num, day)
                    return d
                except ValueError:
                    pass

            # "20th April"
            m = re.search(rf"(\d{{1,2}})(st|nd|rd|th)?\s+{month_name}", t)
            if m:
                day = int(m.group(1))
                year = today.year
                try:
                    d = date(year, month_num, day)
                    if d < today:
                        d = date(year + 1, month_num, day)
                    return d
                except ValueError:
                    pass

        # "on the 25th" / "on 25th"
        m = re.search(r"on (?:the )?(\d{1,2})(?:st|nd|rd|th)?", t)
        if m:
            day = int(m.group(1))
            year = today.year
            month = today.month
            try:
                d = date(year, month, day)
                if d < today:
                    month += 1
                    if month > 12:
                        month = 1
                        year += 1
                    d = date(year, month, day)
                return d
            except ValueError:
                pass

        # "in 3 days" / "in 2 weeks"
        m = re.search(r"in (\d+)\s*(day|week|month)", t)
        if m:
            n = int(m.group(1))
            unit = m.group(2)
            if "day" in unit:
                return today + timedelta(days=n)
            elif "week" in unit:
                return today + timedelta(weeks=n)
            elif "month" in unit:
                return today + timedelta(days=n * 30)

        return None

    def _parse_time(self, text: str) -> str:
        """Parse time from natural language. Returns HH:MM string."""
        t = text.lower()

        # "3pm", "3:30pm", "15:30", "3 pm", "at 3"
        # 12-hour with am/pm
        m = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)", t)
        if m:
            hour = int(m.group(1))
            minute = int(m.group(2)) if m.group(2) else 0
            period = m.group(3)
            if period == "pm" and hour != 12:
                hour += 12
            elif period == "am" and hour == 12:
                hour = 0
            return f"{hour:02d}:{minute:02d}"

        # 24-hour "at 15:30" or "14:00"
        m = re.search(r"\b(\d{1,2}):(\d{2})\b", t)
        if m:
            hour = int(m.group(1))
            minute = int(m.group(2))
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                return f"{hour:02d}:{minute:02d}"

        # "at noon" / "at midnight"
        if "noon" in t or "12 pm" in t:
            return "12:00"
        if "midnight" in t:
            return "00:00"
        if "morning" in t:
            return "09:00"
        if "afternoon" in t:
            return "14:00"
        if "evening" in t:
            return "18:00"
        if "night" in t:
            return "20:00"

        return ""

    def _parse_event_name(self, text: str) -> str:
        """Extract the event name from text."""
        t = text.lower()

        # "called X" or "named X" — explicit name
        m = re.search(r"(?:called|named)\s+(.+?)(?:\s+(?:at|on|tomorrow|today)|$)", t)
        if m:
            return m.group(1).strip().title()

        # Remove date/time words to get event name
        clean = t
        for remove in [
            "add event", "add a", "add an", "schedule a", "schedule an",
            "create event", "set up", "put a", "book a",
            "tomorrow", "today", "tonight", "this morning",
            "next monday", "next tuesday", "next wednesday", "next thursday",
            "next friday", "next saturday", "next sunday",
            "on monday", "on tuesday", "on wednesday", "on thursday",
            "on friday", "on saturday", "on sunday",
            "this monday", "this tuesday", "this wednesday",
            "in the morning", "in the afternoon", "in the evening",
            "at noon", "at midnight", "at morning", "at night",
        ]:
            clean = clean.replace(remove, "").strip()

        # Remove time patterns
        clean = re.sub(r"\b\d{1,2}(?::\d{2})?\s*(?:am|pm)\b", "", clean)
        clean = re.sub(r"\bat\s+\d{1,2}(?::\d{2})?", "", clean)
        clean = re.sub(r"\bon\s+(?:the\s+)?\d{1,2}(?:st|nd|rd|th)?", "", clean)
        clean = re.sub(r"\bon\s+\w+\s+\d{1,2}", "", clean)

        # Remove month names (they're part of date, not event name)
        for month in ["january","february","march","april","may","june","july",
                      "august","september","october","november","december",
                      "jan","feb","mar","apr","jun","jul","aug","sep","oct","nov","dec"]:
            clean = re.sub(rf"\b{month}\b", "", clean)

        # Remove stray ordinal suffixes and standalone 'at'
        clean = re.sub(r"\b(?:st|nd|rd|th|at)\b", "", clean)

        # Remove leftover prepositions
        clean = re.sub(r"^\s*(?:a|an|the|my)\s+", "", clean).strip()
        clean = re.sub(r"\s+", " ", clean).strip()

        if clean and len(clean) > 1:
            return clean.title()
        return "Event"


    # ═══════════════════════════════════════════════════════════
    # HELPERS
    # ═══════════════════════════════════════════════════════════

    def _events_on(self, target: date) -> list:
        """Get events on a specific date, sorted by time."""
        date_str = target.strftime("%Y-%m-%d")
        events = [e for e in self._events if e["date"] == date_str]
        events.sort(key=lambda e: e["time"])
        return events

    def _friendly_date(self, d: date) -> str:
        """Convert date to friendly string: 'Today', 'Tomorrow', 'Monday April 20'."""
        today = date.today()
        if d == today:
            return "today"
        elif d == today + timedelta(days=1):
            return "tomorrow"
        elif d == today + timedelta(days=2):
            return "day after tomorrow"
        elif (d - today).days <= 7:
            return d.strftime("%A")  # "Monday"
        else:
            return d.strftime("%A, %B %d")  # "Monday, April 20"

    def _parse_stored_date(self, date_str: str) -> date:
        """Parse YYYY-MM-DD string to date object."""
        return datetime.strptime(date_str, "%Y-%m-%d").date()

    def _new_id(self) -> str:
        """Generate a unique event ID."""
        return datetime.now().strftime("%Y%m%d%H%M%S%f")

    def _load(self):
        """Load events from disk."""
        try:
            if os.path.exists(CALENDAR_FILE):
                with open(CALENDAR_FILE, "r", encoding="utf-8") as f:
                    self._events = json.load(f)
        except Exception as e:
            log.warning(f"Calendar load error: {e}")
            self._events = []

    def _save(self):
        """Save events to disk."""
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(CALENDAR_FILE, "w", encoding="utf-8") as f:
                json.dump(self._events, f, indent=2, ensure_ascii=False)
        except Exception as e:
            log.error(f"Calendar save error: {e}")


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    cal = CalendarSkill()

    tests = [
        "Add meeting tomorrow at 3pm",
        "Add exam on Monday at 9am called Data Structures",
        "Add dentist appointment on April 25th at 2pm",
        "Add birthday party on 28th April",
        "Add class in 3 days at 10am called Machine Learning",
    ]

    print("=== Adding events ===")
    for t in tests:
        print(f"  '{t}'")
        print(f"  → {cal.add_event(t)}\n")

    print("=== Today's schedule ===")
    print(cal.get_today())
    print()
    print("=== This week ===")
    print(cal.get_this_week())
    print()
    print("=== Next event ===")
    print(cal.get_next_event())
