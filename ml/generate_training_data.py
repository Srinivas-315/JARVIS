"""
JARVIS — ml/generate_training_data.py
Generates synthetic training data for the offline intent classifier.

Uses the skill_registry to create 1500+ labeled training examples
by expanding each skill's examples with natural language variations.

Run this FIRST, then run train_intent_model.py.
"""

import json
import random
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain.skill_registry import SKILL_REGISTRY

# ── Augmentation templates ──────────────────────────────────────
# These transform base examples into natural variations

POLITE_PREFIXES = [
    "", "", "",  # Most commands have no prefix (weighted)
    "please ", "can you ", "could you ", "hey jarvis ",
    "jarvis ", "yo ", "hey ", "would you ", "i want to ",
    "i need to ", "help me ", "go ahead and ", "just ",
    "quickly ", "can you please ", "i want you to ",
]

POLITE_SUFFIXES = [
    "", "", "", "",  # Most have no suffix (weighted)
    " please", " for me", " right now", " quickly",
    " asap", " now", " bro", " man", " sir",
    " if you can", " when you get a chance",
]

# ── Per-skill augmentation data ─────────────────────────────────
# Extra examples beyond what's in skill_registry

EXTRA_EXAMPLES = {
    "open_app": [
        "open {app}", "launch {app}", "start {app}", "fire up {app}",
        "run {app}", "can you open {app}", "please open {app}",
        "i need {app}", "bring up {app}", "get {app} running",
        "open up {app}", "pull up {app}", "load {app}",
        "hey open {app} for me", "start up {app}",
        "i want to use {app}", "switch to {app}",
    ],
    "close_app": [
        "close {app}", "kill {app}", "quit {app}", "exit {app}",
        "shut down {app}", "terminate {app}", "end {app}",
        "stop {app}", "close out of {app}", "get rid of {app}",
    ],
    "send_whatsapp": [
        "send {msg} to {name} on whatsapp",
        "whatsapp {name} {msg}", "message {name} saying {msg}",
        "text {name} {msg}", "tell {name} {msg} on whatsapp",
        "send a message to {name}", "whatsapp {name}",
        "drop a message to {name}", "ping {name} on whatsapp",
        "forward this to {name}", "let {name} know {msg}",
    ],
    "play_music": [
        "play {song}", "play some music", "play songs",
        "put on some {genre} music", "play {artist}",
        "i want to hear {song}", "can you play {song}",
        "play me some {genre}", "shuffle my playlist",
        "play my favorites", "music on", "start playing music",
        "put on {song}", "queue {song}", "play {song} by {artist}",
    ],
    "volume_control": [
        "volume up", "volume down", "louder", "quieter",
        "turn it up", "turn it down", "increase volume",
        "decrease volume", "mute", "unmute", "set volume to {n}",
        "make it louder", "make it quieter", "lower the volume",
        "raise the volume", "turn up the sound", "sound up",
        "full volume", "half volume", "volume to max",
    ],
    "media_control": [
        "pause", "resume", "next song", "previous song",
        "skip", "stop playing", "pause the music", "unpause",
        "play next", "go back", "repeat this song", "stop music",
        "continue playing", "skip this track", "next track",
    ],
    "weather": [
        "what's the weather", "how's the weather", "weather today",
        "is it going to rain", "weather forecast", "temperature outside",
        "weather in {city}", "what's it like outside", "is it cold",
        "is it hot", "will it rain tomorrow", "weather report",
        "how hot is it", "what's the temperature", "weather update",
    ],
    "news": [
        "latest news", "what's happening", "news today",
        "tell me the news", "headlines", "top stories",
        "tech news", "sports news", "business news",
        "what's new", "any news", "trending news",
        "breaking news", "world news", "news update",
    ],
    "web_search": [
        "search for {q}", "google {q}", "look up {q}",
        "find {q}", "search {q}", "what is {q}",
        "who is {q}", "search the web for {q}",
        "find out about {q}", "look up {q} online",
    ],
    "youtube_search": [
        "play {q} on youtube", "youtube {q}", "watch {q}",
        "show me {q} video", "find {q} on youtube",
        "youtube search {q}", "play {q} video",
    ],
    "screenshot": [
        "take a screenshot", "screenshot", "capture screen",
        "screen capture", "snap the screen", "grab the screen",
        "take a screen shot", "capture my screen",
    ],
    "time_date": [
        "what time is it", "what's the time", "current time",
        "what day is it", "what's today's date", "date today",
        "what day is today", "tell me the time", "time please",
    ],
    "math_calculate": [
        "what is {a} plus {b}", "{a} + {b}", "calculate {a} times {b}",
        "{a} minus {b}", "{a} divided by {b}", "what's {a} x {b}",
        "solve {a} into {b}", "compute {a} * {b}", "{a} over {b}",
    ],
    "set_reminder": [
        "remind me to {task}", "set a reminder for {task}",
        "remind me at {time} to {task}", "don't let me forget {task}",
        "reminder for {task}", "remind me about {task}",
    ],
    "chat": [
        "tell me about {topic}", "what do you think about {topic}",
        "explain {topic}", "tell me a joke", "who invented {topic}",
        "what is {topic}", "how does {topic} work",
        "why is the sky blue", "meaning of life",
        "hello", "hi", "hey", "how are you",
        "good morning", "good night", "thank you",
        "you're smart", "i love you", "what can you do",
        "are you real", "who made you", "roast me",
        "i'm bored", "i'm tired", "i'm stressed",
        "tell me something interesting", "give me advice",
        "what should i do today", "motivate me",
        "who are you", "are you better than alexa",
        "what's your favorite color", "do you have feelings",
    ],
    "system_info": [
        "battery status", "how much battery", "battery level",
        "cpu usage", "ram usage", "system health",
        "how much ram is free", "cpu temperature",
        "disk space", "storage status", "my ip address",
        "network info", "internet status", "system status",
    ],
    "send_email": [
        "send email to {name}", "email {name} about {topic}",
        "compose email to {name}", "write email to {name}",
        "send mail to {name}", "email {name} saying {msg}",
    ],
    "read_email": [
        "check my email", "read my inbox", "any new emails",
        "do i have mail", "show my emails", "read emails",
        "check gmail", "new messages in email",
    ],
    "vision_camera": [
        "what's in my hand", "what am i holding", "identify this",
        "what is this", "scan this", "look at this",
        "recognize this", "what do you see", "analyze this object",
        "what is that", "describe what you see", "read this text",
    ],
    "shutdown_system": [
        "shutdown", "shut down the computer", "restart",
        "restart my computer", "sleep mode", "hibernate",
        "turn off the computer", "power off", "log off",
    ],
    "brightness_control": [
        "increase brightness", "decrease brightness", "dim the screen",
        "brighter", "make it brighter", "screen too dark",
        "screen too bright", "brightness up", "brightness down",
    ],
    "set_timer": [
        "set timer for 5 minutes", "timer 10 minutes",
        "start a timer", "countdown 30 seconds",
        "set a 2 minute timer", "timer for {n} minutes",
    ],
    "app_mode": [
        "work mode", "study mode", "movie mode", "gaming mode",
        "activate work mode", "switch to study mode",
        "meeting mode", "focus mode", "relax mode",
    ],
}

