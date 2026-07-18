import logging

log = logging.getLogger("jarvis")

class CalendarHandler:
    """
    Handles parsing and routing of calendar-related voice/text commands.
    Extracts the Calendar routing logic from main.py.
    """
    def __init__(self, calendar_skill, jarvis_instance):
        self.calendar = calendar_skill
        self.jarvis = jarvis_instance

    def handle(self, text: str, text_lower: str) -> str | None:
        """
        Processes a command string. 
        Returns the response string if it's a calendar command, else None.
        """
        # 1. Add event
        add_event_triggers = [
            "add event",
            "add a calendar event",
            "add an event",
            "schedule a",
            "schedule an",
            "create event",
            "put a ",
            "book a",
            "set up a",
            "remind me to",
            "add to calendar",
        ]
        if any(t in text_lower for t in add_event_triggers):
            try:
                response = self.calendar.add_event(text)
            except Exception as e:
                log.exception(f"Skill error: {e}")
                response = "I encountered an error trying to do that."
            return response

        # 2. Show schedule
        if any(
            t in text_lower
            for t in [
                "what's my schedule",
                "my schedule",
                "what do i have",
                "what's happening",
            ]
        ):
            if "tomorrow" in text_lower:
                return self.calendar.get_tomorrow()
            elif "week" in text_lower:
                return self.calendar.get_this_week()
            elif any(
                d in text_lower
                for d in [
                    "monday",
                    "tuesday",
                    "wednesday",
                    "thursday",
                    "friday",
                    "saturday",
                    "sunday",
                ]
            ):
                return self.calendar.get_schedule_for_day(text)
            else:
                return self.calendar.get_today()

        # 3. Today's schedule
        if any(
            t in text_lower
            for t in [
                "today's schedule",
                "schedule for today",
                "what's today",
                "do i have anything today",
            ]
        ):
            return self.calendar.get_today()

        # 4. Tomorrow's schedule
        if any(
            t in text_lower
            for t in [
                "tomorrow's schedule",
                "schedule for tomorrow",
                "do i have anything tomorrow",
            ]
        ):
            return self.calendar.get_tomorrow()

        # 5. Next event
        if "next event" in text_lower or "upcoming event" in text_lower:
            return self.calendar.get_next_event()

        # 6. List all events
        if any(
            t in text_lower
            for t in [
                "show all events",
                "list events",
                "all my events",
                "show calendar",
            ]
        ):
            return self.calendar.list_all_events()

        # 7. Cancel event
        if any(
            t in text_lower
            for t in ["cancel event", "delete event", "remove event", "cancel my"]
        ):
            try:
                response = self.calendar.cancel_event(text)
            except Exception as e:
                log.exception(f"Skill error: {e}")
                response = "I encountered an error trying to do that."
            return response

        # Not a calendar command
        return None
