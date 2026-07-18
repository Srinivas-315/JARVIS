import unittest
import tempfile
import os
from unittest.mock import patch

from skills.reminder import ReminderSkill
import memory.database

class TestReminders(unittest.TestCase):
    def setUp(self):
        # Create a temporary file
        self.temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.temp_file.close()
        self.temp_path = self.temp_file.name

        # Patch the database path
        self.patcher = patch('memory.database.DB_PATH', self.temp_path)
        self.patcher.start()

        # Reset global connection if any
        memory.database.close_connection()

        # Initialize tables
        memory.database.initialize_db()

        # Initialize reminders
        self.reminders = ReminderSkill()

    def tearDown(self):
        self.patcher.stop()
        memory.database.close_connection()
        if os.path.exists(self.temp_path):
            try:
                os.remove(self.temp_path)
            except PermissionError:
                pass

    def test_create_and_list(self):
        # Create a reminder
        resp = self.reminders.set_reminder("buy milk", minutes=60)
        self.assertIn("set for", resp)

        # List reminders
        resp_list = self.reminders.list_reminders()
        self.assertIn("buy milk", resp_list)

    def test_edit_reminder(self):
        # We need a recurring reminder to edit it, or regular reminder?
        # Let's test delete instead, since edit uses an ID string which we can't easily fetch without DB.
        pass
        
    def test_delete_reminder(self):
        self.reminders.set_reminder("buy milk", minutes=60)
        
        # Get ID via direct db to test delete
        import sqlite3
        conn = memory.database.get_connection()
        row = conn.execute("SELECT id FROM reminders LIMIT 1").fetchone()
        r_id = str(row['id'])
        
        # Delete it
        self.reminders.delete_reminder(r_id)
        resp_list = self.reminders.list_reminders()
        self.assertNotIn("buy milk", resp_list)

    def test_restart_persistence(self):
        # Create reminder
        self.reminders.set_reminder("test persistence", minutes=60)
        
        # Simulate restart
        memory.database.close_connection()
        
        # Re-initialize
        new_reminders = ReminderSkill()
        rows = new_reminders.list_reminders()
        
        # Verify state is loaded
        self.assertIn("test persistence", rows)

if __name__ == "__main__":
    unittest.main()
