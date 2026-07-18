import unittest
import tempfile
import os
from unittest.mock import patch

from skills.whatsapp import WhatsAppSkill
import memory.database

class TestWhatsAppDrafts(unittest.TestCase):
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

        # Initialize WhatsAppSkill
        self.whatsapp = WhatsAppSkill()

    def tearDown(self):
        self.patcher.stop()
        memory.database.close_connection()
        if os.path.exists(self.temp_path):
            try:
                os.remove(self.temp_path)
            except PermissionError:
                pass

    def test_create_and_read_draft(self):
        # Create a draft
        self.whatsapp.save_draft("John", "Incoming John", "Hello John")
        
        # Read the draft from DB
        conn = memory.database.get_connection()
        drafts = conn.execute("SELECT * FROM whatsapp_drafts WHERE status='pending'").fetchall()
        
        self.assertEqual(len(drafts), 1)
        self.assertEqual(drafts[0]["contact"], "John")
        self.assertEqual(drafts[0]["generated_reply"], "Hello John")

        # Test string read
        resp = self.whatsapp.read_draft(drafts[0]["id"])
        self.assertIn("John", resp)

    def test_reject_draft(self):
        # Create a draft
        self.whatsapp.save_draft("Alice", "Incoming Alice", "Hi Alice")
        
        conn = memory.database.get_connection()
        drafts = conn.execute("SELECT * FROM whatsapp_drafts WHERE status='pending'").fetchall()
        self.assertEqual(len(drafts), 1)
        d_id = drafts[0]["id"]
        
        # Reject it
        self.whatsapp.reject_draft(d_id)
        
        # Verify it's rejected
        drafts_after = conn.execute("SELECT * FROM whatsapp_drafts WHERE status='pending'").fetchall()
        self.assertEqual(len(drafts_after), 0)

    def test_clear_drafts(self):
        self.whatsapp.save_draft("Bob", "Incoming", "Hi Bob")
        self.whatsapp.save_draft("Charlie", "Incoming", "Hi Charlie")
        
        conn = memory.database.get_connection()
        drafts = conn.execute("SELECT * FROM whatsapp_drafts WHERE status='pending'").fetchall()
        self.assertEqual(len(drafts), 2)
        
        # Clear all
        self.whatsapp.clear_drafts()
        
        drafts_after = conn.execute("SELECT * FROM whatsapp_drafts WHERE status='pending'").fetchall()
        self.assertEqual(len(drafts_after), 0)

    def test_restart_persistence(self):
        # Create draft
        self.whatsapp.save_draft("Dave", "Incoming", "Hello Dave")
        
        # Simulate restart
        memory.database.close_connection()
        
        # Re-initialize
        new_whatsapp = WhatsAppSkill()
        
        # Direct DB check
        conn = memory.database.get_connection()
        drafts = conn.execute("SELECT * FROM whatsapp_drafts WHERE status='pending'").fetchall()
        
        # Verify state is loaded
        self.assertEqual(len(drafts), 1)
        self.assertEqual(drafts[0]["contact"], "Dave")

if __name__ == "__main__":
    unittest.main()
