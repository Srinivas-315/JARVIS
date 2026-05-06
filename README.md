# 🤖 JARVIS — Just A Rather Very Intelligent System `v3.0`

> A voice-controlled AI personal assistant that runs on your Windows laptop — like Iron Man's JARVIS, built for real life.

---

## ⚡ Quick Start

### Step 1 — Install everything (run once):
```powershell
cd "C:\Users\srini\OneDrive\Attachments\Desktop\PROJECTS\JARVIS"
python setup.py
```

### Step 2 — Test your API connections:
```powershell
python test_connection.py
```

### Step 3 — Launch JARVIS:
```powershell
python main.py
```

### Quick test (no microphone needed):
```powershell
python main.py --test
```

---

## 🔑 API Keys Setup

Open `.env` and fill in your keys:

| Key | Where to Get |
|-----|-------------|
| `GEMINI_API_KEY` | [aistudio.google.com](https://aistudio.google.com) → "Get API Key" (starts with `AIzaSy...`) |
| `WEATHER_API_KEY` | [openweathermap.org/api](https://openweathermap.org/api) → Free plan |
| `NEWS_API_KEY` | [newsapi.org](https://newsapi.org) → Free plan |
| `GMAIL_APP_PASSWORD` | Google Account → Security → 2FA → App Passwords |

> ⚠️ **Important**: Gemini keys start with `AIzaSy...` — NOT `AQ.`

---

## 🗣️ Voice Commands

### System Control
| Say | Action |
|-----|--------|
| "Open Chrome" | Opens Chrome browser |
| "Close Spotify" | Kills Spotify process |
| "Volume up / down" | Adjusts system volume |
| "Take a screenshot" | Saves screenshot to Desktop |
| "Shutdown in 5 minutes" | Schedules shutdown |
| "Restart my laptop" | Restarts PC |

### Information
| Say | Action |
|-----|--------|
| "What's the weather?" | Current weather for your city |
| "Latest tech news" | Top tech headlines |
| "What is black holes?" | Wikipedia summary |
| "What time is it?" | Current time |

### Internet
| Say | Action |
|-----|--------|
| "Search for Python tutorials" | Google search |
| "Play Bollywood songs on YouTube" | YouTube playback |
| "Find laptops on Amazon" | Amazon product search |

### Files
| Say | Action |
|-----|--------|
| "Write a note: buy groceries" | Creates a text note on Desktop |
| "Open notepad" | Opens Notepad app |
| "List my desktop files" | Shows Desktop contents |

### Memory & Time
| Say | Action |
|-----|--------|
| "Remind me to drink water in 30 minutes" | Sets a reminder |
| "Set a timer for 5 minutes" | Countdown timer |
| "Reset conversation" | Clears chat context |

### Vision AI
| Say | Action |
|-----|--------|
| "What's on my screen?" | Gemini analyzes your screen |
| "Read text on screen" | OCR on current screen |

---

## 📁 Project Structure

```
JARVIS/
├── main.py              ← 🎯 Entry point
├── setup.py             ← ⚙️  One-click installer
├── test_connection.py   ← 🔍 Test API keys
├── config.py            ← ⚙️  Settings
├── .env                 ← 🔑 API keys (PRIVATE)
│
├── voice/
│   ├── listener.py      ← 🎤 Whisper mic input
│   ├── speaker.py       ← 🔊 pyttsx3 TTS output
│   └── wake_word.py     ← 👂 "Hey Jarvis" detection
│
├── brain/
│   ├── gemini_handler.py ← 🧠 Gemini 1.5 Flash
│   ├── intent_parser.py  ← 🗂️  Routes commands
│   └── vision_handler.py ← 👁️  Screen/image AI
│
├── skills/
│   ├── apps.py          ← Open/close 40+ apps
│   ├── system.py        ← Volume, brightness, power
│   ├── browser.py       ← Google, YouTube, Wikipedia
│   ├── files.py         ← File operations
│   ├── weather.py       ← Weather API
│   ├── news.py          ← News headlines
│   ├── reminder.py      ← Timers & reminders
│   └── email_handler.py ← Gmail send/read
│
├── memory/
│   ├── database.py      ← SQLite setup
│   ├── chat_history.py  ← Conversation memory
│   └── user_prefs.py    ← User preferences
│
└── utils/
    ├── logger.py        ← Colored console logging
    └── helpers.py       ← Common utilities
```

---

## 🗺️ Build Phases

| Phase | Feature | Status |
|-------|---------|--------|
| 1 | Voice + Gemini AI Brain | ✅ Done |
| 2 | System Control | ✅ Done |
| 3 | Internet & Info | ✅ Done |
| 4 | Email & Communication | ✅ Done |
| 5 | Vision AI | ✅ Done |
| 6 | Browser Automation | ✅ Done |
| 7 | Memory & Personalization | ✅ Done |
| 8 | "Hey Jarvis" Wake Word | ✅ Done |
| 9 | Premium GUI (Iron Man HUD) | ✅ Done |
| 10 | Final Polish & 120-Test Suite | ✅ Done |

---

## 🛠️ Tech Stack

| Component | Technology |
|-----------|-----------|
| AI Brain | Gemini 1.5 Flash (free, 1500/day) |
| Voice Input | OpenAI Whisper (local, offline) |
| Voice Output | pyttsx3 (local, offline) |
| Wake Word | OpenWakeWord (free, no signup) |
| Browser | Playwright + webbrowser |
| System | pyautogui + psutil + subprocess |
| Memory | SQLite (built-in) |
| Notifications | plyer |
| GUI | PyQt5 — Iron Man HUD (Arc Reactor, HUD panels, live stats) |

---

## 📝 Notes

- **First run** downloads Whisper `base` model (~145MB) — wait for it
- **Voice speed**: Adjust `VOICE_RATE` in `.env` (default: 180 wpm)
- **Whisper model**: Change `WHISPER_MODEL` in `.env` to `tiny` for speed or `small` for accuracy
- **City**: Change `USER_CITY` in `.env` for correct weather

---

*Built with ❤️ by Srini | Powered by Google Gemini + OpenAI Whisper*
