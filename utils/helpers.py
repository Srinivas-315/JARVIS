"""
JARVIS — utils/helpers.py
Common utility functions used across all modules.
"""

import re
import subprocess
import sys
import time
from pathlib import Path

from utils.logger import log


def clean_text(text: str) -> str:
    """Remove unwanted characters from Gemini output for TTS."""
    # Remove markdown formatting
    text = re.sub(r"\*{1,2}(.*?)\*{1,2}", r"\1", text)  # **bold** / *italic*
    text = re.sub(r"#{1,6}\s*", "", text)  # ### headers
    text = re.sub(r"`{1,3}.*?`{1,3}", "", text, flags=re.DOTALL)  # `code`
    text = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", text)  # [links](url)
    text = re.sub(r"[-•●]\s+", "", text)  # bullet points
    text = re.sub(r"\n+", " ", text)  # newlines
    text = re.sub(r"\s+", " ", text)  # extra spaces
    return text.strip()


def speak_friendly(text: str) -> str:
    """Convert text to be more voice-friendly (numbers, symbols)."""
    text = text.replace("%", " percent")
    text = text.replace("$", " dollars")
    text = text.replace("₹", " rupees")
    text = text.replace("°C", " degrees Celsius")
    text = text.replace("°F", " degrees Fahrenheit")
    text = text.replace("km/h", " kilometers per hour")
    return text


def is_question(text: str) -> bool:
    """Check if a command is a question."""
    question_words = [
        "what",
        "who",
        "where",
        "when",
        "why",
        "how",
        "is",
        "are",
        "can",
        "could",
        "would",
        "should",
        "do",
        "does",
        "did",
    ]
    text_lower = text.lower().strip()
    return (
        text_lower.endswith("?") or text_lower.split()[0] in question_words
        if text_lower
        else False
    )


def contains_any(text: str, keywords: list) -> bool:
    """
    Check if text contains any of the given keywords.
    Uses word-boundary matching for single words to prevent false positives
    (e.g. 'end' should NOT match 'trending', 'kill' should NOT match 'skill').
    Multi-word phrases are matched as substrings (normal behaviour).
    """
    text_lower = text.lower()
    for kw in keywords:
        kw_lower = kw.lower()
        # Multi-word phrase → plain substring match (fast, accurate)
        if " " in kw_lower:
            if kw_lower in text_lower:
                return True
        else:
            # Single word → word-boundary match to avoid partial hits
            if re.search(r"\b" + re.escape(kw_lower) + r"\b", text_lower):
                return True
    return False


def get_jarvis_dir() -> Path:
    """Return the root JARVIS project directory."""
    return Path(__file__).parent.parent


def wait_animation(message: str = "Thinking", duration: float = 0.5):
    """Show a simple thinking animation in console."""
    frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    end_time = time.time() + duration
    i = 0
    while time.time() < end_time:
        sys.stdout.write(f"\r\033[36m{frames[i % len(frames)]} {message}...\033[0m")
        sys.stdout.flush()
        time.sleep(0.1)
        i += 1
    sys.stdout.write("\r" + " " * 40 + "\r")
    sys.stdout.flush()
