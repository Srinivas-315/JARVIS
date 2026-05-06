"""
JARVIS — skills/task_chain.py
Execute multi-step commands in sequence.
Example: "Open Chrome and search for laptops"
"""

import time
from utils.logger import log


class TaskChain:
    """Parse and execute chained voice commands."""

    def __init__(self, jarvis):
        """Takes a reference to the main JARVIS instance."""
        self.jarvis = jarvis

    def is_chain(self, text: str) -> bool:
        """Check if the command contains multiple steps."""
        t = text.lower()
        return (" and then " in t or " then " in t or
                " and " in t and any(w in t for w in
                    ["open", "search", "play", "close", "type"]))

    def execute_chain(self, text: str) -> str:
        """Split and execute commands in sequence."""
        # Split on "and then", "then", "and"
        t = text.lower()

        if " and then " in t:
            parts = text.split(" and then ")
        elif " then " in t:
            parts = text.split(" then ")
        elif " and " in t:
            parts = text.split(" and ")
        else:
            parts = [text]

        results = []
        for i, part in enumerate(parts):
            part = part.strip()
            if not part:
                continue

            log.info(f"Chain step {i+1}/{len(parts)}: '{part}'")
            try:
                result = self.jarvis.process_command(part)
                if result:
                    results.append(result)
            except Exception as e:
                log.error(f"Chain step failed: {e}")

            # Wait between steps
            if i < len(parts) - 1:
                time.sleep(1.5)

        return results[-1] if results else "Done."
