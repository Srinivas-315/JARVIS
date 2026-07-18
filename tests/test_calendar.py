import unittest
import tempfile
import os
import json
from unittest.mock import patch

from skills.calendar_skill import CalendarSkill
from datetime import datetime, timedelta

class TestCalendarSkill(unittest.TestCase):
    def setUp(self):
        # Create a temporary file
        self.temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
        self.temp_file.close()
        self.temp_path = self.temp_file.name

        # Patch the facts file location
        self.patcher = patch('skills.calendar_skill.CALENDAR_FILE', self.temp_path)
        self.patcher.start()

        # Initialize calendar
        self.calendar = CalendarSkill()

    def tearDown(self):
        self.patcher.stop()
        if os.path.exists(self.temp_path):
            os.remove(self.temp_path)

    def test_add_event(self):
        # Action: Add an event tomorrow
        resp = self.calendar.add_event("add meeting tomorrow at 3pm")
        self.assertIn("added", resp.lower())
        self.assertEqual(len(self.calendar._events), 1)
        self.assertEqual(self.calendar._events[0]["name"], "Meeting")

    def test_list_events(self):
        # Action: Add events and list them
        self.calendar.add_event("add meeting tomorrow at 3pm")
        self.calendar.add_event("add gym tomorrow at 6pm")

        resp_list = self.calendar.get_tomorrow()
        self.assertIn("meeting", resp_list.lower())
        self.assertIn("gym", resp_list.lower())
        
        resp_all = self.calendar.list_all_events()
        self.assertIn("meeting", resp_all.lower())
        self.assertIn("gym", resp_all.lower())

    def test_cancel_event(self):
        # Action: Add event and then cancel it
        self.calendar.add_event("add meeting tomorrow at 3pm")
        self.assertEqual(len(self.calendar._events), 1)

        resp = self.calendar.cancel_event("cancel meeting")
        self.assertIn("Removed", resp)
        self.assertEqual(len(self.calendar._events), 0)

    def test_restart_persistence(self):
        # Action: Add event
        self.calendar.add_event("add meeting tomorrow at 3pm")
        
        # Verify it was written to disk
        with open(self.temp_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            self.assertEqual(len(data), 1)
            self.assertEqual(data[0]["name"], "Meeting")

        # Simulate restart
        new_calendar = CalendarSkill()
        
        # Verify state loaded automatically
        self.assertEqual(len(new_calendar._events), 1)
        self.assertEqual(new_calendar._events[0]["name"], "Meeting")

if __name__ == "__main__":
    unittest.main()