# Fill-in values for template expansion
APPS = ["chrome", "spotify", "notepad", "vs code", "excel", "word",
        "firefox", "whatsapp", "telegram", "discord", "slack",
        "file explorer", "calculator", "paint", "teams", "zoom"]
NAMES = ["sarvani", "mom", "dad", "teja", "rahul", "priya", "boss"]
SONGS = ["believer", "shape of you", "blinding lights", "perfect",
         "closer", "faded", "alone", "happier", "thunder", "demons"]
ARTISTS = ["imagine dragons", "ed sheeran", "the weeknd", "alan walker"]
GENRES = ["bollywood", "pop", "rock", "lo-fi", "classical", "hip hop"]
CITIES = ["mumbai", "delhi", "chennai", "new york", "london", "bangalore"]
TOPICS = ["machine learning", "python", "space", "history", "physics",
          "artificial intelligence", "quantum computing", "blockchain"]
QUERIES = ["best laptop under 50000", "how to learn python",
           "restaurants near me", "python vs javascript"]
MESSAGES = ["good morning", "i'll be late", "coming in 10 minutes",
            "call me", "how are you", "happy birthday"]
TASKS = ["call mom", "buy groceries", "submit assignment", "exercise",
         "drink water", "take medicine", "check email"]


def fill_template(template: str) -> str:
    """Fill in template placeholders with random values."""
    result = template
    if "{app}" in result:
        result = result.replace("{app}", random.choice(APPS))
    if "{name}" in result:
        result = result.replace("{name}", random.choice(NAMES))
    if "{song}" in result:
        result = result.replace("{song}", random.choice(SONGS))
    if "{artist}" in result:
        result = result.replace("{artist}", random.choice(ARTISTS))
    if "{genre}" in result:
        result = result.replace("{genre}", random.choice(GENRES))
    if "{city}" in result:
        result = result.replace("{city}", random.choice(CITIES))
    if "{topic}" in result:
        result = result.replace("{topic}", random.choice(TOPICS))
    if "{q}" in result:
        result = result.replace("{q}", random.choice(QUERIES))
    if "{msg}" in result:
        result = result.replace("{msg}", random.choice(MESSAGES))
    if "{task}" in result:
        result = result.replace("{task}", random.choice(TASKS))
    if "{time}" in result:
        result = result.replace("{time}", random.choice(["5pm", "9am", "3:30pm", "tomorrow"]))
    if "{n}" in result:
        result = result.replace("{n}", str(random.randint(10, 100)))
    if "{a}" in result:
        result = result.replace("{a}", str(random.randint(1, 999)))
    if "{b}" in result:
        result = result.replace("{b}", str(random.randint(1, 999)))
    return result


