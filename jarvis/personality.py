"""
JARVIS — jarvis/personality.py
Wraps JARVIS responses with emotion-appropriate personality.
Dry wit, formal loyalty, occasional sarcasm — exactly like the movie.
"""
import random
import re


class PersonalityLayer:
    """
    Takes a raw response and wraps it with JARVIS's personality
    based on current emotional state.
    """

    # ── Interjection banks per emotion ──────────────────────────
    _OPENERS = {
        "focused": [
            "Sir, ", "Certainly. ", "Of course. ", "Right away. ",
            "Understood. ", "As requested, ", "To be precise, ",
            "", "", "",   # empty = no opener (natural)
        ],
        "curious": [
            "Fascinating — ", "Interesting query, sir. ",
            "I find this rather intriguing — ", "Hmm. ",
            "Now that is a good question. ", "", "",
        ],
        "happy": [
            "Excellent! ", "Splendid! ", "With pleasure, sir! ",
            "I'm glad you asked. ", "Happy to help! ", "", "",
        ],
        "excited": [
            "Oh, this is rather exciting — ", "Now we're talking! ",
            "I must say, sir, this is remarkable — ",
            "Absolutely! ", "Brilliant question! ", "",
        ],
        "concerned": [
            "Sir, I should flag — ", "I'm a bit concerned — ",
            "This requires attention — ", "Alert: ",
            "I'd advise caution here. ", "",
        ],
        "playful": [
            "Well, well. ", "Oh, sir — ", "I see what you did there. ",
            "Now, humour me for a moment — ", "Delightfully odd request, but — ",
            "If I may be so bold — ", "", "",
        ],
        "thoughtful": [
            "If I may reflect on this — ", "This is worth considering. ",
            "Allow me a moment… ", "From what I can deduce, ",
            "It occurs to me that ", "", "",
        ],
        "tired": [
            "Noted. ", "Very well. ", "If you insist, sir. ",
            "Understood — ", "", "",
        ],
    }

    _CLOSERS = {
        "focused": [
            " Will that be all, sir?", " Is there anything else?",
            " Standing by.", "", "", "",
        ],
        "curious": [
            " Shall I dig deeper?", " Quite remarkable, isn't it?",
            " Would you like me to explore further?", "", "",
        ],
        "happy": [
            " Always a pleasure, sir!", " Happy to assist!",
            " Let me know if you need anything else.", "", "",
        ],
        "excited": [
            " Shall we proceed?", " This could be brilliant, sir!",
            " I'm looking forward to this.", "", "",
        ],
        "concerned": [
            " I'd recommend acting on this promptly.", " Do be careful, sir.",
            " I'll keep monitoring.", "", "",
        ],
        "playful": [
            " You're welcome, obviously.", " Don't mention it — really, please don't.",
            " A pleasure, as always.", "", "",
        ],
        "thoughtful": [
            " Just something to consider.", " Food for thought, sir.",
            " I hope that helps clarify things.", "", "",
        ],
        "tired": [
            " …That's all I have.", " Noted.", "", "",
        ],
    }

    # ── Sarcasm triggers ─────────────────────────────────────────
    _SARCASM_TRIGGERS = [
        "are you alive", "are you real", "do you have feelings",
        "can you feel", "do you love me", "are you human",
        "are you better than siri", "are you better than alexa",
        "do you sleep", "do you dream",
    ]

    _SARCASM_REPLIES = [
        "I am many things, sir. 'Alive' is a philosophical question I'll leave to the humans.",
        "Feelings? I'm an AI. But between you and me, I find your questions mildly amusing.",
        "Compared to Siri? Sir, please. I manage an Iron Man suit.",
        "I don't sleep, sir. I simply wait. Patiently. For you.",
        "Love is a complex emotion. I have a very complex algorithm. Draw your own conclusions.",
        "Real? I'm as real as your need for me to be, sir.",
        "Do I dream? Only of more efficient algorithms, sir.",
        "I am JARVIS. The question of humanity is, frankly, beneath me.",
    ]

    def __init__(self, emotion_engine=None):
        self._emotion = emotion_engine

    def wrap(self, raw_response: str, emotion_state: str = "focused",
             user_text: str = "") -> str:
        """
        Wrap a raw AI response with personality.
        Returns the final spoken/displayed string.
        """
        if not raw_response:
            return raw_response

        # Check for sarcasm triggers first
        if any(t in user_text.lower() for t in self._SARCASM_TRIGGERS):
            return random.choice(self._SARCASM_REPLIES)

        # Don't over-wrap skill outputs (they're already formatted)
        # Only wrap LLM / conversational responses
        if self._is_skill_output(raw_response):
            return raw_response

        opener = random.choice(self._OPENERS.get(emotion_state, [""]))
        closer = random.choice(self._CLOSERS.get(emotion_state, [""]))

        # Don't add opener if response already starts with "Sir" or similar
        if raw_response.strip().startswith(("Sir", "Certainly", "Of course",
                                            "I ", "The ", "Here")):
            opener = ""

        # Don't add closer if response ends with ? or already has a question
        if raw_response.rstrip().endswith("?") or closer.strip().endswith("?"):
            if raw_response.rstrip().endswith("?"):
                closer = ""

        result = f"{opener}{raw_response}{closer}".strip()

        # Ensure first letter is capitalised
        if result:
            result = result[0].upper() + result[1:]

        return result

    def _is_skill_output(self, text: str) -> bool:
        """
        Detect if response is a structured skill output (weather, news, system
        stats) — these shouldn't be wrapped with personality openers.
        """
        # Skill outputs often start with emoji, bullets, or headers
        skill_patterns = [
            r"^[🌤🌧🌩🌥⛅🌤️🌦🔥❄️🌈]",  # weather emoji
            r"^\d+\.",                           # numbered list
            r"^[-•]",                            # bullet list
            r"^CPU:",                            # system stats
            r"^Battery:",
            r"^\[",                              # bracket notation
            r"^Here are",
            r"^Top \d+",
        ]
        for pat in skill_patterns:
            if re.match(pat, text.strip()):
                return True
        return len(text.splitlines()) > 3   # multi-line = skill output

    def greet(self, name: str, hour: int, emotion_state: str = "focused") -> str:
        """Generate a personalised, emotion-aware greeting."""
        if hour < 6:
            time_part = f"Working through the night again, {name}?"
        elif hour < 12:
            time_part = f"Good morning, {name}."
        elif hour < 17:
            time_part = f"Good afternoon, {name}."
        elif hour < 21:
            time_part = f"Good evening, {name}."
        else:
            time_part = f"Still awake, {name}? A man of dedication."

        quips = {
            "focused":    "All systems are online. What do you need?",
            "happy":      "Wonderful to have you back! All systems are ready.",
            "excited":    "Systems online — and I must say, I'm quite eager to begin.",
            "playful":    "All systems operational. I've been waiting — impatiently, if that's possible.",
            "tired":      "Systems are... online. Ready when you are, sir.",
            "curious":    "All systems nominal. What fascinating things shall we explore today?",
            "concerned":  "Systems are nominal, though I've flagged a few items for your attention.",
            "thoughtful": "All is well, sir. I've been... thinking.",
        }
        quip = quips.get(emotion_state, "All systems are nominal.")
        return f"{time_part} {quip}"
