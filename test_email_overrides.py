import sys
import os

from brain.smart_router import SmartRouter

class MockEmailHandler:
    def check_unread(self): pass
    def search_emails(self, query): pass
    def get_stats(self): pass
    def undo_send(self): pass
    def schedule_email(self, recipient, subject, body, time): pass
    def reply_to_last(self, body): pass
    def forward_last(self, recipient): pass

class MockJarvis:
    def __init__(self):
        self.email = MockEmailHandler()

from brain.skill_executor import SkillExecutor

class MockGeminiHandler:
    pass

import io
import contextlib

def main():
    router = SmartRouter(gemini_handler=MockGeminiHandler())
    executor = SkillExecutor(MockJarvis())

    test_commands = [
        "check unread emails",
        "search email for invoice",
        "email stats",
        "undo email",
        "schedule email to myself at 10:05 pm saying testing",
        "reply to last email saying thanks",
        "forward last email to boss"
    ]

    print("================== EMAIL OVERRIDE TEST REPORT ==================")
    for cmd in test_commands:
        print(f"\n--- Testing Command: '{cmd}' ---")
        
        result = router.route(cmd, context={})
        
        print(f"Input: {cmd}")
        if result:
            action_val = result.get("action")
            entities_val = result.get("entities")
        else:
            action_val = "None"
            entities_val = "None"
            
        print(f"Router Result Action: {action_val}")
        print(f"Entities: {entities_val}")
        
        if result:
            f = io.StringIO()
            with contextlib.redirect_stdout(f):
                try:
                    executor.execute(result)
                except Exception as e:
                    print(f"Error during execution: {e}")
            
            trace_output = f.getvalue().strip()
            if trace_output:
                print("--- Captured Executor Trace ---")
                print(trace_output)
            else:
                print("No trace output from executor.")
        else:
            print("Router failed to route this command.")

if __name__ == "__main__":
    main()