def augment_text(text: str) -> list[str]:
    """Generate variations of a text with prefixes/suffixes."""
    variations = [text]  # Original always included
    for _ in range(3):  # 3 random augmentations per base
        prefix = random.choice(POLITE_PREFIXES)
        suffix = random.choice(POLITE_SUFFIXES)
        aug = prefix + text + suffix
        variations.append(aug.strip())
    return list(set(variations))  # Deduplicate


def generate_dataset() -> list[dict]:
    """Generate the full training dataset."""
    dataset = []

    for skill_name, skill_info in SKILL_REGISTRY.items():
        examples = list(skill_info["examples"])

        # Add extra examples if available
        if skill_name in EXTRA_EXAMPLES:
            for tmpl in EXTRA_EXAMPLES[skill_name]:
                # Generate 3 filled versions of each template
                for _ in range(3):
                    examples.append(fill_template(tmpl))

        # Augment all examples
        for example in examples:
            for variation in augment_text(example):
                dataset.append({
                    "text": variation.lower().strip(),
                    "label": skill_name,
                })

    # Shuffle
    random.shuffle(dataset)

    # Deduplicate by text
    seen = set()
    unique = []
    for item in dataset:
        if item["text"] not in seen:
            seen.add(item["text"])
            unique.append(item)

    return unique


def main():
    print("Generating training data for JARVIS Intent Classifier...")
    print(f"Skills: {len(SKILL_REGISTRY)}")

    dataset = generate_dataset()
    print(f"Total examples: {len(dataset)}")

    # Show distribution
    from collections import Counter
    dist = Counter(item["label"] for item in dataset)
    print("\nExamples per skill:")
    for skill, count in sorted(dist.items(), key=lambda x: -x[1]):
        print(f"  {skill}: {count}")

    # Save
    output_path = os.path.join(os.path.dirname(__file__), "training_data.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(dataset, f, indent=2, ensure_ascii=False)

    print(f"\nSaved to: {output_path}")
    print(f"Total unique examples: {len(dataset)}")
    print("\nNext step: Run 'python ml/train_intent_model.py'")


if __name__ == "__main__":
    main()
