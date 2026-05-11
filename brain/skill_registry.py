"""
JARVIS — brain/skill_registry.py
Central registry of all JARVIS skills.

The SmartRouter sends this list to Gemini so it knows what
JARVIS can do and what entities each skill needs. Think of it
as the "menu" — Gemini picks the right item and extracts
the required ingredients.

Adding a new skill?  Just add an entry here. No more writing
20 `if` blocks in main.py!
"""

# ── Complete Skill Registry ──────────────────────────────────────
# Each skill has:
#   description: What it does (shown to AI)
#   examples: Sample commands (helps AI match)
#   required_entities: Must be present to execute
#   optional_entities: Nice to have
#   handler_path: Which skill object.method to call

SKILL_REGISTRY = {

    # ══════════════════════════════════════════════════════════════
    #  APP / WINDOW CONTROL
    # ══════════════════════════════════════════════════════════════

    "open_app": {
        "description": "Open or launch an application or program",
        "examples": [
            "open chrome", "launch spotify", "start VS Code",
            "open notepad", "fire up Excel", "open WhatsApp",
            "can you open Chrome for me", "please launch Firefox",
        ],
        "required_entities": ["app_name"],
        "optional_entities": ["profile"],
    },

    "close_app": {
        "description": "Close, kill, or quit an application",
        "examples": [
            "close chrome", "kill notepad", "quit spotify",
            "exit Teams", "force close Edge",
        ],
        "required_entities": ["app_name"],
        "optional_entities": [],
    },

    # ══════════════════════════════════════════════════════════════
    #  WHATSAPP MESSAGING
    # ══════════════════════════════════════════════════════════════

    "send_whatsapp": {
        "description": "Send a message to someone on WhatsApp",
        "examples": [
            "send hi to Sarvani on WhatsApp",
            "WhatsApp Mom saying good morning",
            "message Teja I'll be late",
            "text Banty on WhatsApp hi how are you",
        ],
        "required_entities": ["contact", "message"],
        "optional_entities": ["language"],
    },

    "read_whatsapp": {
        "description": "Read last messages from a WhatsApp contact",
        "examples": [
            "read last messages from Sarvani",
            "what did Mom say on WhatsApp",
            "show messages from Teja",
        ],
        "required_entities": ["contact"],
        "optional_entities": ["count"],
    },

    "open_whatsapp_chat": {
        "description": "Open someone's chat in WhatsApp",
        "examples": [
            "open Sarvani's chat", "go to Teja's WhatsApp",
            "open chat with Mom",
        ],
        "required_entities": ["contact"],
        "optional_entities": [],
    },

    "type_text": {
        "description": "Type text in the currently active window or WhatsApp",
        "examples": [
            "type hello", "type I am coming",
            "type good morning",
        ],
        "required_entities": ["text"],
        "optional_entities": [],
    },

    # ══════════════════════════════════════════════════════════════
    #  MEDIA / MUSIC
    # ══════════════════════════════════════════════════════════════

    "play_music": {
        "description": "Play a song or music on Spotify or YouTube",
        "examples": [
            "play Believer", "play some music",
            "play Bollywood songs", "play Imagine Dragons",
        ],
        "required_entities": [],
        "optional_entities": ["song", "artist", "genre", "platform"],
    },

    "media_control": {
        "description": "Control media playback — pause, resume, next, previous, stop",
        "examples": [
            "pause the music", "resume", "next song",
            "skip this song", "previous track", "stop playing",
        ],
        "required_entities": ["action"],
        "optional_entities": [],
    },

    "volume_control": {
        "description": "Change the system volume — up, down, mute, set level",
        "examples": [
            "volume up", "turn it down", "set volume to 50",
            "mute", "unmute", "louder", "quieter",
            "make it louder", "increase volume",
        ],
        "required_entities": ["direction"],
        "optional_entities": ["level"],
    },

    # ══════════════════════════════════════════════════════════════
    #  SYSTEM CONTROL
    # ══════════════════════════════════════════════════════════════

    "screenshot": {
        "description": "Take a screenshot of the screen",
        "examples": [
            "take a screenshot", "capture screen",
            "screenshot", "screen capture",
        ],
        "required_entities": [],
        "optional_entities": [],
    },

    "brightness_control": {
        "description": "Change screen brightness",
        "examples": [
            "increase brightness", "dim the screen",
            "set brightness to 50", "brightness up",
        ],
        "required_entities": ["direction"],
        "optional_entities": ["level"],
    },

    "system_info": {
        "description": "Get system info: battery, CPU temp, RAM, network, health",
        "examples": [
            "battery status", "CPU temperature",
            "system health", "how much RAM",
            "network info", "my IP address",
        ],
        "required_entities": ["info_type"],
        "optional_entities": [],
    },

    "shutdown_system": {
        "description": "Shutdown, restart, sleep, or hibernate the computer",
        "examples": [
            "shutdown", "restart", "sleep",
            "hibernate", "log off",
        ],
        "required_entities": ["action"],
        "optional_entities": ["delay"],
    },

    # ══════════════════════════════════════════════════════════════
    #  WEB / SEARCH / BROWSE
    # ══════════════════════════════════════════════════════════════

    "web_search": {
        "description": "Search the web using Google or real-time search",
        "examples": [
            "search for laptops under 50000",
            "Google who invented Python",
            "look up best restaurants near me",
        ],
        "required_entities": ["query"],
        "optional_entities": [],
    },

    "youtube_search": {
        "description": "Search and play videos on YouTube",
        "examples": [
            "play Minecraft on YouTube",
            "YouTube how to make pasta",
            "watch funny cat videos",
        ],
        "required_entities": ["query"],
        "optional_entities": [],
    },

    "browser_control": {
        "description": "Control the browser — tabs, bookmarks, zoom, dark mode, etc.",
        "examples": [
            "bookmark this page", "zoom in",
            "go back", "reload page", "toggle dark mode",
        ],
        "required_entities": ["action"],
        "optional_entities": ["query"],
    },

    # ══════════════════════════════════════════════════════════════
    #  WEATHER / NEWS
    # ══════════════════════════════════════════════════════════════

    "weather": {
        "description": "Get current weather, forecast, AQI, sunrise/sunset",
        "examples": [
            "what's the weather", "weather in Mumbai",
            "will it rain tomorrow", "air quality index",
            "sunrise time", "should I carry an umbrella",
        ],
        "required_entities": [],
        "optional_entities": ["city", "type"],
    },

    "news": {
        "description": "Get latest news headlines, trending topics, or topic-specific news",
        "examples": [
            "latest news", "tech news",
            "what's trending", "positive news",
        ],
        "required_entities": [],
        "optional_entities": ["topic", "mood"],
    },

    # ══════════════════════════════════════════════════════════════
    #  EMAIL
    # ══════════════════════════════════════════════════════════════

    "send_email": {
        "description": "Send an email",
        "examples": [
            "send email to Rahul saying I'll be late",
            "compose email to boss about the meeting",
            "email Mom saying happy birthday",
        ],
        "required_entities": ["recipient"],
        "optional_entities": ["subject", "body"],
    },

    "read_email": {
        "description": "Read or check emails",
        "examples": [
            "check my email", "read my inbox",
            "any new emails", "read email from Boss",
        ],
        "required_entities": [],
        "optional_entities": ["sender"],
    },

    # ══════════════════════════════════════════════════════════════
    #  REMINDERS / CALENDAR / TIMER
    # ══════════════════════════════════════════════════════════════

    "set_reminder": {
        "description": "Set a one-time or recurring reminder",
        "examples": [
            "remind me at 5pm to call Mom",
            "set a reminder for tomorrow morning",
            "remind me every day to exercise",
        ],
        "required_entities": ["message"],
        "optional_entities": ["time", "recurring"],
    },

    "list_reminders": {
        "description": "Show all pending reminders",
        "examples": [
            "show my reminders", "list reminders",
            "upcoming reminders", "what are my reminders",
        ],
        "required_entities": [],
        "optional_entities": [],
    },

    "set_timer": {
        "description": "Set a countdown timer",
        "examples": [
            "set timer for 5 minutes",
            "timer 30 seconds", "countdown 10 minutes",
        ],
        "required_entities": ["duration"],
        "optional_entities": ["unit"],
    },

    "calendar_event": {
        "description": "Add, view, or manage calendar events",
        "examples": [
            "add meeting at 3pm tomorrow",
            "what's my schedule today",
            "show all events this week",
            "cancel my 5pm meeting",
        ],
        "required_entities": ["action"],
        "optional_entities": ["title", "time", "date"],
    },

    # ══════════════════════════════════════════════════════════════
    #  FILES / CLIPBOARD
    # ══════════════════════════════════════════════════════════════

    "file_operation": {
        "description": "File operations: create, open, delete, search, organize, zip/unzip",
        "examples": [
            "create a file called notes.txt",
            "find file report.pdf", "organize downloads",
            "find duplicates", "zip my documents",
        ],
        "required_entities": ["action"],
        "optional_entities": ["filename", "path"],
    },

    "clipboard_operation": {
        "description": "Clipboard operations: read, summarize, translate, extract, QR code, diff",
        "examples": [
            "read clipboard", "summarize what I copied",
            "translate clipboard to Hindi",
            "extract URLs from clipboard", "generate QR code",
        ],
        "required_entities": ["action"],
        "optional_entities": ["language", "format"],
    },

    # ══════════════════════════════════════════════════════════════
    #  VISION / CAMERA
    # ══════════════════════════════════════════════════════════════

    "vision_camera": {
        "description": "Use the camera to identify objects, read text, describe scene",
        "examples": [
            "what's in my hand", "identify this",
            "read this text", "what am I holding",
            "look through the camera", "scan this",
        ],
        "required_entities": [],
        "optional_entities": ["mode"],
    },

    "vision_screen": {
        "description": "Analyze what's on the screen",
        "examples": [
            "what's on my screen", "describe my screen",
            "what app is this", "read my screen",
        ],
        "required_entities": [],
        "optional_entities": [],
    },

    # ══════════════════════════════════════════════════════════════
    #  CODE / PROBLEM SOLVING
    # ══════════════════════════════════════════════════════════════

    "write_code": {
        "description": "Write or generate code in VS Code",
        "examples": [
            "write a Python calculator",
            "create a snake game using pygame",
            "write a React todo app",
        ],
        "required_entities": ["task"],
        "optional_entities": ["language"],
    },

    "solve_problem": {
        "description": "Solve coding problems, LeetCode questions, debug code",
        "examples": [
            "solve this LeetCode problem",
            "debug this code", "solve two sum",
        ],
        "required_entities": [],
        "optional_entities": ["problem"],
    },

    # ══════════════════════════════════════════════════════════════
    #  SHOPPING
    # ══════════════════════════════════════════════════════════════

    "shopping": {
        "description": "Search products on Amazon/Flipkart, compare prices, manage wishlist",
        "examples": [
            "search laptops on Amazon",
            "compare prices for iPhone 16",
            "add to wishlist", "show my wishlist",
        ],
        "required_entities": ["action"],
        "optional_entities": ["product", "platform"],
    },

    # ══════════════════════════════════════════════════════════════
    #  TIME / DATE / MATH
    # ══════════════════════════════════════════════════════════════

    "time_date": {
        "description": "Get current time, date, day, or time in another city",
        "examples": [
            "what time is it", "today's date",
            "what day is it", "time in New York",
        ],
        "required_entities": [],
        "optional_entities": ["city"],
    },

    "math_calculate": {
        "description": "Calculate a math expression",
        "examples": [
            "what is 16 times 16", "2 plus 2",
            "calculate 500 divided by 7", "16 into 16",
        ],
        "required_entities": ["expression"],
        "optional_entities": [],
    },

    # ══════════════════════════════════════════════════════════════
    #  SCREEN CONTROL
    # ══════════════════════════════════════════════════════════════

    "screen_control": {
        "description": "Mouse clicks, scrolling, keyboard shortcuts, window snapping",
        "examples": [
            "scroll down", "click there", "press enter",
            "select all", "copy this", "undo",
            "snap window left", "minimize", "alt tab",
        ],
        "required_entities": ["action"],
        "optional_entities": ["target"],
    },

    # ══════════════════════════════════════════════════════════════
    #  CONVERSATION / CHAT
    # ══════════════════════════════════════════════════════════════

    "chat": {
        "description": "General conversation, questions, opinions, explanations — anything not matching a specific skill",
        "examples": [
            "tell me about black holes",
            "what do you think about AI",
            "explain machine learning",
            "tell me a joke",
        ],
        "required_entities": [],
        "optional_entities": [],
    },

    # ══════════════════════════════════════════════════════════════
    #  VOICE CONTROL
    # ══════════════════════════════════════════════════════════════

    "voice_control": {
        "description": "Change JARVIS voice, speed, or personality",
        "examples": [
            "change voice to Bella", "speak faster",
            "speak slower", "what voice are you using",
            "list voices", "formal mode", "casual mode",
        ],
        "required_entities": ["action"],
        "optional_entities": ["voice_name", "speed"],
    },

    # ══════════════════════════════════════════════════════════════
    #  NOTIFICATION CONTROL
    # ══════════════════════════════════════════════════════════════

    "notification_control": {
        "description": "Manage notifications — do not disturb, mute/unmute apps, list recent",
        "examples": [
            "do not disturb for 30 minutes",
            "mute WhatsApp notifications",
            "what notifications did I get",
            "resume notifications",
        ],
        "required_entities": ["action"],
        "optional_entities": ["app", "duration"],
    },

    # ══════════════════════════════════════════════════════════════
    #  MEMORY / PERSONAL
    # ══════════════════════════════════════════════════════════════

    "memory": {
        "description": "Remember facts, recall information, memory stats",
        "examples": [
            "remember that I love Python",
            "what do you remember about me",
            "forget everything",
            "my name is Srini",
        ],
        "required_entities": ["action"],
        "optional_entities": ["fact", "key"],
    },

    # ══════════════════════════════════════════════════════════════
    #  APP MODES
    # ══════════════════════════════════════════════════════════════

    "app_mode": {
        "description": "Activate a mode like work, study, movie, gaming",
        "examples": [
            "work mode", "study mode",
            "movie mode", "gaming mode",
        ],
        "required_entities": ["mode"],
        "optional_entities": [],
    },
}


def get_skill_descriptions_for_ai() -> str:
    """
    Generate a compact text summary of all skills for the AI router prompt.
    Formatted to be token-efficient while giving Gemini enough info.
    """
    lines = []
    for skill_name, skill in SKILL_REGISTRY.items():
        examples_str = " | ".join(skill["examples"][:3])
        entities = ", ".join(skill["required_entities"]) if skill["required_entities"] else "none"
        lines.append(f"- {skill_name}: {skill['description']} (needs: {entities}) e.g. \"{examples_str}\"")
    return "\n".join(lines)


def get_all_skill_names() -> list[str]:
    """Get list of all registered skill names."""
    return list(SKILL_REGISTRY.keys())


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    print(f"Total skills registered: {len(SKILL_REGISTRY)}")
    print("\n" + get_skill_descriptions_for_ai())
