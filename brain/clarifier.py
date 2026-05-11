"""
JARVIS — brain/clarifier.py
Follow-up prompts for missing entities — like Google Assistant.

When user says "send a message" without specifying who/what,
JARVIS asks "Who should I send it to?" instead of failing.
"""

from brain.context_manager import ConversationContext
from brain.skill_registry import SKILL_REGISTRY
from utils.logger import log


# Human-readable prompts for each entity type
ENTITY_PROMPTS = {
    "contact": "Who should I send it to?",
    "message": "What should I say?",
    "app_name": "Which app should I open?",
    "app": "Which app?",
    "song": "What song should I play?",
    "query": "What should I search for?",
    "filename": "Which file?",
    "expression": "What calculation?",
    "duration": "How long?",
    "city": "Which city?",
    "recipient": "Who should I send the email to?",
    "subject": "What's the subject?",
    "body": "What should the email say?",
    "task": "What should I write?",
    "mode": "Which mode?",
    "product": "What product?",
    "text": "What should I type?",
}


class Clarifier:
    """Checks for missing required entities and prompts the user."""

    def check_and_clarify(
        self,
        intent_result: dict,
        context: ConversationContext,
    ) -> dict | None:
        """
        Check if the intent has all required entities.
        If not, set up clarification and return a prompt.

        Args:
            intent_result: {"action": "send_whatsapp", "entities": {"message": "hi"}}
            context: Current conversation context

        Returns:
            None if all entities present (proceed with execution).
            {"prompt": "Who should I send it to?", "action": "_clarify"} if missing.
        """
        action = intent_result.get("action", "")
        entities = intent_result.get("entities", {})

        if action not in SKILL_REGISTRY:
            return None

        skill = SKILL_REGISTRY[action]
        required = skill.get("required_entities", [])

        if not required:
            return None

        # Find missing required entities
        missing = []
        for entity in required:
            if entity not in entities or not entities[entity]:
                # Check aliases
                aliases = {
                    "app_name": ["app"],
                    "app": ["app_name"],
                    "song": ["query", "title"],
                    "query": ["song", "search"],
                }
                found = False
                for alias in aliases.get(entity, []):
                    if alias in entities and entities[alias]:
                        found = True
                        break
                if not found:
                    missing.append(entity)

        if not missing:
            return None  # All good, proceed

        # Set up clarification
        first_missing = missing[0]
        prompt = ENTITY_PROMPTS.get(first_missing, f"What's the {first_missing}?")

        log.info(f"Clarifier: missing {missing} for {action}, asking: {prompt}")

        context.set_pending_clarification({
            "action": action,
            "known_entities": entities.copy(),
            "missing": missing,
            "prompt": prompt,
        })

        return {
            "action": "_clarify",
            "entities": {"prompt": prompt},
            "confidence": 1.0,
            "source": "clarification",
        }
