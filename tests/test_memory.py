import unittest
import tempfile
import os
import json
from pathlib import Path
from unittest.mock import patch

from memory.personal_memory import PersonalMemory
import memory.personal_memory

class TestPersonalMemory(unittest.TestCase):
    def setUp(self):
        # Create a temporary file
        self.temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
        self.temp_file.close()
        self.temp_path = Path(self.temp_file.name)

        # Patch the facts file location
        self.patcher = patch('memory.personal_memory._FACTS_FILE', self.temp_path)
        self.patcher.start()

        # Initialize memory
        self.memory = PersonalMemory()

    def tearDown(self):
        self.patcher.stop()
        if os.path.exists(self.temp_path):
            os.remove(self.temp_path)

    def test_create_and_read(self):
        # Action: learn a fact
        resp = self.memory.try_learn("my name is Alice")
        self.assertIn("Alice", resp)

        # Action: read the fact
        resp_read = self.memory.try_recall("what is my name")
        self.assertIn("Alice", resp_read)
        self.assertEqual(self.memory.get_all().get("name"), "Alice")

    def test_update(self):
        self.memory.try_learn("my name is Alice")
        self.assertEqual(self.memory.get_all().get("name"), "Alice")

        # Update the fact
        self.memory.try_learn("my name is Bob")
        self.assertEqual(self.memory.get_all().get("name"), "Bob")
        
        resp_read = self.memory.try_recall("what is my name")
        self.assertIn("Bob", resp_read)

    def test_delete(self):
        self.memory.try_learn("my name is Alice")
        self.assertEqual(self.memory.get_all().get("name"), "Alice")

        # Delete the fact
        resp = self.memory.try_recall("forget everything about me")
        self.assertIn("forgotten", resp)
        self.assertNotIn("name", self.memory.get_all())

    def test_restart_persistence(self):
        # Create a fact
        self.memory.try_learn("my name is Charlie")
        
        # Verify it was written to disk
        with open(self.temp_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            self.assertEqual(data.get("name"), "Charlie")

        # Create a completely new instance (simulating restart)
        new_memory = PersonalMemory()
        
        # Verify state is loaded automatically
        self.assertEqual(new_memory.get_all().get("name"), "Charlie")
        resp = new_memory.try_recall("what is my name")
        self.assertIn("Charlie", resp)

if __name__ == "__main__":
    unittest.main()
