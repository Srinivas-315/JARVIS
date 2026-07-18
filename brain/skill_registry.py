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

    "whatsapp_status": {
        "description": "Check if a contact is online or view their last seen status on WhatsApp",
        "examples": [
            "is Mom online on WhatsApp?", "check status of Teja on WhatsApp",
            "last seen of Sarvani", "when was Rahul online",
        ],
        "required_entities": ["contact"],
        "optional_entities": [],
    },

    "whatsapp_schedule": {
        "description": "Schedule a WhatsApp message to be sent to a contact at a specific time",
        "examples": [
            "schedule WhatsApp message to Mom good night at 10 pm",
            "schedule message to Rahul saying I'll be late in 5 minutes",
            "schedule good morning to Sarvani at 9 am",
        ],
        "required_entities": ["contact", "message", "time"],
        "optional_entities": [],
    },

    "whatsapp_unread_count": {
        "description": "Check the number of unread WhatsApp chats or messages",
        "examples": [
            "check unread WhatsApp messages", "do I have any new messages on WhatsApp",
            "how many unread messages on WhatsApp", "any unread whatsapp chats",
        ],
        "required_entities": [],
        "optional_entities": [],
    },

    "whatsapp_emoji": {
        "description": "Send a specific emoji to a WhatsApp contact",
        "examples": [
            "send heart emoji to Mom", "send thumbs up to Teja on WhatsApp",
            "fire emoji to Sarvani",
        ],
        "required_entities": ["contact", "emoji"],
        "optional_entities": [],
    },

    "whatsapp_send_sticker": {
        "description": "Send a sticker by its 1-based index (e.g. 1st, 2nd, 3rd) in the stickers panel",
        "examples": [
            "send sticker number 3 to Mom", "send 3rd sticker to Sarvani on WhatsApp",
            "send sticker 2 to Rahul", "send sticker number 5",
            "send the 1st sticker on WhatsApp",
        ],
        "required_entities": ["index"],
        "optional_entities": ["contact"],
    },

    "whatsapp_screenshot": {
        "description": "Take a screenshot of the current screen and send it to a contact on WhatsApp",
        "examples": [
            "send screenshot to Mom on WhatsApp", "share my screen capture with Rahul",
            "send a screenshot to Teja",
        ],
        "required_entities": ["contact"],
        "optional_entities": [],
    },

    "whatsapp_voice_note": {
        "description": "Record and send a voice note to a WhatsApp contact",
        "examples": [
            "send a voice note to Mom", "record a voice note for Sarvani on WhatsApp",
            "send 10 second voice note to Rahul",
        ],
        "required_entities": ["contact"],
        "optional_entities": ["duration"],
    },

    "whatsapp_undo": {
        "description": "Delete or undo the last sent message in the active WhatsApp chat",
        "examples": [
            "undo my last WhatsApp message", "delete the last message on WhatsApp",
            "unsend message in WhatsApp",
        ],
        "required_entities": [],
        "optional_entities": [],
    },

    "whatsapp_group": {
        "description": "Send a WhatsApp message to a specific group",
        "examples": [
            "send message to group Family saying hello",
            "post hello to Class group on WhatsApp",
            "whatsapp group Teammates we are starting",
        ],
        "required_entities": ["group_name", "message"],
        "optional_entities": [],
    },

    "whatsapp_bulk": {
        "description": "Send the same WhatsApp message to multiple contacts",
        "examples": [
            "send hello to Mom, Dad and Bro on WhatsApp",
            "message Rahul and Teja saying I am running late",
            "send bulk message to Sarvani and Teja",
        ],
        "required_entities": ["contacts", "message"],
        "optional_entities": [],
    },

    "whatsapp_translate": {
        "description": "Translate a message into another language and send it to a contact on WhatsApp",
        "examples": [
            "translate hello to Spanish and send to Mom on WhatsApp",
            "send good morning translated to Telugu to Dad",
        ],
        "required_entities": ["contact", "message", "language"],
        "optional_entities": [],
    },

    # ══════════════════════════════════════════════════════════════
    #  WHATSAPP CALL CONTROL (Telegram)
    # ══════════════════════════════════════════════════════════════

    "whatsapp_call_accept": {
        "description": "Accept an incoming WhatsApp call",
        "examples": ["lift", "accept call", "answer call", "answer"],
        "required_entities": [],
        "optional_entities": [],
    },
    "whatsapp_call_decline": {
        "description": "Decline an incoming WhatsApp call",
        "examples": ["decline", "reject call", "hang up", "reject"],
        "required_entities": [],
        "optional_entities": [],
    },
    "whatsapp_call_status": {
        "description": "Get real-time WhatsApp call status",
        "examples": ["call status", "whatsapp call status"],
        "required_entities": [],
        "optional_entities": [],
    },
    
    "telegram_status": {
        "description": "Get telegram connection status",
        "examples": ["telegram status"],
        "required_entities": [],
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
    #  IMAGE GENERATION
    # ══════════════════════════════════════════════════════════════

    "generate_image": {
        "description": "Generate an AI image from a text description using Stable Diffusion or DALL-E",
        "examples": [
            "generate an image of a sunset over mountains",
            "create a picture of a cat in space",
            "draw a futuristic city skyline",
            "make an image of a dragon flying over a castle",
            "generate art of a cyberpunk samurai",
            "create a wallpaper of northern lights",
        ],
        "required_entities": ["prompt"],
        "optional_entities": [],
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

    "email_compose_ai": {
        "description": "Draft an email using AI",
        "examples": [
            "compose ai email to boss saying I'm sick",
            "write an email to John about the project status",
        ],
        "required_entities": ["recipient", "instruction"],
        "optional_entities": [],
    },

    "email_schedule": {
        "description": "Schedule an email to be sent later",
        "examples": [
            "schedule email to john saying hello at 5 pm",
            "send email to mom at 9 am saying good morning",
        ],
        "required_entities": ["recipient", "body", "time"],
        "optional_entities": ["subject"],
    },

    "email_undo": {
        "description": "Undo or unsend the last sent email",
        "examples": [
            "undo email", "unsend email", "undo last email",
        ],
        "required_entities": [],
        "optional_entities": [],
    },

    "email_check_unread": {
        "description": "Check the count or list of unread emails",
        "examples": [
            "check unread emails", "do I have unread emails",
        ],
        "required_entities": [],
        "optional_entities": [],
    },

    "email_search": {
        "description": "Search inbox for specific emails",
        "examples": [
            "search email for invoice", "find email about flight",
        ],
        "required_entities": ["query"],
        "optional_entities": [],
    },

    "email_reply": {
        "description": "Reply to an email",
        "examples": [
            "reply to john saying thanks", "reply to last email saying received",
        ],
        "required_entities": ["body"],
        "optional_entities": ["sender"],
    },

    "email_forward": {
        "description": "Forward an email to someone else",
        "examples": [
            "forward last email from john to mark", "forward email to boss",
        ],
        "required_entities": ["recipient"],
        "optional_entities": ["original_sender"],
    },

    "email_delete": {
        "description": "Delete an email",
        "examples": [
            "delete last email from john", "delete the last email",
        ],
        "required_entities": [],
        "optional_entities": ["sender"],
    },

    "email_mark_read": {
        "description": "Mark emails as read",
        "examples": [
            "mark all emails as read", "mark inbox as read",
        ],
        "required_entities": [],
        "optional_entities": [],
    },

    "email_brief": {
        "description": "Get a morning brief or summary of emails",
        "examples": [
            "read my morning email brief", "give me an email brief",
        ],
        "required_entities": [],
        "optional_entities": [],
    },

    "email_stats": {
        "description": "Get email statistics",
        "examples": [
            "email stats", "what are my email statistics",
        ],
        "required_entities": [],
        "optional_entities": [],
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
            "solve this in c++", "solve two sum in java",
            "solve this on my screen in python"
        ],
        "required_entities": [],
        "optional_entities": ["problem", "language"],
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

    # ══════════════════════════════════════════════════════════════
    #  WHATSAPP UI CONTROLS
    # ══════════════════════════════════════════════════════════════

    "whatsapp_open_emoji_panel": {
        "description": "Open the emoji panel / emoji picker in WhatsApp",
        "examples": [
            "open emoji panel", "show emojis", "emoji picker",
            "open emojis in WhatsApp", "show me the emoji panel",
        ],
        "required_entities": [],
        "optional_entities": [],
    },

    "whatsapp_open_sticker_panel": {
        "description": "Open the sticker panel in WhatsApp",
        "examples": [
            "open sticker panel", "show stickers", "sticker picker",
            "open stickers in WhatsApp", "show stickers panel",
        ],
        "required_entities": [],
        "optional_entities": [],
    },

    "whatsapp_focus_chat_input": {
        "description": "Focus the WhatsApp chat input box or text field",
        "examples": [
            "focus chat input", "click the text box",
            "move cursor to chat", "focus the input in WhatsApp",
        ],
        "required_entities": [],
        "optional_entities": [],
    },

    # ══════════════════════════════════════════════════════════════
    #  CURSOR / MOUSE CONTROL
    # ══════════════════════════════════════════════════════════════

    "move_cursor_to": {
        "description": "Move the mouse cursor to a named UI element visible on screen using OCR",
        "examples": [
            "move cursor to send button", "go to the search bar",
            "move mouse to close button", "cursor to the emoji button",
            "move cursor to the chart", "go to the settings icon",
        ],
        "required_entities": ["element"],
        "optional_entities": [],
    },

    "click_element": {
        "description": "Click a named UI element visible on screen by finding it via OCR",
        "examples": [
            "click on send", "click the submit button",
            "click on settings", "press the OK button",
            "click on the emoji button",
        ],
        "required_entities": ["element"],
        "optional_entities": [],
    },

    "move_cursor_direction": {
        "description": "Move the cursor in a direction (up/down/left/right) by a pixel amount",
        "examples": [
            "move cursor up", "move mouse down 200 pixels",
            "cursor left 50", "move cursor right",
        ],
        "required_entities": ["direction"],
        "optional_entities": ["pixels"],
    },

    # ══════════════════════════════════════════════════════════════
    #  KNOWLEDGE BASE / RAG
    # ══════════════════════════════════════════════════════════════

    "knowledge_ingest": {
        "description": "Learn/ingest a file or folder into JARVIS's knowledge base so it can answer questions about it",
        "examples": [
            "learn this file notes.pdf", "learn my notes folder",
            "ingest file README.md", "read file report.pdf",
            "learn my documents folder", "learn my desktop folder",
            "memorize this file", "scan my projects folder",
        ],
        "required_entities": [],
        "optional_entities": ["file_path", "folder_path"],
    },

    "knowledge_search": {
        "description": "Search through ingested documents in the knowledge base",
        "examples": [
            "search my documents for transformers",
            "find in my notes about neural networks",
            "search knowledge base for API keys",
            "look up machine learning in my files",
        ],
        "required_entities": ["query"],
        "optional_entities": [],
    },

    "knowledge_ask": {
        "description": "Ask a question that should be answered from ingested documents and notes",
        "examples": [
            "what do my notes say about neural networks",
            "from my documents explain transformers",
            "according to my files what is the tech stack",
            "based on my notes how does attention work",
        ],
        "required_entities": ["query"],
        "optional_entities": [],
    },

    "knowledge_stats": {
        "description": "Show knowledge base statistics — how many documents and chunks are stored",
        "examples": [
            "how many documents do you know",
            "knowledge base stats", "what files have you learned",
            "what do you know about my documents",
        ],
        "required_entities": [],
        "optional_entities": [],
    },

    "knowledge_clear": {
        "description": "Clear or forget all documents from the knowledge base",
        "examples": [
            "forget all documents", "clear knowledge base",
            "reset knowledge base", "forget my documents",
        ],
        "required_entities": [],
        "optional_entities": [],
    },

    # ══════════════════════════════════════════════════════════════
    #  PROBLEM SOLVER / CODING
    # ══════════════════════════════════════════════════════════════

    "explain_from_screen": {
        "description": "Explain the coding problem currently visible on the screen",
        "examples": [
            "explain the problem on my screen", "explain this problem",
            "what does this problem mean",
        ],
        "required_entities": [],
        "optional_entities": [],
    },

    "explain_solution": {
        "description": "Explain the solution to a coding problem",
        "examples": [
            "explain the solution", "how does the solution work",
        ],
        "required_entities": [],
        "optional_entities": [],
    },

    "paste_solution": {
        "description": "Paste the generated solution code into the active window",
        "examples": [
            "paste the solution", "paste it", "type the solution here",
        ],
        "required_entities": [],
        "optional_entities": [],
    },

    "optimize_code": {
        "description": "Optimize the currently visible code for better time/space complexity",
        "examples": [
            "optimize this code", "make this code faster",
        ],
        "required_entities": [],
        "optional_entities": [],
    },

    "debug_code": {
        "description": "Debug the code on the screen and find errors",
        "examples": [
            "debug this code", "find the bug in my code",
        ],
        "required_entities": [],
        "optional_entities": [],
    },

    "get_complexity": {
        "description": "Get the time and space complexity of the current or last solution",
        "examples": [
            "what is the complexity", "time and space complexity",
        ],
        "required_entities": [],
        "optional_entities": [],
    },

    "show_last_solution": {
        "description": "Show the last generated solution again",
        "examples": [
            "show the last solution", "show me the solution again",
        ],
        "required_entities": [],
        "optional_entities": [],
    },

    "explain_last_problem": {
        "description": "Explain the last coding problem that was solved",
        "examples": [
            "explain the last problem", "what was the last problem",
        ],
        "required_entities": [],
        "optional_entities": [],
    },

    # ══════════════════════════════════════════════════════════════
    #  SYSTEM & INTERNAL
    # ══════════════════════════════════════════════════════════════

    "change_voice": {
        "description": "Change JARVIS's text-to-speech voice",
        "examples": [
            "change your voice", "use a different voice",
        ],
        "required_entities": [],
        "optional_entities": ["voice_name"],
    },

    "_clarify": {
        "description": "Internal intent used when JARVIS needs clarification",
        "examples": [],
        "required_entities": [],
        "optional_entities": [],
        "internal_only": True,
    },

    "stop": {
        "description": "Stop current execution or speaking",
        "examples": [
            "stop", "quiet", "shut up",
        ],
        "required_entities": [],
        "optional_entities": [],
        "internal_only": True,
    },

    "send_typed": {
        "description": "Send typed command (internal logic)",
        "examples": [],
        "required_entities": [],
        "optional_entities": [],
        "internal_only": True,
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
