"""
JARVIS — main.py
🤖 Main entry point. The brain that ties everything together.

Flow:
    Boot → Initialize all modules → Greet user
    Loop: Listen → Parse intent → Execute skill → Speak response → Repeat
"""

import os
import sys

# ─── FIX: Force UTF-8 console encoding on Windows ────────────
# Without this, emojis/Unicode chars crash with UnicodeEncodeError
# because Windows defaults to cp1252 encoding.
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass  # Older Python or non-standard stream

import re
import time
from datetime import datetime

# ─── Core ────────────────────────────────────────────────────
from pathlib import Path

import config
from brain.autocorrect import autocorrect
from brain.correction_learner import CorrectionLearner

# ─── Brain ───────────────────────────────────────────────────
from brain.gemini_handler import GeminiHandler
from brain.intent_parser import (
    extract_app_name,
    extract_name_and_message,
    extract_search_query,
    parse_intent,
)

# ─── Language ────────────────────────────────────────────────
from brain.language_handler import LanguageHandler
from brain.vision_handler import VisionHandler

# ─── Emotion / Personality / Memory ─────────────────────────
from jarvis.emotion_engine import EmotionEngine
from jarvis.memory_system import MemorySystem
from jarvis.personality import PersonalityLayer
from memory.chat_history import ChatHistory

# ─── Memory ──────────────────────────────────────────────────
from memory.database import initialize_db
from memory.user_prefs import UserPrefs
from skills.app_control import AppControl  # ← NEW
from skills.browser import BrowserSkill
from skills.calendar_skill import CalendarSkill
from skills.clipboard_ai import ClipboardSkill
from skills.code_runner import CodeRunner
from skills.email_handler import EmailHandler
from skills.files import FileSkill
from skills.media import MediaController
from skills.news import NewsSkill
from skills.reminder import ReminderSkill
from skills.screen_control import ScreenController
from skills.shopping import ShoppingSkill

# ─── Skills ──────────────────────────────────────────────────
from skills.system import SystemController
from skills.weather import WeatherSkill
from skills.web_search import WebSearch
from skills.whatsapp import WhatsAppSkill
from skills.wolfram import WolframSkill, is_wolfram_query
from utils.helpers import clean_text, wait_animation

# ─── Core modules ────────────────────────────────────────────
from utils.logger import log
from voice.listener import Listener

# ─── Voice ───────────────────────────────────────────────────
from voice.speaker import Speaker
from voice.wake_word import WakeWordDetector

# ═══════════════════════════════════════════════════════════════
#  JARVIS Core
# ═══════════════════════════════════════════════════════════════


class JARVIS:
    """The main JARVIS AI assistant controller."""

    def __init__(self):
        import threading

        self._running = True
        self._stop_event = threading.Event()  # Set this to cancel all tasks
        self._session = datetime.now().strftime("%Y%m%d_%H%M%S")

        # ── Initialize database ───────────────────────────────
        log.info("Initializing JARVIS memory system...")
        initialize_db()

        # ── Validate API Configuration ─────────────────────────
        missing_keys = config.validate_api_keys()
        if missing_keys:
            log.warning("⚠️  Missing or empty API keys:")
            for key in missing_keys:
                log.warning(f"   - {key}")
            disabled = config.get_disabled_features()
            if disabled:
                log.warning(f"   ⚠️  Disabled features: {', '.join(disabled)}")
        else:
            log.info("✅ All API keys configured")

        # ── Load preferences ──────────────────────────────────
        self.prefs = UserPrefs()
        self.history = ChatHistory()

        # ── Initialize voice ──────────────────────────────────
        log.info("Starting voice systems...")
        self.speaker = Speaker()
        self.listener = Listener()  # Downloads Whisper on first run
        self.listener._speaker = self.speaker  # Link so listener waits for speech

        # ── Language handler ──────────────────────────────────
        self.lang = LanguageHandler()
        self.speaker.language_handler = self.lang  # Wire to speaker
        self.listener._jarvis = self  # Wire to listener for language-aware recognition

        # ── Initialize AI brain ───────────────────────────────
        log.info("Connecting to Gemini AI...")
        self.gemini = GeminiHandler()
        self.vision = VisionHandler()
        # Object recognizer — 100% local ML, no API needed
        try:
            from vision.object_recognizer import ObjectRecognizer as _ObjRec

            self.obj_recog = _ObjRec()
        except Exception as _e:
            log.warning(f"Object recognizer unavailable: {_e}")
            self.obj_recog = None

        # NOTE: OCR is handled INSIDE obj_recog automatically.
        # Do NOT create a separate OCRReader here — causes double-loading.
        self.ocr = getattr(self.obj_recog, "_ocr", None)  # reuse same instance

        # ── Initialize skills ─────────────────────────────────
        log.info("Loading skills...")

        self.system = SystemController()
        self.browser = BrowserSkill()
        self.files = FileSkill()
        self.weather = WeatherSkill()
        self.news = NewsSkill()
        self.reminder = ReminderSkill(speak_callback=self._speak)
        self.email = EmailHandler()
        self.whatsapp = WhatsAppSkill()
        self.wolfram = WolframSkill()
        self.shopping = ShoppingSkill()
        self.media = MediaController()
        self.screen = ScreenController()
        self.clipboard = ClipboardSkill()

        # Start reminder scheduler in background
        self.reminder.start_scheduler()

        # Task chains (needs self reference)
        from skills.task_chain import TaskChain

        self.chain = TaskChain(self)

        # Learning from corrections
        self.corrector = CorrectionLearner()

        # Code Runner
        self.code_runner = CodeRunner()

        # VS Code Code Writer (voice → Gemini → VS Code with animation)
        try:
            from skills.code_writer import VSCodeWriter

            self.code_writer = VSCodeWriter(gemini_handler=self.gemini)
            log.info(
                "  💻 VSCodeWriter ready — say 'write a Python function...' to code!"
            )
        except Exception as _cw_err:
            log.warning(f"VSCodeWriter unavailable: {_cw_err}")
            self.code_writer = None

        # Problem Solver (LeetCode, DSA, debugging)
        try:
            from skills.problem_solver import ProblemSolver

            self.problem_solver = ProblemSolver(
                gemini_handler=self.gemini,
                vision_handler=self.vision,
            )
            log.info(
                "  🧠 ProblemSolver ready — say 'solve this' on any LeetCode problem!"
            )
        except Exception as _ps_err:
            log.warning(f"ProblemSolver unavailable: {_ps_err}")
            self.problem_solver = None

        # Real-time Web Search
        self.web_search = WebSearch()

        # Calendar
        self.calendar = CalendarSkill()

        # Advanced App / Window / Smart-Mode Control
        self.app_ctrl = AppControl()
        self.app_ctrl.start_usage_tracking()

        # 📞 Call Monitor — announces incoming calls & listens for answer/decline
        try:
            from skills.call_monitor import CallMonitor

            self.call_monitor = CallMonitor(
                speak_fn=self._speak,
                listen_fn=lambda timeout=6: self.listener.listen(timeout=timeout),
            )
            self.call_monitor.start()
            log.info("📞 Call monitor active — WhatsApp, Phone Link, Skype, Teams")
        except Exception as _ce:
            log.warning(f"Call monitor unavailable: {_ce}")
            self.call_monitor = None

        # 🔔 Notification Watcher — always-on background monitor for ALL Windows toasts
        try:
            from skills.notification_watcher import NotificationWatcher

            self.notif_watcher = NotificationWatcher(
                speak_fn=self._speak,
                is_speaking_fn=lambda: self.speaker.is_speaking,
            )
            self.notif_watcher.start()
            log.info("🔔 Notification watcher active — monitoring all Windows toasts")
        except Exception as _nw_err:
            log.warning(f"Notification watcher unavailable: {_nw_err}")
            self.notif_watcher = None

        # ── Face Login (optional, skip if not enrolled) ─────────
        try:
            from vision.face_login import FaceLogin

            self.face_login = FaceLogin()
        except Exception:
            self.face_login = None

        log.info("=" * 50)
        log.info("  🤖 JARVIS is ONLINE and ready!")
        log.info("=" * 50)

        # ── Emotion / Personality / Memory ────────────────────
        self.emotion = EmotionEngine()
        self.personality = PersonalityLayer(self.emotion)
        self.memory = MemorySystem()
        self.memory.increment_session()
        log.info("  🧠 Emotion engine + memory system online.")

        # ── Personal Memory — load at startup so name is ready ──
        try:
            from memory.personal_memory import PersonalMemory

            self._personal_mem = PersonalMemory()
            saved_name = self._personal_mem.get("name")
            if saved_name:
                self.prefs.name = saved_name
                config.USER_NAME = saved_name
                log.info(f"  📝 Loaded saved name from memory: {saved_name}")
        except Exception as _pm_init_err:
            self._personal_mem = None
            log.warning(f"PersonalMemory init error: {_pm_init_err}")

        # ── Wire MemorySystem ↔ PersonalMemory ↔ GeminiHandler ──
        # Makes EVERY AI call context-aware: name, college, city, etc.
        # are injected into the system prompt automatically, surviving
        # all restarts. This is the key integration point.
        try:
            if self._personal_mem:
                self.memory.set_personal_memory(self._personal_mem)
            self.gemini.set_memory_system(self.memory)
            log.info("  🔗 Memory fully wired — context injected in every AI call")
        except Exception as _wire_err:
            log.warning(f"Memory wiring error: {_wire_err}")

        # ── Register graceful shutdown ────────────────────────
        import atexit

        atexit.register(self.shutdown)

    # ─── Global STOP ──────────────────────────────────────────
    def _cancel_all_tasks(self):
        """Cancel everything JARVIS is doing right now."""
        # 1. Set stop flag (all tasks check this)
        self._stop_event.set()

        # 2. Stop speaking immediately
        try:
            self.speaker.stop()
        except Exception:
            pass

        # 3. Cancel pending code confirmation
        try:
            if self.code_runner._pending_confirmation:
                self.code_runner.cancel()
        except Exception:
            pass

        # 3b. Stop any in-progress code writing / VS Code typing
        try:
            if self.code_writer:
                self.code_writer.stop_writing()
        except Exception:
            pass

        # 4. Clear reminder queue
        try:
            self.reminder.clear_all()
        except Exception:
            pass

        # 5. Reset stop event so next command works normally
        import threading

        def _reset():
            import time

            time.sleep(0.5)
            self._stop_event.clear()

        threading.Thread(target=_reset, daemon=True).start()

    def shutdown(self):
        """
        Graceful shutdown — clean up all resources.
        Called on exit (Ctrl+C) or via atexit.
        """
        log.info("🛑 JARVIS shutting down...")

        # 1. Stop main loop
        self._running = False

        # 2. Cancel all active tasks
        self._cancel_all_tasks()

        # 3. Stop scheduler
        try:
            self.reminder.stop_scheduler()
            log.info("  ✓ Reminder scheduler stopped")
        except Exception as e:
            log.debug(f"Reminder scheduler cleanup: {e}")

        # 4. Stop wake word detector if active
        try:
            if hasattr(self, "wake_detector") and self.wake_detector:
                self.wake_detector.stop()
                log.info("  ✓ Wake word detector stopped")
        except Exception as e:
            log.debug(f"Wake detector cleanup: {e}")

        # 5. Stop call monitor if active
        try:
            if hasattr(self, "call_monitor") and self.call_monitor:
                self.call_monitor.stop()
                log.info("  ✓ Call monitor stopped")
        except Exception as e:
            log.debug(f"Call monitor cleanup: {e}")

        # 5b. Stop notification watcher if active
        try:
            if hasattr(self, "notif_watcher") and self.notif_watcher:
                self.notif_watcher.stop()
                log.info("  ✓ Notification watcher stopped")
        except Exception as e:
            log.debug(f"Notification watcher cleanup: {e}")

        # 6. Stop app usage tracking
        try:
            self.app_ctrl.stop_usage_tracking()
            log.info("  ✓ App tracking stopped")
        except Exception as e:
            log.debug(f"App tracking cleanup: {e}")

        # 7. Close database connection
        try:
            from memory.database import close_connection

            close_connection()
            log.info("  ✓ Database connection closed")
        except Exception as e:
            log.debug(f"Database cleanup: {e}")

        # 8. Stop speaker and listener threads
        try:
            self.speaker.stop()
            log.info("  ✓ Speaker stopped")
        except Exception as e:
            log.debug(f"Speaker cleanup: {e}")

        # 9. Close any open processes
        try:
            import os

            import psutil

            current = psutil.Process(os.getpid())
            for child in current.children(recursive=True):
                try:
                    child.terminate()
                except Exception:
                    pass
            log.info("  ✓ Child processes cleaned up")
        except Exception as e:
            log.debug(f"Child process cleanup: {e}")

        log.info("✅ JARVIS shutdown complete.")

        log.info("⏹️  JARVIS stopped all tasks.")

    @property
    def is_stopped(self) -> bool:
        """Check if stop was requested — use in long-running skills."""
        return self._stop_event.is_set()

    # ─── Speaking (interruptible) ─────────────────────────────────
    def _speak(self, text: str):
        """Speak response. Stops immediately if stop event is set."""
        if self._stop_event.is_set():
            return  # Don't speak if stopped
        import threading

        speak_thread = threading.Thread(
            target=self.speaker.speak, args=(text,), daemon=True
        )
        speak_thread.start()

        interrupt_words = [
            "calm down",
            "stop",
            "shut up",
            "quiet",
            "enough",
            "ok stop",
            "okay stop",
            "be quiet",
            "silence",
            "hush",
        ]

        mic = getattr(self, "_interrupt_mic", None)
        recognizer = getattr(self, "_interrupt_recognizer", None)

        if mic is None or recognizer is None:
            speak_thread.join()
            return

        try:
            import speech_recognition as sr

            while speak_thread.is_alive():
                try:
                    with mic as source:
                        audio = recognizer.listen(
                            source, timeout=0.5, phrase_time_limit=2
                        )
                    heard = recognizer.recognize_google(audio).lower().strip()
                    if any(w in heard for w in interrupt_words):
                        self.speaker.stop()
                        print("\033[93m⚡ JARVIS interrupted.\033[0m")
                        return
                except sr.WaitTimeoutError:
                    continue
                except (sr.UnknownValueError, sr.RequestError):
                    continue
                except Exception:
                    break
        except Exception:
            speak_thread.join()

    # ─── Greeting ────────────────────────────────────────────
    def greet(self):
        """Warm, natural startup greeting — feels like ChatGPT/Gemini, not a robot."""
        import random
        from datetime import date

        hour = datetime.now().hour
        name = self.prefs.name or "sir"
        today = date.today().strftime("%A, %d %B")

        # ── Pick a natural, varied greeting based on time ────
        if 5 <= hour < 12:
            greetings = [
                f"Good morning, {name}! Hope you slept well. Today is {today} — what are we starting with?",
                f"Morning, {name}! I'm all set and ready to go. What's first?",
                f"Good morning! It's {today}. What can I help you with today, {name}?",
                f"Rise and shine, {name}! I've been up all night. What do you need?",
            ]
        elif 12 <= hour < 17:
            greetings = [
                f"Hey {name}! Good afternoon. What can I do for you?",
                f"Afternoon, {name}. It's {today} — how's the day going? What do you need?",
                f"Good afternoon! I'm here and ready. What's on your mind, {name}?",
            ]
        elif 17 <= hour < 21:
            greetings = [
                f"Good evening, {name}! How was your day? What can I help with?",
                f"Evening, {name}. I'm all ears — what do you need?",
                f"Hey {name}, good evening! It's {today}. Ready when you are.",
            ]
        else:
            greetings = [
                f"Working late again, {name}? I don't sleep, so I'm here. What do you need?",
                f"Hey {name}! Late night session on {today}. What are we doing?",
                f"Still up, {name}? I'm with you. What can I help with?",
            ]

        self._speak(random.choice(greetings))

    def process_command(self, text: str) -> str:
        """
        Public entry point — crash-proof wrapper around _process_command_inner.
        Catches ALL exceptions, logs to crash_log.txt, and keeps JARVIS running.
        Emotion + memory are applied here so they always run regardless of intent.
        """
        try:
            # ── 0. STOP — HIGHEST PRIORITY ────────────────────────────
            _stop_words = [
                "stop",
                "cancel",
                "shut up",
                "be quiet",
                "enough",
                "silence",
                "abort",
                "halt",
            ]
            if any(
                text.lower().strip() == w or text.lower().strip().startswith(w + " ")
                for w in _stop_words
            ):
                self.speaker.speak("Stopping everything, sir.")
                self._cancel_all_tasks()
                return ""

            # ── 1. Update emotion from user input ────────────────────
            emotion = self.emotion.detect_and_update(text)

            # ── 2. Check if user is teaching JARVIS something ────
            learn_msg = self.memory.process_user_input(text)
            if learn_msg:
                self._speak(learn_msg)
                return ""

            # ── 3. Memory recall / search / stats commands ────────
            text_lower = text.lower().strip()

            # Full recall — "what do you know about me?"
            if any(
                p in text_lower
                for p in [
                    "what do you remember",
                    "what do you know about me",
                    "what have you learned",
                    "tell me what you know",
                    "what have you stored",
                    "what have you saved",
                    "what have you learned about me",
                ]
            ):
                recall = self.memory.recall_all()
                self._speak(recall)
                return ""

            # Memory statistics — "how many times have we talked?"
            if any(
                p in text_lower
                for p in [
                    "how many conversations",
                    "how many times have we talked",
                    "memory stats",
                    "conversation count",
                    "how much do you remember",
                    "how long have we talked",
                ]
            ):
                self._speak(self.memory.get_stats_spoken())
                return ""

            # Search conversation history — "what did we talk about Python?"
            _mem_search_triggers = [
                "what did we talk about",
                "search my memory",
                "search memory for",
                "do you remember when",
                "did we discuss",
                "have we talked about",
                "look up in memory",
                "find in my history",
            ]
            for _st in _mem_search_triggers:
                if _st in text_lower:
                    _q = text_lower.replace(_st, "").strip().strip("?").strip()
                    if _q:
                        _result = self.memory.search_history(_q)
                        self._speak(_result)
                        return ""
                    break

            # ── 4. Route to inner handler ─────────────────────────
            raw_response = self._process_command_inner(text)

            # ── 5. Wrap with personality ──────────────────────────
            if raw_response:
                styled = self.personality.wrap(raw_response, emotion, text)
                # Save exchange to permanent memory (SQLite + short-term RAM)
                self.memory.add_exchange(text, styled, session_id=self._session)
                # Update emotion from the response content
                self.emotion.update_from_response(styled)
                return styled

            return raw_response

        except Exception as exc:
            import datetime
            import traceback

            tb = traceback.format_exc()
            crash_file = Path(__file__).parent / "data" / "crash_log.txt"
            crash_file.parent.mkdir(parents=True, exist_ok=True)
            with open(crash_file, "a", encoding="utf-8") as f:
                f.write(f"\n{'=' * 60}\n")
                f.write(f"CRASH at {datetime.datetime.now()}\n")
                f.write(f"Command: {text!r}\n")
                f.write(tb)
            print(
                f"\n\033[91m💥 JARVIS caught a crash! Saved to data/crash_log.txt\033[0m"
            )
            print(f"\033[91m   Error: {exc}\033[0m\n")
            try:
                self._speak(
                    "Sorry, something went wrong on that one. I'm still here though!"
                )
            except Exception:
                pass
            return ""

    def _process_command_inner(self, text: str) -> str:
        """
        Takes user voice input, routes to correct skill,
        speaks immediately, executes, then returns response.
        """
        if not text or not text.strip():
            return ""

        # ── Auto-correct misheard words ───────────────────────
        text = autocorrect(text)
        text_lower = text.lower().strip()

        # ── Normalize Unicode apostrophes & quotes ────────────
        # Google STT often returns curly apostrophes (U+2019 ') instead of
        # straight ones (U+0027 '). This causes PRIORITY_VISION checks like
        # "what's in my hand" to silently fail, falling through to Wolfram/Gemini.
        # Fix: normalise ALL quote variants to ASCII equivalents BEFORE any check.
        text_lower = (
            text_lower.replace("\u2019", "'")  # RIGHT SINGLE QUOTATION MARK  '
            .replace("\u2018", "'")  # LEFT  SINGLE QUOTATION MARK  '
            .replace("\u02bc", "'")  # MODIFIER LETTER APOSTROPHE   ʼ
            .replace("\u0060", "'")  # GRAVE ACCENT                  `
            .replace("\u00b4", "'")  # ACUTE ACCENT                  ´
            .replace("\u201c", '"')  # LEFT  DOUBLE QUOTATION MARK  "
            .replace("\u201d", '"')  # RIGHT DOUBLE QUOTATION MARK  "
        )
        # Also patch the original text so downstream handlers get clean text
        text = (
            text.replace("\u2019", "'")
            .replace("\u2018", "'")
            .replace("\u02bc", "'")
            .replace("\u0060", "'")
            .replace("\u00b4", "'")
            .replace("\u201c", '"')
            .replace("\u201d", '"')
        )

        # ══ PRIORITY: Camera / Vision commands ══════════════
        # Checked FIRST — never fall through to LLM/Wolfram
        _PRIORITY_VISION = [
            # ── Hand / holding (most important — were breaking due to apostrophe) ──
            "what's in my hand",
            "what is in my hand",
            "whats in my hand",
            "what am i holding",
            "what do i have",
            "what do i hold",
            "in my hand",
            "am i holding",
            # ── Object identification ─────────────────────────────────────────────
            "identify this",
            "recognize this",
            "what is this",
            "what's this",
            "whats this",
            "what is that",
            "what's that",
            "whats that",
            "look at this",
            "scan this",
            "analyze this",
            "check this out",
            "see this",
            "tell me what this is",
            "can you identify",
            "what do you think this is",
            "what am i showing",
            "use camera",
            "take a look at this",
            "look at the camera",
            "look through the camera",
            "what can you see",
            "look around",
            # ── Extra safety aliases so apostrophe variants always match ──────────
            "whats in my",
            "what's in my",
        ]
        _SCREEN_VISION = [
            "what's on my screen",
            "what is on my screen",
            "what's on screen",
            "look at my screen",
            "describe my screen",
            "what am i looking at",
            "what's open on screen",
            "what app is this",
        ]
        _READ_VISION = [
            "read this",
            "read that",
            "what does this say",
            "what does that say",
            "read the text",
            "what is written",
            "read this for me",
            "read the board",
            "read the whiteboard",
            "read this sign",
        ]
        if any(t in text_lower for t in _SCREEN_VISION):
            self._speak("Looking at your screen...")
            _vis_resp = self.vision.what_is_on_screen()
            self._speak(_vis_resp)
            return ""
        if any(t in text_lower for t in _READ_VISION):
            self._speak("Reading...")
            _vis_resp = self.vision.read_text_from_camera()
            self._speak(_vis_resp)
            return ""
        if any(t in text_lower for t in _PRIORITY_VISION):
            if any(
                t in text_lower for t in ["holding", "hand", "have", "showing", "in my"]
            ):
                self._speak("Let me take a look, sir. Hold it up to the camera.")
                _vis_resp = self.vision.what_am_i_holding()
            else:
                self._speak("Looking through the camera now...")
                _vis_resp = self.vision.identify_objects()
            if _vis_resp:
                self._speak(_vis_resp)
            else:
                self._speak(
                    "Camera isn't responding, sir. "
                    "Check it's connected and not in use by another app like Teams or Zoom."
                )
            return ""

        stdlib_re = re  # Alias to avoid Python scoping issue with local imports

        # ── Greeting Detection ────────────────────────────────
        # When user says "Hey JARVIS", "Hi", "Hello", "Good morning"
        # respond warmly instead of routing to intent parser
        _greet_triggers = [
            "hey jarvis",
            "hi jarvis",
            "hello jarvis",
            "yo jarvis",
            "hi",
            "hello",
            "hey",
            "good morning",
            "good evening",
            "good afternoon",
            "good night",
            "what's up",
            "wassup",
            "how are you",
            "how r u",
            "how are u",
            "you there",
            "are you there",
            "jarvis hello",
            "jarvis hi",
        ]
        _tstrip = text_lower.rstrip("!?. ")
        # FIX: use startswith so "hello jar" / "hi there" etc. also match
        _is_greeting = (
            _tstrip in _greet_triggers
            or any(_tstrip.startswith(t) for t in _greet_triggers)
            or any(
                t in _tstrip
                for t in ["hey jarvis", "hi jarvis", "hello jarvis", "yo jarvis"]
            )
        )
        if _is_greeting:
            import random as _rg

            _h = datetime.now().hour
            _n = self.prefs.name
            if 5 <= _h < 12:
                _greets = [
                    f"Good morning, {_n}! How can I help you today?",
                    f"Morning! Hope you're having a great start to the day, {_n}. What do you need?",
                    f"Good morning, {_n}. I'm ready whenever you are.",
                ]
            elif 12 <= _h < 17:
                _greets = [
                    f"Hey {_n}! What's on your mind?",
                    f"Hello! What can I do for you this afternoon, {_n}?",
                    f"Hi {_n}! Good to hear from you. What do you need?",
                ]
            elif 17 <= _h < 21:
                _greets = [
                    f"Good evening, {_n}! How was your day?",
                    f"Evening! What can I help you with, {_n}?",
                    f"Hey {_n}! Good evening. What do you need?",
                ]
            else:
                _greets = [
                    f"Still going, {_n}? I'm here whenever you need me.",
                    f"Late night session! What can I do for you, {_n}?",
                    f"Hey {_n}! I never sleep — what do you need?",
                ]
            _reply = _rg.choice(_greets)
            self._speak(_reply)
            return ""

        # Must check BEFORE intent parsing so corrections are never misrouted
        if self.corrector.is_correction(text):
            response = self.corrector.learn(text)
            self._speak(response)
            return ""

        # ── Personal Memory — NO LLM, instant file-based ──────
        # "my name is X", "remember I am X", "what's my name" etc.
        try:
            if self._personal_mem is None:
                from memory.personal_memory import PersonalMemory

                self._personal_mem = PersonalMemory()

            # Try recall first (so "my name" doesn't trigger learn)
            recall = self._personal_mem.try_recall(text)
            if recall:
                self._speak(recall)
                return ""

            # Try learn
            learned = self._personal_mem.try_learn(text)
            if learned:
                # Sync name across ALL stores so it persists across restarts
                if "name" in text.lower():
                    saved_name = self._personal_mem.get("name")
                    if saved_name:
                        # 1. Update UserPrefs (SQLite)
                        self.prefs.name = saved_name
                        # 2. Update RAM config so greetings use it immediately
                        config.USER_NAME = saved_name
                        # 3. Persist to .env so it survives full restarts
                        try:
                            from pathlib import Path as _Path

                            env_path = _Path(__file__).parent / ".env"
                            if env_path.exists():
                                lines = env_path.read_text(
                                    encoding="utf-8"
                                ).splitlines()
                                new_lines = []
                                found = False
                                for line in lines:
                                    if line.startswith("USER_NAME="):
                                        new_lines.append(f"USER_NAME={saved_name}")
                                        found = True
                                    else:
                                        new_lines.append(line)
                                if not found:
                                    new_lines.append(f"USER_NAME={saved_name}")
                                env_path.write_text(
                                    "\n".join(new_lines) + "\n", encoding="utf-8"
                                )
                                log.info(f"📝 Name saved everywhere: {saved_name}")
                        except Exception as _env_err:
                            log.warning(f"Could not persist name to .env: {_env_err}")
                # ── Sync ALL personal facts to ConversationDatabase ──
                # Makes facts permanently searchable and cross-session aware.
                try:
                    if hasattr(self, "memory") and self.memory.conv_db:
                        for _fact_key in [
                            "name",
                            "college",
                            "city",
                            "age",
                            "job",
                            "birthday",
                            "hobby",
                            "profession",
                            "nickname",
                            "note",
                        ]:
                            _fact_val = self._personal_mem.get(_fact_key)
                            if _fact_val:
                                self.memory.conv_db.save_fact(
                                    "personal", _fact_key, _fact_val
                                )
                except Exception:
                    pass
                self._speak(learned)
                return ""
        except Exception as _pm_err:
            log.warning(f"PersonalMemory error: {_pm_err}")

        # ── Correction stats ──────────────────────────────────
        if any(
            p in text_lower
            for p in [
                "how many corrections",
                "what have you learned",
                "how smart are you",
                "corrections learned",
            ]
        ):
            self._speak(self.corrector.get_stats())
            return ""

        # ── WhatsApp: READ last messages from a person ────────
        # "read last messages from Sarvani"
        # "what did Sarvani say" / "last message from Banty"
        _read_msg_triggers = [
            "read last message",
            "read messages from",
            "last message from",
            "what did",
            "what's the last message",
            "show messages from",
            "read whatsapp from",
            "check messages from",
        ]
        if any(p in text_lower for p in _read_msg_triggers):
            # Extract contact name
            contact = ""
            # Pattern: "...from NAME"
            import re as _re

            m = _re.search(r"from\s+(\w+)", text_lower)
            if m:
                contact = m.group(1).strip()
            # Pattern: "what did NAME say"
            if not contact:
                m = _re.search(
                    r"(?:what did|did)\s+(\w+)\s+(?:say|send|message)", text_lower
                )
                if m:
                    contact = m.group(1).strip()
            # Pattern: "NAME's last message"
            if not contact:
                m = _re.search(r"(\w+)'s last message", text_lower)
                if m:
                    contact = m.group(1).strip()

            # Skip generic words as contact
            skip_words = {"the", "a", "any", "last", "new", "my", "read"}
            if contact in skip_words:
                contact = ""

            if contact:
                # How many messages? "last 5 messages" → 5
                count = 3
                m_count = _re.search(r"last\s+(\d+)\s+message", text_lower)
                if m_count:
                    count = min(int(m_count.group(1)), 8)

                self._speak(f"Opening chat with {contact}, one moment sir.")
                result = self.whatsapp.read_last_messages(contact, count)
                self._speak(result)
                return ""

        # ── WA: SEND from natural language BEFORE type handler ─────────
        # "write a message to Sarvani hi in WhatsApp"
        # "send hi to Sarvani on WhatsApp"
        # "WhatsApp Sarvani I am coming"
        import re as _re_wa_snd

        _wa_mentioned = "whatsapp" in text_lower or " wa " in text_lower
        _wa_snd_m = None
        if _wa_mentioned:
            # Pattern: write/send/message + "to CONTACT MESSAGE"
            _wa_snd_m = _re_wa_snd.search(
                r"(?:write|send|type|compose|say|message)\s+(?:a\s+)?(?:message\s+)?to\s+(\w+)\s+(.+)",
                text_lower.strip(),
            )
            # Also: "WhatsApp Sarvani good morning"
            if not _wa_snd_m:
                _wa_snd_m = _re_wa_snd.search(
                    r"whatsapp\s+(\w+)\s+(.+)", text_lower.strip()
                )
        if _wa_snd_m:
            _ws_contact = _wa_snd_m.group(1).strip()
            _ws_msg = _wa_snd_m.group(2).strip()
            # Strip trailing "in/on whatsapp" from message
            _ws_msg = _re_wa_snd.sub(
                r"\s*(?:in|on)\s+whatsapp\s*$", "", _ws_msg
            ).strip()
            _bad_wa = {"a", "the", "my", "this", "some", "any", "that"}
            if _ws_contact not in _bad_wa and _ws_msg:
                self._speak(f"Sending to {_ws_contact} on WhatsApp, sir.")
                result = self.whatsapp.send_message(
                    _ws_contact, _ws_msg, stop_event=self._stop_event
                )
                self._speak(result)
                return ""

        # ── TYPE command — works in ANY active window ──────────
        # "type hello" → types in WhatsApp if open, else types globally
        # GUARD: skip type handler entirely if this looks like a code-write command
        # e.g. "write a Python calculator" / "write a snake game using pygame"
        _is_code_write_cmd = bool(
            re.search(
                r"\b(?:write|create|build|make|generate|code)\b"
                r"(?:\s+(?:me|us|a|an|the))?"
                r"(?:\s+\w+)?"
                r"\s+(?:"
                r"python|javascript|java|typescript|react|html|css|sql|bash|c\+\+|"
                r"pygame|flask|django|fastapi|function|class|program|script|game|"
                r"app|application|calculator|snake|tetris|todo|api|server|tool|bot|"
                r"component|algorithm|scraper|website|webpage|code|using\s+\w+"
                r")",
                text_lower,
                re.IGNORECASE,
            )
        )
        _type_msg = "" if _is_code_write_cmd else self.whatsapp.parse_type_command(text)
        if _type_msg:
            # Check which window is currently active
            _active_win = ""
            try:
                import pygetwindow as gw

                _aw = gw.getActiveWindow()
                _active_win = (_aw.title or "").lower() if _aw else ""
            except Exception:
                pass

            _wa_active = "whatsapp" in _active_win

            # Convert "heart emoji" → ❤️ before typing
            _em_word_m = re.match(r"(.+?)\s+emoji\s*$", _type_msg, re.IGNORECASE)
            if _em_word_m:
                _em_char = self.whatsapp._word_to_emoji(_em_word_m.group(1))
                if _em_char:
                    _type_msg = _em_char
            if _wa_active:
                # Route to WhatsApp chat box
                self._speak(f"Typing in WhatsApp: {_type_msg}")
                result = self.whatsapp.type_in_active_chat(
                    _type_msg, stop_event=self._stop_event
                )
                self._speak(result)
            else:
                # Type globally into whatever window is focused
                import time

                import pyautogui
                import pyperclip

                self._speak(f"Typing: {_type_msg}")
                try:
                    pyperclip.copy(_type_msg)
                    pyautogui.hotkey("ctrl", "v")  # paste (handles Unicode)
                    time.sleep(0.2)
                    result = (
                        f"Typed '{_type_msg}' in {_active_win or 'active window'}, sir."
                    )
                except Exception as _te:
                    result = f"Could not type: {str(_te)[:60]}"
                self._speak(result)
            return ""

        # ── WhatsApp: SEND what was typed ─────────────────────
        # "send" / "enter" / "send it" / "press enter"
        _send_words = {
            "send",
            "enter",
            "send it",
            "send message",
            "press enter",
            "send now",
            "ok send",
            "go ahead send",
        }
        if text_lower.strip() in _send_words or text_lower in _send_words:
            # GUARD: only fire when WhatsApp is the active window
            _active_for_send = ""
            try:
                import pygetwindow as _gw_s

                _aw_s = _gw_s.getActiveWindow()
                _active_for_send = (_aw_s.title or "").lower() if _aw_s else ""
            except Exception:
                pass
            if "whatsapp" in _active_for_send:
                result = self.whatsapp.send_typed_message()
                self._speak(result)
                return ""

        # ── BACKSPACE — works in ANY active window ────────────
        import re as _re2

        # Normalize "back space" → "backspace", repeated presses
        _bs_text = text_lower.strip()
        _bs_text = re.sub(r"\bback\s+space\b", "backspace", _bs_text)
        _bs_text = re.sub(
            r"\b(backspace|delete)\s+(backspace|delete)\b", r"\1 2", _bs_text
        )
        _bs_match = _re2.match(
            r"^(?:backspace|delete)\s*(\d+)?(?:\s*(?:letters?|chars?|characters?))?$",
            _bs_text,
        )
        if _bs_match:
            _n = int(_bs_match.group(1)) if _bs_match.group(1) else 1
            try:
                import pygetwindow as gw

                _aw2 = gw.getActiveWindow()
                _aw2_title = (_aw2.title or "").lower() if _aw2 else ""
            except Exception:
                _aw2_title = ""
            if "whatsapp" in _aw2_title:
                result = self.whatsapp.backspace_in_chat(_n)
            else:
                import pyautogui

                for _ in range(_n):
                    pyautogui.press("backspace")
                result = f"Deleted {_n} character{'s' if _n > 1 else ''}, sir."
            self._speak(result)
            return ""

        # ── WhatsApp: DELETE LAST WORD ────────────────────────
        # "delete last word" / "remove last word" / "delete word"
        if any(
            p in text_lower
            for p in [
                "delete last word",
                "remove last word",
                "delete word",
                "remove word",
                "undo word",
                "ctrl backspace",
            ]
        ):
            result = self.whatsapp.delete_last_word()
            self._speak(result)
            return ""

        # ── CLEAR — works in ANY active window ───────────────
        if any(
            p in text_lower
            for p in [
                "clear message",
                "clear the message",
                "erase message",
                "start over",
                "clear whatsapp",
                "clear chat box",
                "erase all",
                "delete all typed",
                "clear text",
                "delete everything",
            ]
        ):
            try:
                import pygetwindow as gw

                _aw3 = gw.getActiveWindow()
                _aw3_title = (_aw3.title or "").lower() if _aw3 else ""
            except Exception:
                _aw3_title = ""
            if "whatsapp" in _aw3_title:
                result = self.whatsapp.clear_typed_message()
            else:
                import pyautogui

                pyautogui.hotkey("ctrl", "a")
                pyautogui.press("delete")
                result = "Cleared text in active window, sir."
            self._speak(result)
            return ""

        # ── WA: Notification Listener ──────────────────────────
        if any(
            p in text_lower
            for p in [
                "start whatsapp notification",
                "watch for whatsapp",
                "watch whatsapp messages",
                "listen for whatsapp",
            ]
        ):

            def _wa_notify_cb(contact, msg):
                self._speak(f"New WhatsApp from {contact}: {msg}")

            result = self.whatsapp.start_notification_listener(_wa_notify_cb)
            self._speak(result)
            return ""

        if any(
            p in text_lower
            for p in ["stop whatsapp notification", "stop watching whatsapp"]
        ):
            self._speak(self.whatsapp.stop_notification_listener())
            return ""

        # ── WA: Unread count (badge OCR) ──────────────────────
        if any(
            p in text_lower
            for p in [
                "how many unread",
                "unread count",
                "count unread",
                "check whatsapp unread",
                "how many whatsapp messages",
            ]
        ):
            self._speak("Checking unread count, sir.")
            self._speak(self.whatsapp.get_unread_count())
            return ""

        # ── WA: Open someone's chat ────────────────────────────
        # "open Sarvani chat" / "open chat with Teja" / "go to Sarvani WhatsApp"
        # "show Teja chat" / "open Sarvani's WhatsApp"
        _oc_match = None
        if any(w in text_lower for w in ["whatsapp", "chat", "message"]):
            import re as _re_oc

            _oc_match = _re_oc.search(
                r"(?:open|go to|show|switch to|take me to)\s+"
                r"(?:chat\s+with\s+|whatsapp\s+(?:chat\s+)?(?:of\s+|with\s+)?)?([a-zA-Z ]+?)"
                r"(?:'s)?\s*(?:chat|whatsapp|message|conversation)?$",
                text_lower.strip(),
            )
            # Also catch: "open Sarvani's chat" / "Sarvani chat open"
            if not _oc_match:
                _oc_match = _re_oc.search(
                    r"([a-zA-Z ]+?)'?s?\s+(?:chat|whatsapp)\s*(?:open|show|go)?",
                    text_lower.strip(),
                )
        if _oc_match:
            _oc_name = _oc_match.group(1).strip()
            # Filter out generic words that aren't contact names
            _bad_oc = {
                "the",
                "a",
                "my",
                "his",
                "her",
                "their",
                "this",
                "that",
                "open",
                "show",
                "whatsapp",
                "chat",
            }
            if _oc_name and _oc_name not in _bad_oc and len(_oc_name) > 1:
                self._speak(f"Opening {_oc_name}'s chat, sir.")
                result = self.whatsapp._open_chat(_oc_name)
                self._speak("Chat opened, sir." if result else "Failed to open chat.")
                return ""

        if any(
            p in text_lower
            for p in [
                "read all unread",
                "scan all unread",
                "what are my unread",
                "show all unread",
                "read unread whatsapp",
            ]
        ):
            self._speak("Scanning all unread WhatsApp chats, sir. Give me a moment.")
            self._speak(self.whatsapp.scan_all_unread_chats())
            return ""

        # ── WA: Mark all as read ──────────────────────────────
        if any(
            p in text_lower
            for p in [
                "mark all as read",
                "mark all whatsapp",
                "clear all unread",
                "mark read",
            ]
        ):
            self._speak(self.whatsapp.mark_all_as_read())
            return ""

        # ── WA: Voice note ────────────────────────────────────
        import re as _re3

        _vn = _re3.match(
            r"send\s+(?:(\d+)\s+second\s+)?voice\s+note\s+to\s+(.+)", text_lower.strip()
        )
        if _vn:
            _vn_dur = int(_vn.group(1)) if _vn.group(1) else 5
            _vn_who = _vn.group(2).strip()
            self._speak(f"Recording {_vn_dur} second voice note, sir. Speak now.")
            self._speak(self.whatsapp.send_voice_note(_vn_who, _vn_dur))
            return ""

        # ── Voice Change ────────────────────────────────────────
        # Detect: "change voice to Bella" / "switch to George" / "use Bella voice"
        # Strategy: must have 'voice' keyword OR explicit change verb + a known voice name
        _VOICE_NAMES = [
            "george",
            "bella",
            "adam",
            "lewis",
            "michael",
            "nicole",
            "sarah",
            "sky",
            "emma",
            "isabella",
        ]
        _VOICE_VERBS = [
            "change voice",
            "switch voice",
            "use voice",
            "set voice",
            "voice to",
            "change to",
            "switch to",
        ]

        _has_voice_name = any(v in text_lower for v in _VOICE_NAMES)
        _has_voice_verb = (
            "voice" in text_lower
            and any(
                v in text_lower
                for v in ["change", "switch", "use", "set", "make", "want"]
            )
        ) or any(v in text_lower for v in _VOICE_VERBS)

        if _has_voice_name and _has_voice_verb:
            voice_name = self.speaker.find_voice_in_text(text)
            if voice_name:
                self._speak(f"Switching to {voice_name}, one moment...")
                result = self.speaker.set_voice(voice_name)
                self._speak(result)
                return ""

        # ── Notification Watcher Controls ────────────────────────
        # "do not disturb" / "stop notifications" / "resume notifications"
        # "mute whatsapp" / "unmute whatsapp" / "notification status"
        # "what notifications did I get"
        if self.notif_watcher:
            import re as _re_dnd   # available to all sub-blocks below

            # Do Not Disturb
            if any(p in text_lower for p in [
                "do not disturb", "don't disturb",
                "stop notifications", "mute notifications",
                "silence notifications", "quiet mode",
            ]):
                # Extract duration if mentioned
                _dnd_match = _re_dnd.search(r"(\d+)\s*(?:min|minute|hour)", text_lower)
                if _dnd_match:
                    mins = int(_dnd_match.group(1))
                    if "hour" in text_lower:
                        mins *= 60
                else:
                    mins = 30
                self._speak(self.notif_watcher.set_dnd(mins))
                return ""

            # Resume notifications
            if any(p in text_lower for p in [
                "resume notifications", "start notifications",
                "unmute notifications", "turn on notifications",
                "enable notifications",
            ]):
                self._speak(self.notif_watcher.resume())
                return ""

            # Mute specific app (only if "notification" is mentioned)
            if "notification" in text_lower and any(
                p in text_lower for p in ["mute ", "silence "]
            ):
                _mute_match = _re_dnd.search(
                    r"(?:mute|silence)\s+(.+?)\s*(?:notification|$)",
                    text_lower,
                )
                if _mute_match:
                    _app = _mute_match.group(1).strip()
                    self._speak(self.notif_watcher.mute_app(_app))
                    return ""

            # Unmute specific app (only if "notification" is mentioned)
            if "notification" in text_lower and "unmute " in text_lower:
                _unmute_match = _re_dnd.search(
                    r"unmute\s+(.+?)\s*(?:notification|$)",
                    text_lower,
                )
                if _unmute_match:
                    _app = _unmute_match.group(1).strip()
                    self._speak(self.notif_watcher.unmute_app(_app))
                    return ""

            # What notifications did I get?
            if any(p in text_lower for p in [
                "what notification", "recent notification",
                "show notification", "list notification",
                "read notification", "tell me notification",
                "any notification", "my notification",
                "check notification",
            ]):
                self._speak(self.notif_watcher.get_recent())
                return ""

            # Notification watcher status
            if any(p in text_lower for p in [
                "notification status", "notification watcher status",
                "watcher status",
            ]):
                self._speak(self.notif_watcher.status())
                return ""

        # ── Unread messages / Notifications ───────────────────
        _unread_triggers = [
            "any unread",
            "unread messages",
            "check messages",
            "check my messages",
            "what did i miss",
            "any messages",
            "new messages",
            "check notifications",
            "any notifications",
            "check email",
            "any emails",
            "unread email",
            "any whatsapp",
            "whatsapp messages",
            "check whatsapp",
            "any mail",
        ]
        if any(p in text_lower for p in _unread_triggers):
            self._speak("Checking your messages, sir. One moment.")
            try:
                from skills.notifications_checker import NotificationsChecker

                checker = NotificationsChecker()
                if any(w in text_lower for w in ["email", "gmail", "mail"]):
                    result = checker.check_gmail_only()
                elif any(w in text_lower for w in ["whatsapp", "whats app"]):
                    result = checker.check_whatsapp_only()
                else:
                    result = checker.check_all()
                self._speak(result)
            except Exception as e:
                log.error(f"Notifications check error: {e}")
                self._speak("I couldn't check your messages right now, sir.")
            return ""

        # ── Language Switch ────────────────────────────────────
        # "speak in Hindi" / "switch to Telugu" / "telugu lo" / "back to English"
        _lang_switch = self.lang.detect_switch(text_lower)
        if _lang_switch:
            greeting = self.lang.switch_to(_lang_switch)
            self._speak(greeting)
            return ""

        # "what language" / "which language" / "current language"
        if any(
            t in text_lower
            for t in [
                "what language",
                "which language",
                "current language",
                "language status",
            ]
        ):
            response = self.lang.status()
            self._speak(response)
            return ""

        # "list languages" / "what languages do you know"
        if any(
            t in text_lower
            for t in [
                "list languages",
                "what languages",
                "available languages",
                "languages you know",
            ]
        ):
            response = self.lang.list_languages()
            self._speak(response)
            return ""

        # ══════════════════════════════════════════════════════
        #  NEW ADVANCED FEATURE ROUTING
        # ══════════════════════════════════════════════════════

        # ── Battery ────────────────────────────────────────────
        if any(
            t in text_lower
            for t in [
                "battery status",
                "how much battery",
                "battery level",
                "check battery",
                "battery percentage",
            ]
        ):
            self._speak(self.system.battery_status())
            return ""

        if any(
            t in text_lower
            for t in [
                "battery saver",
                "optimize battery",
                "battery optimizer",
                "save battery",
            ]
        ):
            self._speak("Activating battery saver mode, sir.")
            self._speak(self.system.battery_optimizer())
            return ""

        # ── Hardware Temps ─────────────────────────────────────
        if any(
            t in text_lower
            for t in [
                "cpu temperature",
                "gpu temperature",
                "hardware temp",
                "how hot is",
                "pc temperature",
            ]
        ):
            self._speak(self.system.hardware_temps())
            return ""

        # ── System Health ──────────────────────────────────────
        if any(
            t in text_lower
            for t in [
                "system health",
                "how is my system",
                "pc health",
                "computer health",
            ]
        ):
            self._speak(self.system.system_health())
            return ""

        # ── WiFi ───────────────────────────────────────────────
        if any(
            t in text_lower
            for t in [
                "wifi password",
                "wi-fi password",
                "what is my wifi password",
                "show wifi password",
            ]
        ):
            import re as _re_wifi

            _wifi_m = _re_wifi.search(
                r"(?:wifi|wi-fi)\s+password\s+(?:for\s+)?(.+)", text_lower
            )
            profile = _wifi_m.group(1).strip() if _wifi_m else None
            self._speak(self.system.wifi_password(profile))
            return ""

        if any(
            t in text_lower
            for t in ["list wifi", "saved wifi", "wifi networks", "show wifi networks"]
        ):
            self._speak(self.system.list_wifi_networks())
            return ""

        # ── Startup Apps ───────────────────────────────────────
        if any(
            t in text_lower
            for t in [
                "startup apps",
                "startup programs",
                "what starts on boot",
                "boot apps",
                "autostart programs",
            ]
        ):
            self._speak(self.system.list_startup_apps())
            return ""

        # ── Network Info ───────────────────────────────────────
        if any(
            t in text_lower
            for t in [
                "network info",
                "network status",
                "my ip address",
                "internet info",
                "ip address",
            ]
        ):
            self._speak(self.system.network_info())
            return ""

        # ── App Modes (Work/Study/Movie) ───────────────────────
        _mode_triggers = [
            "work mode",
            "study mode",
            "movie mode",
            "gaming mode",
            "meeting mode",
        ]
        if any(t in text_lower for t in _mode_triggers):
            for mode in _mode_triggers:
                if mode in text_lower:
                    self._speak(f"Activating {mode.title()}, sir.")
                    self._speak(self.app_ctrl.activate_mode(mode))
                    return ""

        # ── App Usage ──────────────────────────────────────────
        if any(
            t in text_lower
            for t in [
                "app usage",
                "app stats",
                "app tracker",
                "what apps have i opened",
                "apps i used",
            ]
        ):
            self._speak(self.app_ctrl.get_usage_report())
            return ""

        # ── File: Fuzzy Search ─────────────────────────────────
        if any(
            t in text_lower
            for t in [
                "find file",
                "search file",
                "look for file",
                "fuzzy search",
                "find my",
            ]
        ):
            import re as _re_ff

            _ff_m = _re_ff.search(
                r"(?:find|search|look for)\s+(?:file\s+)?(?:my\s+)?(.+)", text_lower
            )
            if _ff_m:
                _fname = _ff_m.group(1).strip()
                self._speak(f"Searching for '{_fname}', sir.")
                self._speak(self.files.fuzzy_search(_fname))
                return ""

        # ── File: Recent Files ─────────────────────────────────
        if any(
            t in text_lower
            for t in [
                "recent files",
                "last opened files",
                "recently opened",
                "files i opened",
            ]
        ):
            self._speak(self.files.recent_files())
            return ""

        # ── File: Zip / Unzip ──────────────────────────────────
        import re as _re_zip

        _zip_m = _re_zip.search(r"(?:zip|compress|archive)\s+(.+)", text_lower)
        if _zip_m:
            _zip_target = _zip_m.group(1).strip()
            self._speak(f"Zipping {_zip_target}, sir.")
            self._speak(self.files.zip_file(_zip_target))
            return ""

        _unzip_m = _re_zip.search(r"(?:unzip|extract|decompress)\s+(.+)", text_lower)
        if _unzip_m:
            _unzip_target = _unzip_m.group(1).strip()
            self._speak(f"Extracting {_unzip_target}, sir.")
            self._speak(self.files.unzip_file(_unzip_target))
            return ""

        # ── File: Organize Downloads ───────────────────────────
        if any(
            t in text_lower
            for t in [
                "organize downloads",
                "sort downloads",
                "clean downloads",
                "organize my downloads",
            ]
        ):
            self._speak("Organizing your downloads folder, sir. One moment.")
            self._speak(self.files.organize_downloads())
            return ""

        # ── File: Duplicate Finder ─────────────────────────────
        if any(
            t in text_lower
            for t in [
                "find duplicates",
                "duplicate files",
                "find duplicate",
                "remove duplicates",
            ]
        ):
            self._speak("Scanning for duplicate files, sir.")
            self._speak(self.files.find_duplicates())
            return ""

        # ── Media: Sleep Timer ─────────────────────────────────
        import re as _re_st

        _st_m = _re_st.search(
            r"(?:sleep timer|stop music in|music off in)\s*(\d+)\s*min", text_lower
        )
        if _st_m:
            _mins = int(_st_m.group(1))
            self._speak(self.media.set_sleep_timer(_mins))
            return ""

        if any(
            t in text_lower
            for t in ["cancel sleep timer", "cancel timer", "stop sleep timer"]
        ):
            self._speak(self.media.cancel_sleep_timer())
            return ""

        # ── Media: Fade ────────────────────────────────────────
        if "fade out" in text_lower:
            self._speak(self.media.fade_out())
            return ""
        if "fade in" in text_lower:
            self._speak(self.media.fade_in())
            return ""

        # ══════════════════════════════════════════════════════
        # "speak faster" / "speak slower"
        # ══════════════════════════════════════════════════════

        # ── Voice speed ────────────────────────────────────────
        if any(
            t in text_lower
            for t in [
                "speak faster",
                "speed up",
                "talk faster",
                "faster voice",
                "increase speed",
            ]
        ):
            current_speed = self.speaker._kokoro_speed
            new_speed = min(2.0, current_speed + 0.2)
            self.speaker._kokoro_speed = new_speed
            self.speaker._wav_cache.clear()
            self.speaker._save_config()
            self._speak(f"Speed increased to {new_speed:.1f}x. How's this?")
            return ""

        if any(
            t in text_lower
            for t in [
                "speak slower",
                "slow down",
                "talk slower",
                "slower voice",
                "decrease speed",
            ]
        ):
            current_speed = self.speaker._kokoro_speed
            new_speed = max(0.5, current_speed - 0.2)
            self.speaker._kokoro_speed = new_speed
            self.speaker._wav_cache.clear()
            self.speaker._save_config()
            self._speak(f"Speed decreased to {new_speed:.1f}x. How's this?")
            return ""

        # "what voice are you using" / "current voice" / "which voice"
        if any(
            t in text_lower
            for t in [
                "what voice",
                "which voice",
                "current voice",
                "voice status",
                "your voice",
            ]
        ):
            name = self.speaker.current_voice_name()
            self._speak(f"I'm using {name}, sir.")
            return ""

        # "list voices" / "available voices" / "what voices do you have"
        if any(
            t in text_lower
            for t in ["list voices", "available voices", "what voices", "show voices"]
        ):
            voices = self.speaker.list_voices()
            voice_list = ", ".join(voices[:10])
            self._speak(f"Available voices: {voice_list}")
            return ""

        # ── Clipboard History ─────────────────────────────────
        if any(
            t in text_lower
            for t in [
                "clipboard history",
                "show clipboard history",
                "what did i copy",
                "last copied",
                "my clipboard",
            ]
        ):
            self._speak(self.clipboard.get_history())
            return ""
        if any(
            t in text_lower
            for t in ["clear clipboard history", "delete clipboard history"]
        ):
            self._speak(self.clipboard.clear_history())
            return ""
        if "restore clipboard" in text_lower:
            import re as _re_cb

            _cb_n = _re_cb.search(r"restore clipboard\s*(\d+)", text_lower)
            n = int(_cb_n.group(1)) if _cb_n else 1
            self._speak(self.clipboard.restore_from_history(n))
            return ""
        # ── Clipboard Format Conversion ──────────────────────
        if any(
            t in text_lower
            for t in [
                "convert json to yaml",
                "json to yaml",
                "convert yaml to json",
                "yaml to json",
                "convert csv to markdown",
                "csv to table",
                "convert to uppercase",
                "make uppercase",
                "convert to lowercase",
                "make lowercase",
            ]
        ):
            from_fmt = (
                "json"
                if "json" in text_lower
                and "yaml" in text_lower
                and text_lower.index("json") < text_lower.index("yaml")
                else "yaml"
                if "yaml" in text_lower and "json" in text_lower
                else "csv"
                if "csv" in text_lower
                else "text"
            )
            to_fmt = (
                "yaml"
                if "yaml" in text_lower and from_fmt == "json"
                else "json"
                if "json" in text_lower and from_fmt == "yaml"
                else "markdown"
                if "markdown" in text_lower or "table" in text_lower
                else "uppercase"
                if "uppercase" in text_lower
                else "lowercase"
                if "lowercase" in text_lower
                else "json"
            )
            self._speak(f"Converting {from_fmt} to {to_fmt}...")
            self._speak(self.clipboard.convert_format(from_fmt, to_fmt))
            return ""
        # ── QR Code ───────────────────────────────────────────
        if any(
            t in text_lower for t in ["generate qr", "create qr", "make qr", "qr code"]
        ):
            self._speak("Generating QR code from clipboard...")
            self._speak(self.clipboard.generate_qr())
            return ""
        # ── Text Diff ─────────────────────────────────────────
        if any(
            t in text_lower
            for t in [
                "text diff",
                "compare clipboard",
                "diff clipboard",
                "compare the two",
                "clipboard diff",
            ]
        ):
            self._speak(self.clipboard.text_diff())
            return ""
        # ── Extract from Clipboard ────────────────────────────
        if any(
            t in text_lower
            for t in ["extract urls", "extract links", "get urls from clipboard"]
        ):
            self._speak(self.clipboard.extract_urls())
            return ""
        if any(
            t in text_lower
            for t in [
                "extract emails from clipboard",
                "emails in clipboard",
                "get emails from clipboard",
            ]
        ):
            self._speak(self.clipboard.extract_emails())
            return ""
        if any(
            t in text_lower
            for t in ["extract phones", "phone numbers in clipboard", "get phones"]
        ):
            self._speak(self.clipboard.extract_phones())
            return ""
        if any(
            t in text_lower
            for t in [
                "extract all",
                "extract everything",
                "extract contact",
                "get contacts from clipboard",
            ]
        ):
            self._speak(self.clipboard.extract_all())
            return ""
        # ── Translate Clipboard ───────────────────────────────
        if any(
            t in text_lower
            for t in [
                "translate clipboard",
                "translate what i copied",
                "translate clipboard to",
            ]
        ):
            import re as _re_trcb

            _lang_m = _re_trcb.search(r"translate.*?to\s+(\w+)", text_lower)
            lang = _lang_m.group(1) if _lang_m else "english"
            self._speak(f"Translating clipboard to {lang}...")
            self._speak(self.clipboard.translate_clipboard(lang))
            return ""
        # ── Count Words ───────────────────────────────────────
        if any(
            t in text_lower
            for t in [
                "count words",
                "word count",
                "count characters",
                "how many words",
                "clipboard count",
            ]
        ):
            self._speak(self.clipboard.count_clipboard())
            return ""

        # ── Browser Extra Features ────────────────────────────
        if any(
            t in text_lower
            for t in [
                "bookmark this",
                "bookmark page",
                "save bookmark",
                "add bookmark",
                "bookmark this page",
            ]
        ):
            self._speak(self.browser.bookmark_current_page())
            return ""
        if any(
            t in text_lower
            for t in [
                "clear browsing data",
                "clear browser history",
                "delete browsing data",
                "clear cookies",
            ]
        ):
            self._speak("Clearing browsing data, sir.")
            self._speak(self.browser.clear_browsing_data())
            return ""
        if any(
            t in text_lower
            for t in [
                "extract emails from page",
                "emails on this page",
                "get emails from website",
            ]
        ):
            self._speak("Extracting emails from current page...")
            self._speak(self.browser.extract_emails_from_page())
            return ""
        if any(
            t in text_lower
            for t in [
                "extract phones from page",
                "phone numbers on page",
                "get phone numbers",
            ]
        ):
            self._speak("Extracting phone numbers from page...")
            self._speak(self.browser.extract_phones_from_page())
            return ""
        if any(
            t in text_lower
            for t in [
                "toggle dark mode",
                "dark mode on",
                "dark mode page",
                "invert page colors",
            ]
        ):
            self._speak(self.browser.toggle_dark_mode())
            return ""
        if "find in page" in text_lower or "search on page" in text_lower:
            import re as _re_fp

            _fp_m = _re_fp.search(r"(?:find in page|search on page)\s+(.+)", text_lower)
            query = _fp_m.group(1).strip() if _fp_m else ""
            if query:
                self._speak(self.browser.find_in_page(query))
                return ""
        if any(t in text_lower for t in ["zoom in", "increase zoom"]):
            self._speak(self.browser.zoom_in())
            return ""
        if any(t in text_lower for t in ["zoom out", "decrease zoom"]):
            self._speak(self.browser.zoom_out())
            return ""
        if any(
            t in text_lower
            for t in ["zoom reset", "reset zoom", "normal zoom", "zoom 100"]
        ):
            self._speak(self.browser.zoom_reset())
            return ""
        if any(
            t in text_lower for t in ["reload page", "refresh page", "reload browser"]
        ):
            self._speak(self.browser.reload_page())
            return ""
        if any(
            t in text_lower
            for t in ["hard reload", "force reload", "clear cache reload"]
        ):
            self._speak(self.browser.hard_reload())
            return ""
        if any(t in text_lower for t in ["go back", "browser back", "previous page"]):
            self._speak(self.browser.go_back())
            return ""
        if any(t in text_lower for t in ["go forward", "browser forward", "next page"]):
            self._speak(self.browser.go_forward())
            return ""
        if any(t in text_lower for t in ["print page", "print this page"]):
            self._speak(self.browser.print_page())
            return ""
        if any(
            t in text_lower for t in ["view source", "page source", "show source code"]
        ):
            self._speak(self.browser.view_source())
            return ""

        # ── Weather New Features ──────────────────────────────
        if any(
            t in text_lower
            for t in [
                "air quality",
                "aqi",
                "pollution level",
                "air pollution",
                "pm2.5",
                "air index",
            ]
        ):
            import re as _re_aq

            _city_m = _re_aq.search(
                r"(?:in|for|at)\s+([a-zA-Z ]+?)(?:\s*$|\s*\?)", text_lower
            )
            city = _city_m.group(1).strip() if _city_m else None
            self._speak("Checking air quality...")
            self._speak(self.weather.get_aqi(city))
            return ""
        if any(
            t in text_lower
            for t in [
                "sunrise",
                "sunset",
                "what time is sunrise",
                "when does the sun rise",
                "when does it get dark",
                "daylight hours",
            ]
        ):
            import re as _re_ss

            _city_m = _re_ss.search(
                r"(?:in|for|at)\s+([a-zA-Z ]+?)(?:\s*$|\s*\?)", text_lower
            )
            city = _city_m.group(1).strip() if _city_m else None
            self._speak(self.weather.get_sunrise_sunset(city))
            return ""
        if any(
            t in text_lower
            for t in [
                "weather suggestion",
                "should i carry umbrella",
                "carry an umbrella",
                "carry umbrella",
                "bring umbrella",
                "need an umbrella",
                "need umbrella",
                "what to wear",
                "what should i wear",
                "weather advice",
                "should i go out",
                "is it safe to go out",
            ]
        ):
            self._speak("Checking weather for suggestions...")
            self._speak(self.weather.get_weather_suggestion())
            return ""
        if any(
            t in text_lower
            for t in [
                "weather alert",
                "severe weather",
                "weather warning",
                "any weather warning",
            ]
        ):
            self._speak(self.weather.get_weather_alert())
            return ""
        if any(
            t in text_lower
            for t in [
                "compare weather",
                "weather in multiple cities",
                "weather comparison",
            ]
        ):
            import re as _re_cw

            cities_raw = _re_cw.sub(
                r"compare weather|weather comparison|in|and|between", "", text_lower
            ).strip()
            cities = [
                c.strip()
                for c in cities_raw.replace(",", " ").split()
                if len(c.strip()) > 2
            ][:4]
            if not cities:
                cities = ["Chennai", "Mumbai", "Delhi"]
            self._speak("Comparing weather across cities...")
            self._speak(self.weather.compare_cities(cities))
            return ""

        # ── News New Features ─────────────────────────────────
        if any(
            t in text_lower
            for t in [
                "trending topics",
                "trending now",
                "what's trending",
                "google trends",
                "trending searches",
            ]
        ):
            self._speak("Fetching trending topics...")
            self._speak(self.news.get_trending_topics())
            return ""
        if any(
            t in text_lower for t in ["rss news", "fetch rss", "rss feed", "read rss"]
        ):
            import re as _re_rss

            _src_m = _re_rss.search(r"(?:from|of)\s+(\w+)", text_lower)
            topic = _src_m.group(1) if _src_m else None
            self._speak("Fetching RSS news...")
            self._speak(self.news.get_rss_news(topic=topic))
            return ""
        if any(
            t in text_lower
            for t in [
                "positive news",
                "good news",
                "happy news",
                "uplifting news",
                "nice news",
            ]
        ):
            self._speak("Finding positive news...")
            self._speak(self.news.get_news_by_mood("positive"))
            return ""
        if any(t in text_lower for t in ["tech news", "technology news"]):
            self._speak(self.news.get_news_by_mood("tech"))
            return ""
        if any(t in text_lower for t in ["science news", "research news"]):
            self._speak(self.news.get_news_by_mood("science"))
            return ""

        # ── System New Features ───────────────────────────────
        if any(
            t in text_lower
            for t in [
                "disk cleanup",
                "clean disk",
                "clear temp",
                "free disk space",
                "clean storage",
            ]
        ):
            self._speak("Running disk cleanup, sir. One moment...")
            self._speak(self.system.disk_cleanup())
            return ""
        if any(
            t in text_lower
            for t in [
                "network speed",
                "internet speed",
                "speed test",
                "check speed",
                "test internet",
                "how fast is my internet",
            ]
        ):
            self._speak("Running speed test, sir. This takes about 10 seconds...")
            self._speak(self.system.network_speed_test())
            return ""
        if any(
            t in text_lower
            for t in [
                "create restore point",
                "restore point",
                "system restore",
                "make restore point",
            ]
        ):
            self._speak("Creating system restore point, sir.")
            import re as _re_rp

            _desc_m = _re_rp.search(
                r"(?:named|called|label|description)\s+(.+)", text_lower
            )
            desc = _desc_m.group(1).strip() if _desc_m else "JARVIS Restore Point"
            self._speak(self.system.create_restore_point(desc))
            return ""
        if any(
            t in text_lower
            for t in [
                "free ram",
                "clear memory",
                "clean ram",
                "free up memory",
                "ram cleanup",
            ]
        ):
            self._speak("Freeing up RAM, sir.")
            self._speak(self.system.free_ram())
            return ""
        if any(
            t in text_lower
            for t in [
                "top processes",
                "what's using cpu",
                "cpu hogs",
                "most cpu",
                "heavy processes",
            ]
        ):
            self._speak(self.system.get_top_processes())
            return ""

        # ── File New Features ─────────────────────────────────
        if any(t in text_lower for t in ["encrypt file", "lock file", "secure file"]):
            import re as _re_ef

            _fn_m = _re_ef.search(
                r"(?:encrypt|lock|secure)\s+(?:file\s+)?(.+)", text_lower
            )
            filename = _fn_m.group(1).strip() if _fn_m else ""
            if filename:
                self._speak(f"Encrypting {filename}, sir.")
                self._speak(self.files.encrypt_file(filename))
                return ""
        if any(t in text_lower for t in ["decrypt file", "unlock file", "unencrypt"]):
            import re as _re_df

            _fn_m = _re_df.search(
                r"(?:decrypt|unlock|unencrypt)\s+(?:file\s+)?(.+)", text_lower
            )
            filename = _fn_m.group(1).strip() if _fn_m else ""
            if filename:
                self._speak(f"Decrypting {filename}, sir.")
                self._speak(self.files.decrypt_file(filename))
                return ""
        if any(
            t in text_lower
            for t in [
                "batch rename",
                "rename all files",
                "bulk rename",
                "rename multiple",
            ]
        ):
            import re as _re_br

            _prefix_m = _re_br.search(r"(?:prefix|add)\s+(\S+)", text_lower)
            _suffix_m = _re_br.search(r"suffix\s+(\S+)", text_lower)
            _find_m = _re_br.search(r"replace\s+(\S+)\s+with\s+(\S+)", text_lower)
            prefix = _prefix_m.group(1) if _prefix_m else ""
            suffix = _suffix_m.group(1) if _suffix_m else ""
            find = _find_m.group(1) if _find_m else ""
            replace_val = _find_m.group(2) if _find_m else ""
            self._speak("Batch renaming files, sir.")
            self._speak(
                self.files.batch_rename(
                    prefix=prefix, suffix=suffix, find=find, replace=replace_val
                )
            )
            return ""
        if any(
            t in text_lower
            for t in [
                "cloud sync",
                "sync status",
                "onedrive status",
                "dropbox status",
                "cloud status",
            ]
        ):
            self._speak(self.files.cloud_sync_status())
            return ""
        if any(
            t in text_lower for t in ["file info", "file details", "file properties"]
        ):
            import re as _re_fi

            _fn_m = _re_fi.search(
                r"(?:info|details|properties)\s+(?:of\s+|for\s+)?(.+)", text_lower
            )
            filename = _fn_m.group(1).strip() if _fn_m else ""
            if filename:
                self._speak(self.files.get_file_info(filename))
                return ""

        # ── Reminder New Features ─────────────────────────────
        if any(
            t in text_lower
            for t in [
                "remind me every day",
                "daily reminder",
                "recurring reminder",
                "remind me every",
                "set daily reminder",
                "remind me every morning",
                "remind me every evening",
            ]
        ):
            import re as _re_recur

            _msg_m = _re_recur.search(
                r"(?:remind me every (?:day|morning|evening|week|hour) (?:to|about|at \S+ to|at \S+ about)?\s*)(.+)",
                text_lower,
            )
            freq = (
                "morning"
                if "morning" in text_lower
                else "evening"
                if "evening" in text_lower
                else "hourly"
                if "hour" in text_lower
                else "weekly"
                if "week" in text_lower
                else "daily"
            )
            msg = _msg_m.group(1).strip() if _msg_m else text.strip()
            import re as _re_at

            _at_m = _re_at.search(r"at (\d{1,2}(?::\d{2})?\s*(?:am|pm)?)", text_lower)
            at_time = "09:00"
            if _at_m:
                t_str = _at_m.group(1).strip().lower()
                if "pm" in t_str:
                    h = int(t_str.replace("pm", "").replace(":", "").strip().split()[0])
                    at_time = f"{h + 12 if h < 12 else h:02d}:00"
                elif "am" in t_str:
                    h = int(t_str.replace("am", "").strip().split()[0])
                    at_time = f"{h:02d}:00"
            self._speak(f"Setting {freq} reminder, sir.")
            self._speak(self.reminder.set_recurring_reminder(msg, freq, at_time))
            return ""
        # ── Reminder: List upcoming reminders ─────────────────────
        if any(
            t in text_lower
            for t in [
                "upcoming reminders",
                "list reminders",
                "show reminders",
                "what are my reminders",
                "show my reminders",
                "my reminders",
                "pending reminders",
                "all reminders",
                "check reminders",
            ]
        ):
            self._speak(self.reminder.list_reminders())
            return ""

        if any(
            t in text_lower for t in ["snooze reminder", "snooze", "remind me later"]
        ):
            import re as _re_snooze

            _min_m = _re_snooze.search(r"(\d+)\s*min", text_lower)
            mins = int(_min_m.group(1)) if _min_m else 10
            self._speak(self.reminder.snooze_reminder(mins))
            return ""
        if any(
            t in text_lower
            for t in ["delete reminder", "cancel reminder", "remove reminder"]
        ):
            import re as _re_dr

            _kw_m = _re_dr.search(
                r"(?:delete|cancel|remove)\s+reminder\s+(?:for\s+|about\s+)?(.+)",
                text_lower,
            )
            keyword = _kw_m.group(1).strip() if _kw_m else ""
            if keyword:
                self._speak(self.reminder.delete_reminder(keyword))
                return ""
        if any(
            t in text_lower
            for t in ["timer status", "is timer running", "active timer"]
        ):
            self._speak(self.reminder.get_timer_status())
            return ""

        # ── Shopping New Features ─────────────────────────────
        if any(
            t in text_lower
            for t in [
                "add to wishlist",
                "add to my wishlist",
                "save to wishlist",
                "wishlist add",
                "to my wishlist",
                "to wishlist",
            ]
        ):
            import re as _re_wl

            # "add iPhone 16 to my wishlist" — item is between add/save and "to wishlist"
            _item_m = _re_wl.search(
                r"(?:add|save)\s+(.+?)\s+to\s+(?:my\s+)?wishlist",
                text_lower,
            )
            if not _item_m:
                _item_m = _re_wl.search(
                    r"(?:add|save)\s+(?:to\s+(?:my\s+)?wishlist\s+)?(.+?)(?:\s+to\s+(?:my\s+)?wishlist)?$",
                    text_lower,
                )
            item = _item_m.group(1).strip() if _item_m else ""
            if item:
                self._speak(self.shopping.add_to_wishlist(item))
                return ""
        if any(
            t in text_lower
            for t in [
                "view wishlist",
                "my wishlist",
                "show wishlist",
                "wishlist items",
                "what's on my wishlist",
            ]
        ):
            self._speak(self.shopping.view_wishlist())
            return ""
        if any(
            t in text_lower
            for t in ["remove from wishlist", "delete from wishlist", "wishlist remove"]
        ):
            import re as _re_rwl

            _item_m = _re_rwl.search(
                r"(?:remove|delete)\s+(?:from\s+(?:my\s+)?wishlist\s+)?(.+?)(?:\s+from\s+(?:my\s+)?wishlist)?$",
                text_lower,
            )
            item = _item_m.group(1).strip() if _item_m else ""
            if item:
                self._speak(self.shopping.remove_from_wishlist(item))
                return ""
        if any(
            t in text_lower
            for t in ["shop wishlist", "buy from wishlist", "search wishlist"]
        ):
            import re as _re_shwl

            _n_m = _re_shwl.search(
                r"(?:shop|buy)\s+(?:wishlist\s+)?(?:item\s+)?(\d+)", text_lower
            )
            n = int(_n_m.group(1)) if _n_m else 1
            self._speak(self.shopping.shop_wishlist_item(n))
            return ""

        # ── Media New Features ────────────────────────────────
        if any(
            t in text_lower
            for t in [
                "show lyrics",
                "get lyrics",
                "lyrics of",
                "lyrics for",
                "what are the lyrics",
                "display lyrics",
            ]
        ):
            import re as _re_lyr

            _song_m = _re_lyr.search(
                r"(?:lyrics\s+(?:of|for)|show lyrics|get lyrics)\s+(.+?)(?:\s+by\s+(.+))?$",
                text_lower,
            )
            song = _song_m.group(1).strip() if _song_m else ""
            artist = _song_m.group(2).strip() if _song_m and _song_m.group(2) else None
            if song:
                self._speak(f"Getting lyrics for {song}...")
                self._speak(self.media.get_lyrics(song, artist))
                return ""
            else:
                # Try to get currently playing song
                self._speak("Getting lyrics for current song...")
                self._speak(self.media.get_lyrics())
                return ""
        if any(
            t in text_lower
            for t in ["play radio", "open radio", "radio station", "listen to radio"]
        ):
            import re as _re_radio

            _station_m = _re_radio.search(
                r"(?:play|open|listen to)\s+(?:radio\s+)?(.+?)(?:\s+radio)?$",
                text_lower,
            )
            station = _station_m.group(1).strip() if _station_m else "fm"
            self._speak(f"Opening {station} radio, sir.")
            self._speak(self.media.play_radio(station))
            return ""
        if any(
            t in text_lower
            for t in [
                "what's playing",
                "current song",
                "what song is this",
                "what song is playing",
                "now playing",
            ]
        ):
            self._speak(self.media.get_current_song())
            return ""
        if any(
            t in text_lower
            for t in ["create playlist", "make playlist", "playlist from list"]
        ):
            import re as _re_pl

            _songs_m = _re_pl.search(
                r"(?:create|make)\s+playlist\s+(?:with|from)?\s*(.+)", text_lower
            )
            if _songs_m:
                songs_str = _songs_m.group(1).strip()
                songs = [
                    s.strip()
                    for s in songs_str.replace(" and ", ",").split(",")
                    if s.strip()
                ]
                self._speak(f"Creating playlist with {len(songs)} songs, sir.")
                self._speak(self.media.create_playlist(songs))
                return ""

        mem = (
            self.gemini._local_llm.memory
            if hasattr(self.gemini, "_local_llm")
            else None
        )

        # ── Memory commands ───────────────────────────────────
        if mem:
            if any(
                p in text_lower
                for p in [
                    "what do you remember",
                    "what do you know about me",
                    "what have you remembered",
                    "recall",
                ]
            ):
                facts = mem.get_facts_prompt()
                if facts:
                    response = facts.replace(
                        "Things I know about the user:\n- ", ""
                    ).replace("\n- ", ", ")
                    self._speak(f"I remember: {response}")
                else:
                    self._speak("I don't know much about you yet. Tell me something!")
                return ""

            if any(
                p in text_lower
                for p in [
                    "forget everything",
                    "clear memory",
                    "forget all",
                    "reset memory",
                ]
            ):
                mem.forget()
                mem.clear_session()
                self._speak("Done. I've forgotten everything.")
                return ""

            if text_lower.startswith("remember that ") or text_lower.startswith(
                "remember "
            ):
                mem.add_user_message(text)
                self._speak("Got it, I'll remember that.")
                return ""

        # ── AI Conversation Stats ─────────────────────────────
        if any(
            p in text_lower
            for p in [
                "ai stats",
                "conversation stats",
                "how much have we talked",
                "how many conversations",
                "training stats",
            ]
        ):
            self._speak(self.gemini.get_conversation_stats())
            return ""

        # ── Export Training Data ──────────────────────────────
        if any(
            p in text_lower
            for p in [
                "export training",
                "save training data",
                "export conversations",
                "save for training",
            ]
        ):
            self._speak("Exporting conversations for AI training, sir.")
            self._speak(self.gemini.export_conversations_for_training())
            return ""

        # ── Personality Switch ────────────────────────────────
        if any(
            p in text_lower
            for p in [
                "switch to formal mode",
                "be more formal",
                "formal mode",
                "switch personality",
            ]
        ):
            self._speak(self.gemini.set_personality("formal"))
            return ""
        if any(
            p in text_lower
            for p in ["be casual", "casual mode", "relax a bit", "chill mode"]
        ):
            self._speak(self.gemini.set_personality("casual"))
            return ""
        if any(
            p in text_lower
            for p in ["be funny", "funny mode", "joke mode", "make me laugh more"]
        ):
            self._speak(self.gemini.set_personality("funny"))
            return ""
        if any(
            p in text_lower
            for p in [
                "default personality",
                "normal mode",
                "back to normal",
                "reset personality",
            ]
        ):
            self._speak(self.gemini.set_personality("default"))
            return ""

        # ── Conditional commands ("if X then Y") ──────────────────
        import re as _re_cond

        _cond_m = _re_cond.search(
            r"if\s+(?:my\s+)?(?:battery|charge)\s+(?:is\s+)?(?:below|less than|under)\s+(\d+)%?",
            text_lower,
        )
        if _cond_m:
            _threshold = int(_cond_m.group(1))
            import psutil as _psu

            _bat = _psu.sensors_battery()
            _bat_pct = int(_bat.percent) if _bat else 100
            if _bat_pct < _threshold:
                self._speak(
                    f"Battery is at {_bat_pct}%. Below {_threshold}%, sir. Activating battery saver."
                )
                self._speak(self.system.battery_optimizer())
            else:
                self._speak(
                    f"Battery is at {_bat_pct}%, which is above {_threshold}%. No need to activate battery saver, sir."
                )
            return ""

        # Screenshot + send to WhatsApp compound command
        _ss_wa_m = _re_cond.search(
            r"(?:take|capture)\s+(?:a\s+)?screenshot\s+and\s+(?:send|share)\s+(?:it\s+)?(?:to|with)\s+(\w+)",
            text_lower,
        )
        if _ss_wa_m:
            _sc_contact = _ss_wa_m.group(1).strip()
            self._speak(
                f"Taking screenshot and sending to {_sc_contact} on WhatsApp, sir."
            )
            import os
            import tempfile

            import pyautogui as _pag

            _sc_path = os.path.join(tempfile.gettempdir(), "jarvis_sc_wa.png")

            _pag.screenshot().save(_sc_path)
            import time as _time

            _time.sleep(0.5)
            response = self.whatsapp.send_screenshot(_sc_contact)
            self._speak(response)
            return ""

        # ── Task chain detection ──────────────────────────────
        if self.chain.is_chain(text):
            self._speak("On it.")
            return self.chain.execute_chain(text)

        # ── Name: get / set ───────────────────────────────────
        # "What's my name" / "What is my name" / "Do you know my name"
        _name_ask = [
            "what's my name",
            "what is my name",
            "do you know my name",
            "who am i",
            "what do you call me",
            "what's your user's name",
        ]
        if any(t in text_lower for t in _name_ask):
            name = config.USER_NAME or "Boss"
            self._speak(f"Your name is {name}, sir.")
            return ""

        # "My name is Srinivas" / "Call me Srini" / "Remember my name is X"
        _name_set_patterns = [
            "my name is ",
            "call me ",
            "remember my name is ",
            "remember that my name is ",
            "i am ",
            "my name's ",
        ]
        for pat in _name_set_patterns:
            if text_lower.startswith(pat):
                new_name = (
                    text[len(pat) :].strip().rstrip(".,!").split()[0].capitalize()
                )
                if new_name and len(new_name) > 1:
                    # Update config at runtime
                    config.USER_NAME = new_name
                    # Persist to .env file
                    try:
                        from pathlib import Path as _Path

                        env_path = _Path(__file__).parent / ".env"
                        if env_path.exists():
                            lines = env_path.read_text(encoding="utf-8").splitlines()
                            found = False
                            new_lines = []
                            for line in lines:
                                if line.startswith("USER_NAME="):
                                    new_lines.append(f"USER_NAME={new_name}")
                                    found = True
                                else:
                                    new_lines.append(line)
                            if not found:
                                new_lines.append(f"USER_NAME={new_name}")
                            env_path.write_text(
                                "\n".join(new_lines) + "\n", encoding="utf-8"
                            )
                    except Exception as _e:
                        log.warning(f"Could not persist name: {_e}")
                    self._speak(f"Got it! I'll call you {new_name} from now on, sir.")
                    return ""
                break

        # ── Camera Vision — Gemini AI (no disk writes, no local model) ──────
        # ALL camera commands now use vision_handler + Gemini Vision API

        # What am I holding / what's in my hand / identify this
        _cam_identify = [
            "what is in my hand",
            "what's in my hand",
            "whats in my hand",
            "what am i holding",
            "what do i have",
            "what is this",
            "what's this",
            "whats this",
            "what is that",
            "what's that",
            "whats that",
            "identify this",
            "identify this object",
            "tell me what this is",
            "what object is this",
            "scan this",
            "look at this",
            "can you identify",
            "recognize this",
            "analyze this",
            "what am i showing",
            "what do i hold",
            "see this",
            "check this out",
            "what do you think this is",
        ]
        if any(t in text_lower for t in _cam_identify):
            if "screen" in text_lower or "monitor" in text_lower:
                self._speak("Looking at your screen...")
                response = self.vision.what_is_on_screen()
            else:
                self._speak("Looking through the camera...")
                response = self.vision.identify_objects()
            self._speak(response)
            return ""

        # Look at camera / describe scene / what do you see
        _cam_look = [
            "look at the camera",
            "look through the camera",
            "what can you see",
            "what's in front",
            "what is in front",
            "describe the room",
            "describe the scene",
            "look around",
            "what am i holding",
            "what do you see",
            "use your camera",
            "open your camera",
            "whats in front",
            "whats in my hand",
        ]
        if any(t in text_lower for t in _cam_look):
            self._speak("Looking...")
            response = self.vision.look_at_camera()
            self._speak(response)
            return ""

        # Who am I / can you see me
        _cam_person = [
            "who am i",
            "can you see me",
            "do you see me",
            "describe me",
            "what do i look like",
            "can you see my face",
        ]
        if any(t in text_lower for t in _cam_person):
            self._speak("Looking at you...")
            response = self.vision.identify_person()
            self._speak(response)
            return ""

        # Read text from camera (book, paper, board, sign)
        _cam_read = [
            "read this",
            "read that",
            "what does this say",
            "what does that say",
            "read the text",
            "what is written",
            "what does it say",
            "read this for me",
            "scan the text",
            "read the label",
            "what's written",
            "tell me what it says",
            "read this book",
            "read this sign",
            "read this page",
            "read the board",
            "read the whiteboard",
        ]
        if any(t in text_lower for t in _cam_read):
            self._speak("Reading...")
            response = self.vision.read_text_from_camera()
            self._speak(response)
            return ""

        # ── Direct Math Handler ──────────────────────
        # Catches: "2+2", "16 X 16", "16 into 16", "what is 5 times 3"
        # FIX: strip prefixes and "equals to"; add 'into', 'x', 'X' as multiply
        import re as _re_math

        _math_text = text_lower.strip()
        for _pfx in [
            "jarvis ",
            "what is ",
            "what's ",
            "calculate ",
            "solve ",
            "compute ",
            "tell me ",
        ]:
            if _math_text.startswith(_pfx):
                _math_text = _math_text[len(_pfx) :].strip()
        # FIX: strip trailing noise like "equals to", "equal", "="
        _math_text = _re_math.sub(
            r"\s*(equals to|equals|equal|=)\s*$", "", _math_text
        ).strip()
        _math_text = (
            _math_text.replace("plus", "+")
            .replace("minus", "-")
            .replace("times", "*")
            .replace("multiplied by", "*")
            .replace("divided by", "/")
            .replace("over", "/")
            .replace(" into ", "*")  # FIX: "16 into 16" = 16*16 in Indian math
        )
        # FIX: replace standalone X/x as multiply (e.g. "16 X 16", "16 x 16")
        _math_text = _re_math.sub(r"(?<=\d)\s+[xX]\s+(?=\d)", "*", _math_text)
        _math_m = _re_math.search(
            r"^(-?\d+(?:\.\d+)?)\s*([+\-*/])\s*(-?\d+(?:\.\d+)?)$", _math_text.strip()
        )
        if _math_m:
            try:
                _ma = float(_math_m.group(1))
                _mop = _math_m.group(2)
                _mb = float(_math_m.group(3))
                _mres = {
                    "+": _ma + _mb,
                    "-": _ma - _mb,
                    "*": _ma * _mb,
                    "/": (_ma / _mb if _mb != 0 else None),
                }[_mop]
                if _mres is None:
                    _math_reply = "Can't divide by zero, sir!"
                elif _mres == int(_mres):
                    _math_reply = f"That's {int(_mres)}, sir."
                else:
                    _math_reply = f"That's {_mres:.4f}, sir."
                self._speak(_math_reply)
                return ""  # FIX: return '' so the calling loop doesn't speak again
            except Exception:
                pass

        # ── Screen control (click, scroll, type, snap) ────────
        screen_words = [
            "click",
            "scroll",
            "type ",
            "press ",
            "select all",
            "copy this",
            "copy that",
            "paste",
            "undo",
            "redo",
            "save this",
            "save it",
            "snap left",
            "snap right",
            "move left",
            "move right",
            "minimize",
            "minimise",
            "maximize",
            "maximise",
            "switch window",
            "alt tab",
            "task view",
            "full screen",
            "show all windows",
            "next window",
        ]
        if any(w in text_lower for w in screen_words):
            result = self.screen.execute(text)
            if result:
                self._speak(result)
                return ""  # Already spoken

        # ── Clipboard ─────────────────────────────────────────────────
        if (
            "read clipboard" in text_lower
            or "what's in clipboard" in text_lower
            or "what did i copy" in text_lower
        ):
            response = self.clipboard.read_clipboard()
            self._speak(response)
            return ""

        if (
            "summarize clipboard" in text_lower
            or "summarize what i copied" in text_lower
        ):
            response = self.clipboard.summarize_clipboard(self.gemini)
            self._speak(response)
            return ""

        # ── Calendar ───────────────────────────────────────────────
        add_event_triggers = [
            "add event",
            "add a ",
            "schedule a",
            "schedule an",
            "create event",
            "put a ",
            "book a",
            "set up a",
            "remind me to",
            "add to calendar",
        ]
        if any(t in text_lower for t in add_event_triggers):
            response = self.calendar.add_event(text)
            self._speak(response)
            return ""

        if any(
            t in text_lower
            for t in [
                "what's my schedule",
                "my schedule",
                "what do i have",
                "what's happening",
            ]
        ):
            if "tomorrow" in text_lower:
                self._speak(self.calendar.get_tomorrow())
            elif "week" in text_lower:
                self._speak(self.calendar.get_this_week())
            elif any(
                d in text_lower
                for d in [
                    "monday",
                    "tuesday",
                    "wednesday",
                    "thursday",
                    "friday",
                    "saturday",
                    "sunday",
                ]
            ):
                self._speak(self.calendar.get_schedule_for_day(text))
            else:
                self._speak(self.calendar.get_today())
            return ""

        if any(
            t in text_lower
            for t in [
                "today's schedule",
                "schedule for today",
                "what's today",
                "do i have anything today",
            ]
        ):
            self._speak(self.calendar.get_today())
            return ""

        if any(
            t in text_lower
            for t in [
                "tomorrow's schedule",
                "schedule for tomorrow",
                "do i have anything tomorrow",
            ]
        ):
            self._speak(self.calendar.get_tomorrow())
            return ""

        if "next event" in text_lower or "upcoming event" in text_lower:
            self._speak(self.calendar.get_next_event())
            return ""

        if any(
            t in text_lower
            for t in [
                "show all events",
                "list events",
                "all my events",
                "show calendar",
            ]
        ):
            self._speak(self.calendar.list_all_events())
            return ""

        if any(
            t in text_lower
            for t in ["cancel event", "delete event", "remove event", "cancel my"]
        ):
            response = self.calendar.cancel_event(text)
            self._speak(response)
            return ""

        # ── Direct Math Handler ──────────────────────────────
        # Handle BEFORE factual triggers so "what is 2+2" never hits Wikipedia
        # Catches: "2+2", "what is 2+2", "2 + 2 =", "5 times 3"
        import re as _re_math

        _math_text = text_lower.strip()
        # Strip common prefixes like "what is", "calculate", "jarvis"
        for _pfx in [
            "jarvis ",
            "what is ",
            "what's ",
            "calculate ",
            "solve ",
            "compute ",
        ]:
            if _math_text.startswith(_pfx):
                _math_text = _math_text[len(_pfx) :].strip()
        _math_text = (
            _math_text.rstrip("=? ")
            .replace("plus", "+")
            .replace("minus", "-")
            .replace("times", "*")
            .replace("multiplied by", "*")
            .replace("divided by", "/")
            .replace("over", "/")
        )
        _math_m = _re_math.search(
            r"^(-?\d+(?:\.\d+)?)\s*([+\-*/])\s*(-?\d+(?:\.\d+)?)$", _math_text.strip()
        )
        if _math_m:
            try:
                _ma = float(_math_m.group(1))
                _mop = _math_m.group(2)
                _mb = float(_math_m.group(3))
                _mres = {
                    "+": _ma + _mb,
                    "-": _ma - _mb,
                    "*": _ma * _mb,
                    "/": (_ma / _mb if _mb != 0 else None),
                }[_mop]
                if _mres is None:
                    _math_reply = "Can't divide by zero, sir!"
                elif _mres == int(_mres):
                    _math_reply = f"That's {int(_mres)}, sir."
                else:
                    _math_reply = f"That's {_mres:.4f}, sir."
                self._speak(_math_reply)
                return ""
            except Exception:
                pass

        # ── Crypto Price (CoinGecko — free, no API key) ────────────────────
        _crypto_map = {
            "bitcoin": "bitcoin",
            "btc": "bitcoin",
            "ethereum": "ethereum",
            "eth": "ethereum",
            "dogecoin": "dogecoin",
            "doge": "dogecoin",
            "solana": "solana",
            "sol": "solana",
            "ripple": "ripple",
            "xrp": "ripple",
            "litecoin": "litecoin",
            "ltc": "litecoin",
            "cardano": "cardano",
            "ada": "cardano",
            "bnb": "binancecoin",
            "binance": "binancecoin",
        }
        _crypto_id = None
        for _kw, _cid in _crypto_map.items():
            if _kw in text_lower:
                _crypto_id = _cid
                break
        _wants_price = any(
            w in text_lower
            for w in ["price", "worth", "cost", "value", "rate", "how much"]
        )
        if _crypto_id and (_wants_price or "crypto" in text_lower):
            try:
                import requests as _req

                _inr = (
                    "inr" in text_lower
                    or "rupee" in text_lower
                    or "rupees" in text_lower
                )
                _currency = "inr" if _inr else "usd"
                _symbol = _currency.upper()
                _r = _req.get(
                    f"https://api.coingecko.com/api/v3/simple/price"
                    f"?ids={_crypto_id}&vs_currencies={_currency}",
                    timeout=6,
                )
                if _r.status_code == 200:
                    _price = _r.json().get(_crypto_id, {}).get(_currency, 0)
                    _name = _crypto_id.title()
                    if _inr:
                        _price_fmt = f"₹{_price:,.2f}"
                    else:
                        _price_fmt = f"${_price:,.2f}"
                    response = f"{_name} is currently at {_price_fmt} {_symbol}, sir."
                    self._speak(response)
                    return ""
                else:
                    response = f"Couldn't fetch {_crypto_id} price right now, sir. CoinGecko returned {_r.status_code}."
                    self._speak(response)
                    return ""
            except Exception as _ce:
                response = f"Crypto price check failed: {str(_ce)[:60]}"
                self._speak(response)
                return ""

        # ── Real-time Web Search + Factual Questions ────────────────────────
        live_search_triggers = [
            "latest news",
            "current news",
            "news about",
            "news on",
            "price of",
            "current price",
            "bitcoin",
            "btc",
            "ethereum",
            "crypto price",
            "stock price",
            "time in ",
            "what time is it in",
            "live score",
            "current score",
            "today's",
            "right now",
            "currently",
        ]
        factual_triggers_startswith = [
            "who is ",
            "who was ",
            "who are ",
            "who were ",
            "what is ",
            "what are ",
            "what was ",
            "what were ",
            "how does ",
            "how did ",
            "how do ",
            "why is ",
            "why was ",
            "why are ",
            "why did ",
            "when did ",
            "when was ",
            "when is ",
            "where is ",
            "where was ",
            "where are ",
            "tell me about ",
            "tell about ",
            "explain ",
            "define ",
            "describe ",
            "how to ",
            "how do i ",
            "what causes ",
            "do you know about ",
            "what do you know about ",
            "can you tell me about ",
            "can you explain ",
            "give me information about ",
            "give me info about ",
            "what happened to ",
            "what happened with ",
            "who invented ",
            "who created ",
            "who founded ",
            "what is the history of ",
        ]
        factual_triggers_contains = [
            "elon musk",
            "bill gates",
            "steve jobs",
            "mark zuckerberg",
            "narendra modi",
            "donald trump",
            "joe biden",
            "who is he",
            "who is she",
            "who are they",
            "what does he do",
            "what does she do",
        ]
        is_live = any(t in text_lower for t in live_search_triggers)
        is_factual = any(
            text_lower.startswith(t) for t in factual_triggers_startswith
        ) or any(t in text_lower for t in factual_triggers_contains)
        # FIX: Don't route math questions to Wikipedia
        # Catches: "what is 16 X 16", "what is 16 into 16", "16+2", etc.
        _looks_math = bool(
            _re_math.search(
                r"\d.*[+\-*/xX]|[+\-*/].*\d|\d+\s+into\s+\d|\d+\s+[xX]\s+\d", text_lower
            )
        )
        if _looks_math:
            is_factual = False

        # FIX: Conversational/opinion/casual markers → always Gemini, never Wikipedia
        # "explain X like I'm 15", "using an analogy", "in simple terms",
        # "what do you think", "your opinion", "roast me", etc.
        _conversational_markers = [
            "like i'm ",
            "like i am ",
            "like a 5",
            "like a 10",
            "like a 15",
            "like i was ",
            "as if i",
            "for dummies",
            "in simple terms",
            "simply explain",
            "easy explanation",
            "in layman",
            "using an analogy",
            "give me an analogy",
            "real world analogy",
            "what do you think",
            "your opinion",
            "your take",
            "do you think",
            "should i ",
            "would you ",
            "what would you",
            "i feel like",
            "i feel ",
            "i'm feeling",
            "i am feeling",
            "i'm stressed",
            "i'm bored",
            "i'm confused",
            "i'm stuck",
            "help me understand",
            "can you help me",
            "roast me",
            "tell me a joke",
            "make me laugh",
            "what's your favorite",
            "do you have a favorite",
            "are you conscious",
            "do you have feelings",
            "are you alive",
            "are you smarter",
            "better than chatgpt",
            "better than siri",
            "meaning of life",
            "meaning of",
            "purpose of life",
            "what would happen if",
            "what if ",
            "hypothetically",
            "genuinely surprising",
            "tell me something surprising",
            "fun fact",
            "did you know",
            "interesting fact",
        ]
        _is_conversational = any(m in text_lower for m in _conversational_markers)
        if _is_conversational:
            is_factual = False
            is_live = False

        if is_live or is_factual:
            self._speak("Let me look that up...")
            response = self.web_search.search(text)
            self._speak(response)
            return ""

        # "search news about cricket" / "latest news"
        if "search news" in text_lower or "latest news" in text_lower:
            topic = (
                text_lower.replace("search news", "")
                .replace("latest news", "")
                .replace("about", "")
                .strip()
            )
            self._speak("Fetching news...")
            response = self.web_search.search_news(topic)
            self._speak(response)
            return ""

        # ── System info ───────────────────────────────────────
        if any(
            w in text_lower
            for w in [
                "cpu usage",
                "ram usage",
                "how much ram",
                "how much storage",
                "disk space",
                "system info",
                "system status",
                "what's eating",
                "what is using",
            ]
        ):
            import psutil

            cpu = psutil.cpu_percent(interval=0.5)
            ram = psutil.virtual_memory()
            disk = psutil.disk_usage("C:\\")
            response = (
                f"CPU at {cpu:.0f} percent, "
                f"RAM {ram.percent:.0f} percent used, "
                f"{ram.available / (1024**3):.1f} gigs free, "
                f"disk {100 - disk.percent:.0f} percent free."
            )
            self._speak(response)
            return ""  # Already spoken

        # ── Problem Solver (LeetCode / DSA / Debug) ────────────
        if self.problem_solver:
            # "solve this" / "solve this problem" / "solve leetcode"
            _solve_screen_triggers = [
                "solve this",
                "solve the problem",
                "solve this problem",
                "solve leetcode",
                "solve this question",
                "solve the question",
                "solve this code",
            ]
            if any(t in text_lower for t in _solve_screen_triggers):
                self._speak("Reading the problem from your screen...")
                response = self.problem_solver.solve_from_screen()
                self._speak(response)
                return ""

            # "solve two sum" / "solve reverse linked list" / "solve [problem name]"
            _solve_name_match = re.match(
                r"(?:solve|solve the|solve a)\s+(.+?)(?:\s+problem|\s+question)?$",
                text_lower,
            )
            if _solve_name_match:
                problem_name = _solve_name_match.group(1).strip()
                # Skip if it matched a screen trigger
                if problem_name not in ["this", "the problem", "leetcode", "the question", "this code"]:
                    self._speak(f"Solving {problem_name}...")
                    response = self.problem_solver.solve_by_name(problem_name)
                    self._speak(response)
                    return ""

            # "debug this" / "fix this code" / "why is this failing"
            _debug_triggers = [
                "debug this",
                "fix this code",
                "fix this",
                "why is this failing",
                "why is it failing",
                "what's wrong with this code",
                "what is wrong with this code",
                "find the bug",
            ]
            if any(t in text_lower for t in _debug_triggers):
                self._speak("Analyzing your code for bugs...")
                response = self.problem_solver.debug_from_screen()
                self._speak(response)
                return ""

            # "optimize this" / "optimize this code" / "make this faster"
            _optimize_triggers = [
                "optimize this",
                "optimize this code",
                "make this faster",
                "improve this code",
                "better solution",
            ]
            if any(t in text_lower for t in _optimize_triggers):
                self._speak("Looking for optimizations...")
                response = self.problem_solver.optimize_from_screen()
                self._speak(response)
                return ""

            # "explain the approach" / "explain the solution"
            _explain_triggers = [
                "explain the approach",
                "explain the solution",
                "explain this solution",
                "how does this work",
                "walk me through",
            ]
            if any(t in text_lower for t in _explain_triggers):
                response = self.problem_solver.explain_last()
                self._speak(response)
                return ""

            # "paste it" / "paste the solution" / "paste solution"
            _paste_triggers = [
                "paste it",
                "paste the solution",
                "paste solution",
                "paste the code",
                "put it in",
            ]
            if any(t in text_lower for t in _paste_triggers):
                response = self.problem_solver.paste_solution()
                self._speak(response)
                return ""

            # "what's the complexity" / "time complexity"
            if "complexity" in text_lower and any(
                w in text_lower for w in ["time", "space", "what"]
            ):
                response = self.problem_solver.get_complexity()
                self._speak(response)
                return ""

            # "how many problems solved" / "coding stats" / "solve stats"
            _stats_triggers = [
                "how many problems",
                "coding stats",
                "solve stats",
                "problems solved",
                "learning stats",
                "what have you learned",
            ]
            if any(t in text_lower for t in _stats_triggers):
                if self.problem_solver.memory:
                    response = self.problem_solver.memory.get_stats()
                else:
                    response = "Code memory isn't available right now."
                self._speak(response)
                return ""

            # "export training data"
            if "export" in text_lower and ("training" in text_lower or "data" in text_lower):
                if self.problem_solver.memory:
                    response = self.problem_solver.memory.export_training_data()
                else:
                    response = "Code memory isn't available."
                self._speak(response)
                return ""

        # ── Screen Vision ─────────────────────────────────────
        vision_triggers = [
            "what's on my screen",
            "what is on my screen",
            "what's on screen",
            "look at my screen",
            "what do you see",
            "describe my screen",
            "what am i looking at",
            "what's open",
            "what app is this",
        ]
        if any(t in text_lower for t in vision_triggers):
            self._speak("Looking...")
            response = self.vision.what_is_on_screen()
            self._speak(response)
            return ""

        if "read" in text_lower and "screen" in text_lower:
            self._speak("Reading your screen...")
            response = self.vision.read_text_from_screen()
            self._speak(response)
            return ""

        if "summarize" in text_lower and "screen" in text_lower:
            self._speak("One sec...")
            response = self.vision.summarize_screen()
            self._speak(response)
            return ""

        if (
            "find" in text_lower or "is there" in text_lower
        ) and "screen" in text_lower:
            # "find the settings button on screen" / "is there a login button on screen"
            query = (
                text_lower.replace("find", "")
                .replace("on screen", "")
                .replace("on my screen", "")
                .strip()
            )
            self._speak("Checking...")
            response = self.vision.find_on_screen(query)
            self._speak(response)
            return ""

        if any(
            t in text_lower
            for t in [
                "any error",
                "error on screen",
                "what's the error",
                "what error",
                "check error",
            ]
        ):
            self._speak("Checking for errors...")
            response = self.vision.check_error_on_screen()
            self._speak(response)
            return ""

        # ── Camera Vision (webcam — NO screenshots, all in RAM) ──────
        camera_triggers = [
            "what is in my hand",
            "what's in my hand",
            "whats in my hand",
            "what am i holding",
            "what do i have",
            "look at this",
            "look at what i have",
            "can you see what",
            "can you identify",
            "tell me what this is",
            "what object",
            "identify this object",
            "scan this object",
            "use camera",
            "take a look at this",
            "check the camera",
            "what am i showing",
            "what do i hold",
            "see this",
        ]
        if any(t in text_lower for t in camera_triggers):
            self._speak("Let me take a look...")
            response = self.vision.what_am_i_holding()
            self._speak(response)
            return ""

        # "What is this" / "identify this" / "what do you see" via camera
        if any(
            t in text_lower
            for t in [
                "what is this",
                "what's this",
                "whats this",
                "identify this",
                "recognize this",
                "what do you see",
                "scan this",
                "analyze this",
            ]
        ):
            # Check if asking about screen or camera
            if "screen" in text_lower or "monitor" in text_lower:
                self._speak("Looking at your screen...")
                response = self.vision.what_is_on_screen()
            else:
                self._speak("Looking through the camera...")
                response = self.vision.identify_objects()
            self._speak(response)
            return ""

        # "Look at the camera" / "describe what you see" via camera
        if any(
            t in text_lower
            for t in [
                "look at the camera",
                "look through the camera",
                "what can you see",
                "describe the room",
                "describe the scene",
                "what's in front",
                "what is in front",
                "look around",
            ]
        ):
            self._speak("Looking...")
            response = self.vision.look_at_camera()
            self._speak(response)
            return ""

        # "Who am I" / "can you see me" via camera
        if any(
            t in text_lower
            for t in [
                "who am i",
                "can you see me",
                "do you see me",
                "describe me",
                "what do i look like",
                "can you see my face",
            ]
        ):
            self._speak("Looking at you...")
            response = self.vision.identify_person()
            self._speak(response)
            return ""

        # "Read what's in front of me" / "read the board" via camera
        if "read" in text_lower and any(
            t in text_lower
            for t in ["camera", "in front", "board", "paper", "book", "whiteboard"]
        ):
            self._speak("Reading...")
            response = self.vision.read_text_from_camera()
            self._speak(response)
            return ""

        # "This is a [name]" — teach JARVIS a new object
        teach_name = None
        for prefix in [
            "this is a ",
            "this is an ",
            "this is ",
            "it's a ",
            "it is a ",
            "its a ",
            "remember this as ",
            "call this ",
        ]:
            if text_lower.startswith(prefix):
                teach_name = text[len(prefix) :].strip().rstrip(".")
                break

        if (
            teach_name
            and self.obj_recog
            and (self.obj_recog.has_pending_learn or self.obj_recog._last_capture)
        ):
            result = self.obj_recog.teach(teach_name)
            self._speak(result)
            return ""

        # "What objects do you know?"
        if any(
            t in text_lower
            for t in [
                "what objects do you know",
                "what have you learned",
                "objects you know",
                "show learned objects",
                "what can you identify",
            ]
        ):
            if self.obj_recog:
                self._speak(self.obj_recog.status())
            return ""

        # ══════════════════════════════════════════════════════
        #  VS CODE WRITER — Voice → Gemini → VS Code Animation
        # ══════════════════════════════════════════════════════

        # ── Triggers that clearly mean "write code in VS Code" ─
        _vscode_write_triggers = [
            # Language-specific
            "write a python",
            "write python",
            "write a javascript",
            "write javascript",
            "write a java",
            "write a typescript",
            "write a bash",
            "write a c++",
            "write c++",
            "write a react",
            "write a html",
            "write html",
            "write a css",
            "write css",
            "write a sql",
            "write sql",
            # Code constructs
            "write a function",
            "write a class",
            "write a program",
            "write a script",
            "write a component",
            "write an algorithm",
            "write a algorithm",
            "write a code",
            "write code",
            "write code for",
            "code a function",
            "code a class",
            # Create / build / make / generate
            "create a function",
            "create a class",
            "create a python",
            "create a javascript",
            "create a react",
            "create a script",
            "create a program",
            "build a function",
            "build a class",
            "build a python",
            "build a script",
            "make a function",
            "make a class",
            "make a python",
            "make a script",
            "generate a function",
            "generate code",
            "generate a script",
            # VS Code explicit
            "open vscode and write",
            "open vs code and write",
            "write in vscode",
            "write in vs code",
            "code in vscode",
            "write me a",
            "write me an",
            "write me the",
            "build me a",
            "build me an",
            "make me a",
            "make me an",
            "create me a",
            "create me an",
            # Library/framework keywords — catches "using pygame", "with pygame" etc.
            "using pygame",
            "with pygame",
            "pygame game",
            "pygame project",
            "using tkinter",
            "with tkinter",
            "using flask",
            "with flask",
            "using django",
            "with django",
            "using fastapi",
            "with fastapi",
            "using numpy",
            "with numpy",
            "using pandas",
            "with pandas",
            "using opencv",
            "with opencv",
            "using tensorflow",
            "with tensorflow",
            "using pytorch",
            "with pytorch",
            "using requests",
            "with requests",
            # Application types — "write a snake game", "build a todo app"
            "write a game",
            "build a game",
            "make a game",
            "create a game",
            "write a snake",
            "write a tetris",
            "write a chess",
            "write a tic tac toe",
            "write a todo",
            "write a calculator",
            "write a timer",
            "write a clock",
            "write a chat",
            "write a bot",
            "write a scraper",
            "write a crawler",
            "write a server",
            "write a client",
            "write a api",
            "write an api",
            "write a cli",
            "write a tool",
            "write a utility",
            "build a todo",
            "build a calculator",
            "build a snake",
            "build a chat",
            "build a bot",
            "build a scraper",
            "build a server",
            "build a client",
            "build a app",
            "build an app",
            "build a tool",
            "make a todo",
            "make a calculator",
            "make a snake",
            "make a game",
            "make a chat",
            "make a bot",
            "make a app",
            "make an app",
            "create a todo",
            "create a calculator",
            "create a snake",
            "create a chat",
            "create a bot",
            "create a app",
            "create an app",
            "create a game",
            "create a tool",
        ]

        # ── Regex-based smart detection (catches everything else) ──────────────
        # Matches: "write/build/make/create/code a/an/the [ANYTHING] [game/app/tool/…]"
        # Also:    "write/build [ANYTHING] using/with/in [language/library]"
        _CODE_NOUN_PATTERN = re.compile(
            r"\b(?:write|build|make|create|code|generate|develop|implement)\b"
            r"(?:\s+(?:me|us|a|an|the))?"
            r"\s+\w+"
            r"\s+(?:game|app|application|tool|utility|bot|script|program|system"
            r"|api|server|client|dashboard|website|webpage|simulation"
            r"|visualizer|visualisation|visualization|tracker|manager|calculator"
            r"|timer|clock|alarm|reminder|quiz|test|checker|converter|player"
            r"|recorder|downloader|scraper|crawler|parser|generator|editor)\b",
            re.IGNORECASE,
        )
        _USING_LANG_PATTERN = re.compile(
            r"\b(?:write|build|make|create|code|generate|develop|implement)\b"
            r".{2,60}"
            r"\b(?:using|with|in)\s+"
            r"(?:python|javascript|java|c\+\+|typescript|react|html|css|sql|bash"
            r"|pygame|tkinter|flask|django|fastapi|express|nodejs|vue|angular"
            r"|numpy|pandas|opencv|tensorflow|pytorch|keras|sklearn|matplotlib"
            r"|requests|beautifulsoup|selenium|scrapy|kivy|wxpython|pyqt)\b",
            re.IGNORECASE,
        )

        _is_vscode_write = (
            any(t in text_lower for t in _vscode_write_triggers)
            or bool(_CODE_NOUN_PATTERN.search(text_lower))
            or bool(_USING_LANG_PATTERN.search(text_lower))
        )

        # ── Named file creation ("create main.py with ...") ────
        _named_file_triggers = [
            "create ",
            "make a file",
            "make file",
            "write a file",
            "new file",
            "generate a file",
        ]
        _has_filename = bool(
            stdlib_re.search(
                r"\b[\w\-]+\.(py|js|ts|html|css|cpp|c|java|json|yaml|sql|sh|txt|md|jsx|vue|rs|go|rb|php|kt|swift)\b",
                text_lower,
            )
        )

        _is_named_file = _has_filename and any(
            t in text_lower for t in _named_file_triggers
        )

        if _is_vscode_write or _is_named_file:
            # ── Use VSCodeWriter if available ─────────────────
            if self.code_writer:
                # Parse the command to extract task, language, suggested filename
                parsed = self.code_writer.parse_write_command(text)
                task = parsed["task"]
                language = parsed["language"]
                suggested_filename = parsed["filename"]

                # If user already specified a filename in the command, use it
                _fname_match = stdlib_re.search(
                    r"\b([\w\-]+\.(py|js|ts|html|css|cpp|c|java|json|yaml|sql|sh|txt|md|jsx|vue|rs|go|rb|php|kt|swift))\b",
                    text_lower,
                )
                if _fname_match:
                    # User said a specific filename → use it directly, skip asking
                    final_filename = _fname_match.group(1)
                    self._speak(
                        f"Got it, sir. Writing {language} code and opening VS Code now."
                    )
                else:
                    # Ask user for filename
                    self._speak(
                        f"I'll write that in {language}. "
                        f"Shall I call it {suggested_filename}? "
                        f"Or say a different name."
                    )
                    _fname_response = self._get_input()

                    if _fname_response:
                        _fname_response_lower = _fname_response.lower().strip()
                        # User confirmed the suggestion
                        if any(
                            w in _fname_response_lower
                            for w in [
                                "yes",
                                "sure",
                                "okay",
                                "ok",
                                "that's fine",
                                "that's good",
                                "sounds good",
                                "go ahead",
                                "perfect",
                                "good",
                                "fine",
                                "yep",
                                "yeah",
                            ]
                        ):
                            final_filename = suggested_filename
                        else:
                            # User said a custom name — extract it
                            _custom_match = stdlib_re.search(
                                r"\b([\w\-]+\.(py|js|ts|html|css|cpp|c|java|json|yaml|sql|sh|txt|md|jsx|vue|rs|go|rb|php|kt|swift))\b",
                                _fname_response_lower,
                            )
                            if _custom_match:
                                # Exact filename with extension
                                final_filename = _custom_match.group(1)
                            else:
                                # Plain name without extension — add one
                                raw_name = re.sub(
                                    r"[^\w\-]", "_", _fname_response_lower.strip()
                                )
                                ext = self.code_writer._ext_from_language(language)
                                final_filename = f"{raw_name}{ext}"
                    else:
                        # No input — use suggested
                        final_filename = suggested_filename

                # ── Ask for save folder ────────────────────────
                from pathlib import Path as _Path
                _default_dir = _Path.home() / "Desktop" / "JARVIS_Code"
                _save_dir = _default_dir

                self._speak(
                    f"I'll save it in Desktop JARVIS Code folder. "
                    f"Say okay, or tell me a different folder like Desktop, Documents, Downloads, or a folder name."
                )
                _folder_response = self._get_input()

                if _folder_response:
                    _folder_lower = _folder_response.lower().strip()

                    # User confirmed default
                    if any(w in _folder_lower for w in [
                        "yes", "sure", "okay", "ok", "that's fine", "that's good",
                        "sounds good", "go ahead", "perfect", "good", "fine",
                        "yep", "yeah", "default", "jarvis code",
                    ]):
                        _save_dir = _default_dir

                    # Common folder shortcuts
                    elif "desktop" in _folder_lower and "jarvis" not in _folder_lower:
                        _save_dir = _Path.home() / "Desktop"
                    elif "document" in _folder_lower:
                        _save_dir = _Path.home() / "Documents"
                    elif "download" in _folder_lower:
                        _save_dir = _Path.home() / "Downloads"
                    elif "project" in _folder_lower:
                        _projects = _Path.home() / "Desktop" / "PROJECTS"
                        if _projects.exists():
                            _save_dir = _projects
                        else:
                            _save_dir = _Path.home() / "Projects"
                    else:
                        # Try to use the response as a folder name
                        _custom_folder = _folder_lower.strip().replace(" ", "_")
                        # Remove filler words
                        for _filler in ["save in ", "save to ", "put it in ", "in ", "folder ", "the "]:
                            _custom_folder = _custom_folder.replace(_filler.replace(" ", "_"), "")
                        _custom_folder = _custom_folder.strip("_").strip()

                        if _custom_folder:
                            # Check if it's an absolute path
                            _custom_path = _Path(_custom_folder)
                            if _custom_path.is_absolute() and _custom_path.exists():
                                _save_dir = _custom_path
                            else:
                                # Create as subfolder on Desktop
                                _save_dir = _Path.home() / "Desktop" / _custom_folder

                _save_dir.mkdir(parents=True, exist_ok=True)
                self._speak(f"Saving to {_save_dir.name}. Generating {language} code now, sir. One moment.")

                # ── Generate, open VS Code, type code ─────────
                try:
                    result = self.code_writer.write_to_vscode(
                        task=task,
                        filename=final_filename,
                        language=language,
                        save_dir=_save_dir,
                        speak_fn=None,  # We speak ourselves
                    )
                    self._speak(result)
                except Exception as _cw_write_err:
                    log.error(f"Code writing failed: {_cw_write_err}")
                    self._speak(
                        f"Code writing hit an error, sir: {str(_cw_write_err)[:100]}. "
                        f"The file may still be saved in {_save_dir.name}."
                    )
                return ""

            else:
                # ── Fallback: CodeRunner (no VS Code) ─────────
                if _is_named_file:
                    llm = (
                        self.gemini._local_llm
                        if hasattr(self.gemini, "_local_llm")
                        else None
                    )
                    if llm and llm.is_available:
                        self._speak("Creating the file...")
                        response = self.code_runner.create_file(text, llm)
                    else:
                        response = self.gemini.ask(
                            f"Write complete {text} code, return ONLY the code:"
                        )
                    self._speak(response)
                    return ""
                else:
                    self._speak("Writing the code...")
                    task = text
                    for t in _vscode_write_triggers:
                        if t in text_lower:
                            idx = text_lower.find(t) + len(t)
                            task = (
                                text[idx:].strip().lstrip("to ").lstrip("that ").strip()
                                or text
                            )
                            break
                    response = self.gemini.ask(
                        f"Write a complete, well-commented code for: {task}. Return ONLY the code."
                    )
                    self._speak(response)
                    return ""

        # ── Run the last written code ─────────────────────────
        if any(
            t in text_lower
            for t in [
                "run it",
                "yes run",
                "execute it",
                "run the code",
                "go ahead and run",
                "yes do it",
                "run that",
                "execute that",
                "run the file",
            ]
        ):
            # Try VSCodeWriter first (runs in VS Code terminal for visual feedback)
            if self.code_writer and self.code_writer.get_last_filepath():
                self._speak("Running the code in VS Code, sir.")
                ran = self.code_writer.run_in_vscode_terminal()
                if ran:
                    return ""
                # Fallback to subprocess run
                result = self.code_writer.run_last_file()
                self._speak(result)
                return ""
            # Fallback to old CodeRunner
            self._speak("Running...")
            response = self.code_runner.confirm_and_run()
            self._speak(response)
            return ""

        # ── Show the last written code ────────────────────────
        if any(
            t in text_lower
            for t in [
                "show me the code",
                "show the code",
                "what code did you write",
                "what did you write",
                "open the file",
                "open last file",
                "open that file in vscode",
            ]
        ):
            if self.code_writer and self.code_writer.get_last_filepath():
                result = self.code_writer.open_last_in_vscode()
                self._speak(result)
                return ""
            response = self.code_runner.show_last_code()
            self._speak(response)
            return ""

        # ── Explain the last written code ─────────────────────
        if any(
            t in text_lower
            for t in [
                "explain the code",
                "explain that code",
                "what does the code do",
                "describe the code",
            ]
        ):
            if self.code_writer and self.code_writer.get_last_filepath():
                self._speak("Let me read the code and explain it, sir.")
                result = self.code_writer.explain_last_code()
                self._speak(result)
                return ""

        # ── Cancel / don't run ────────────────────────────────
        if any(t in text_lower for t in ["don't run", "cancel code", "cancel that"]):
            if self.code_writer:
                self.code_writer.clear_pending_run()
            if self.code_runner._pending_confirmation:
                self.code_runner.cancel()
            self._speak("Cancelled, sir.")
            return ""

        # ── Run again ─────────────────────────────────────────
        if any(t in text_lower for t in ["run last code", "run again", "run it again"]):
            if self.code_writer and self.code_writer.get_last_filepath():
                self._speak("Running again, sir.")
                ran = self.code_writer.run_in_vscode_terminal()
                if not ran:
                    result = self.code_writer.run_last_file()
                    self._speak(result)
                return ""
            self._speak("Running again...")
            response = self.code_runner.run_last_code()
            self._speak(response)
            return ""

        # ── Code history ──────────────────────────────────────
        if any(
            t in text_lower
            for t in ["code history", "what code have you run", "last code run"]
        ):
            self._speak(self.code_runner.get_history())
            return ""

        # ══════════════════════════════════════════════════════
        #  APP CONTROL — Window, Browser, Smart Modes
        # ══════════════════════════════════════════════════════
        import re as _re_ac

        # ── Window: minimize ─────────────────────────────────
        _min_m = _re_ac.search(r"minimiz[e|s]?\s+(.+)", text_lower)
        if _min_m and "minimize" in text_lower:
            app = _min_m.group(1).strip()
            self._speak(f"Minimizing {app}.")
            self._speak(self.app_ctrl.minimize_app(app))
            return ""

        # ── Window: maximize ─────────────────────────────────
        _max_m = _re_ac.search(r"maximiz[e|s]?\s+(.+)", text_lower)
        if _max_m and "maximize" in text_lower:
            app = _max_m.group(1).strip()
            self._speak(self.app_ctrl.maximize_app(app))
            return ""

        # ── Window: fullscreen ────────────────────────────────
        if "fullscreen" in text_lower or "full screen" in text_lower:
            _app_m = _re_ac.search(r"(?:fullscreen|full screen)\s+(.+)", text_lower)
            app = _app_m.group(1).strip() if _app_m else "current"
            self._speak(self.app_ctrl.fullscreen_app(app))
            return ""

        # ── Window: switch to ─────────────────────────────────
        _sw_m = _re_ac.search(
            r"(?:switch to|go to|open|bring up)\s+(\w[\w\s]+)", text_lower
        )
        if _sw_m and any(p in text_lower for p in ["switch to", "go to"]):
            app = _sw_m.group(1).strip()
            result = self.app_ctrl.switch_to_app(app)
            self._speak(result)
            return ""

        # ── Window: snap ─────────────────────────────────────
        # "snap Chrome to the left" / "move Spotify to right"
        _snap_m = _re_ac.search(
            r"(?:snap|move)\s+(\w+)\s+(?:to\s+the\s+)?(\w+)", text_lower
        )
        if (
            _snap_m
            and any(p in text_lower for p in ["snap", "move"])
            and any(
                d in text_lower for d in ["left", "right", "up", "down", "fullscreen"]
            )
        ):
            app_n = _snap_m.group(1).strip()
            dir_n = _snap_m.group(2).strip()
            self._speak(self.app_ctrl.snap_window(app_n, dir_n))
            return ""

        # ── Window: always on top ─────────────────────────────
        if "always on top" in text_lower or "pin on top" in text_lower:
            _aot_m = _re_ac.search(
                r"(?:pin|keep|make|set)\s+(\w+)\s+(?:always\s+on\s+top|on\s+top)",
                text_lower,
            )
            app = _aot_m.group(1).strip() if _aot_m else ""
            if app:
                self._speak(self.app_ctrl.always_on_top(app))
                return ""

        # ── Kill frozen app ────────────────────────────────────
        if any(
            p in text_lower
            for p in [
                "kill frozen",
                "force kill",
                "app not responding",
                "frozen app",
                "unresponsive app",
            ]
        ):
            self._speak("Checking for frozen apps...")
            self._speak(self.app_ctrl.kill_frozen_app())
            return ""

        # ── Restart app ────────────────────────────────────────
        _rst_m = _re_ac.search(r"restart\s+(.+)", text_lower)
        if _rst_m and "restart" in text_lower:
            app = _rst_m.group(1).strip()
            self._speak(f"Restarting {app}...")
            self._speak(self.app_ctrl.restart_app(app))
            return ""

        # ── Auto-close after N minutes ─────────────────────────
        # "close Chrome in 30 minutes"
        _ac_m = _re_ac.search(r"close\s+(\w+)\s+in\s+(\d+)\s*min", text_lower)
        if _ac_m:
            app = _ac_m.group(1).strip()
            mins = int(_ac_m.group(2))
            self._speak(self.app_ctrl.auto_close_after(app, mins))
            return ""

        # ── App usage tracker ──────────────────────────────────
        if any(
            p in text_lower
            for p in [
                "app usage",
                "how long did i use",
                "what apps did i use",
                "usage report",
                "how long have i been",
            ]
        ):
            self._speak(self.app_ctrl.get_usage_report())
            return ""

        if any(
            p in text_lower
            for p in [
                "recent apps",
                "apps i used today",
                "recently used",
                "what's open",
            ]
        ):
            self._speak(self.app_ctrl.get_recent_apps())
            return ""

        # ── Kill by CPU ────────────────────────────────────────
        if any(
            p in text_lower
            for p in [
                "kill high cpu",
                "kill cpu hog",
                "stop high cpu",
                "task using most cpu",
            ]
        ):
            self._speak("Checking CPU usage...")
            self._speak(self.app_ctrl.kill_by_cpu(70))
            return ""

        # ── Browser: New / Close tab ───────────────────────────
        if any(p in text_lower for p in ["new tab", "open tab", "open new tab"]):
            self._speak(self.app_ctrl.new_tab())
            return ""
        if any(p in text_lower for p in ["close tab", "close this tab"]):
            self._speak(self.app_ctrl.close_tab())
            return ""
        if "next tab" in text_lower:
            self._speak(self.app_ctrl.next_tab())
            return ""
        if "previous tab" in text_lower or "last tab" in text_lower:
            self._speak(self.app_ctrl.prev_tab())
            return ""

        # ── Browser: Incognito ─────────────────────────────────
        if any(
            p in text_lower
            for p in ["incognito", "private mode", "private browser", "inprivate"]
        ):
            browser = "edge" if "edge" in text_lower else "chrome"
            self._speak(self.app_ctrl.open_incognito(browser))
            return ""

        # ── Browser: Open specific URL ─────────────────────────
        # "open youtube.com in Chrome" / "open github"
        _url_m = _re_ac.search(
            r"open\s+([a-zA-Z0-9\.\-]+\.[a-zA-Z]{2,}(?:/\S*)?)", text_lower
        )
        if _url_m:
            url = _url_m.group(1).strip()
            browser = (
                "chrome"
                if "chrome" in text_lower
                else ("edge" if "edge" in text_lower else None)
            )
            self._speak(f"Opening {url}...")
            self._speak(self.app_ctrl.open_url(url, browser))
            return ""

        # ── Browser: Open multiple sites ───────────────────────
        # "open gmail youtube and whatsapp"
        if any(
            site in text_lower
            for site in [
                "gmail",
                "youtube",
                "github",
                "whatsapp web",
                "instagram",
                "twitter",
                "notion",
                "chatgpt",
                "netflix",
                "linkedin",
            ]
        ) and any(p in text_lower for p in ["open", "launch"]):
            from skills.app_control import SITE_MAP

            sites = [s for s in SITE_MAP if s in text_lower]
            if len(sites) >= 2:
                self._speak(f"Opening {', '.join(sites)}.")
                self._speak(self.app_ctrl.open_multiple_sites(sites))
                return ""

        # ── Chrome profile + site ──────────────────────────────
        # "open gmail in Sarvani's Chrome"
        if "chrome" in text_lower and any(
            p in text_lower for p in ["sarvani", "ben", "aww", "srinivas", "ganesh"]
        ):
            from skills.app_control import SITE_MAP

            profile = next(
                (
                    p
                    for p in ["sarvani", "ben", "aww", "srinivas", "ganesh"]
                    if p in text_lower
                ),
                "srinivas",
            )
            url = next((v for k, v in SITE_MAP.items() if k in text_lower), "")
            self._speak(self.app_ctrl.open_chrome_profile(profile, url))
            return ""

        # ── Settings pages ─────────────────────────────────────
        # "open wifi settings" / "open display settings"
        if "settings" in text_lower:
            from skills.app_control import SETTINGS_MAP

            page = next((k for k in SETTINGS_MAP if k in text_lower), "")
            self._speak(self.app_ctrl.open_settings(page))
            return ""

        # ── System apps ────────────────────────────────────────
        if any(p in text_lower for p in ["task manager", "open task manager"]):
            self._speak(self.app_ctrl.open_task_manager())
            return ""
        if "device manager" in text_lower:
            self._speak(self.app_ctrl.open_device_manager())
            return ""
        if "startup apps" in text_lower or "startup programs" in text_lower:
            self._speak(self.app_ctrl.open_startup_apps())
            return ""
        if "control panel" in text_lower:
            section = (
                text_lower.replace("control panel", "").replace("open", "").strip()
            )
            self._speak(self.app_ctrl.open_control_panel(section))
            return ""

        # ── Media: pause all ──────────────────────────────────
        if any(
            p in text_lower
            for p in ["pause all", "stop all media", "pause music", "pause everything"]
        ):
            self._speak(self.app_ctrl.pause_all_media())
            return ""

        # ── VLC ────────────────────────────────────────────────
        if "vlc" in text_lower:
            if any(p in text_lower for p in ["next", "skip"]):
                self._speak(self.app_ctrl.vlc_next())
                return ""
            if any(p in text_lower for p in ["play", "pause", "resume"]):
                self._speak(self.app_ctrl.vlc_play_pause())
                return ""

        # ── Smart modes ────────────────────────────────────────
        # "activate work mode" / "focus mode on" / "gaming mode"
        _mode_m = _re_ac.search(
            r"(?:activate|enable|turn on|start|switch to)?\s*"
            r"(work|focus|gaming|night|morning)\s*mode",
            text_lower,
        )
        if _mode_m:
            mode = _mode_m.group(1).strip()
            self._speak(f"Activating {mode} mode...")
            result = self.app_ctrl.activate_mode(mode)
            self._speak(result)
            return ""

        # ── App suggestion ─────────────────────────────────────
        if any(
            p in text_lower
            for p in [
                "what should i use to",
                "what app for",
                "best app for",
                "what to use for",
                "which app to",
            ]
        ):
            task = text_lower
            for p in [
                "what should i use to",
                "what app for",
                "best app for",
                "what to use for",
                "which app to",
            ]:
                task = task.replace(p, "").strip()
            self._speak(self.app_ctrl.suggest_app(task))
            return ""

        # ══════════════════════════════════════════════════════
        #  END APP CONTROL
        # ══════════════════════════════════════════════════════

        # ── Shopping sites: always route to shopping skill, never browser_search ──
        # "search amazon for X", "find on flipkart", "search flights to Mumbai"
        _shop_site_kw = ["amazon", "flipkart", "myntra", "makemytrip"]
        _shop_flight_kw = ["flight", "flights", "fly to", "ticket to", "book flight"]
        _shop_hotel_kw = ["hotel", "hotels", "stay in", "accommodation in"]
        _shop_act_kw = [
            "search",
            "find",
            "look for",
            "shop for",
            "buy on",
            "search on",
            "find on",
        ]
        _is_flight_query = any(f in text_lower for f in _shop_flight_kw)
        _is_hotel_query = any(h in text_lower for h in _shop_hotel_kw)
        _is_shop_site = any(s in text_lower for s in _shop_site_kw) and any(
            a in text_lower for a in _shop_act_kw
        )
        if _is_shop_site or _is_flight_query or _is_hotel_query:
            self._speak("On it!")
            _sr = self.shopping.execute(text)
            self._speak(_sr)
            return ""

        intent, _ = parse_intent(text)

        response = ""

        # Wrap Gemini prompts in current language instruction
        # (used below in the fallback Gemini call)
        def _ask_gemini(prompt: str) -> str:
            ml_prompt = self.lang.make_prompt_multilingual(prompt)
            return self.gemini.ask(ml_prompt)

        # ── System control ────────────────────────────────────
        if intent == "open_app":
            app = extract_app_name(text)
            result = self.app_ctrl.open_app(app)

            # Chrome profile selection
            if result and result.startswith("CHOOSE_PROFILE:"):
                profiles = result.replace("CHOOSE_PROFILE:", "").split(",")
                profile_list = ", ".join(profiles)
                self._speak(f"Which Chrome profile? Say a name: {profile_list}")
                print(f"\033[93m  Profiles: {profile_list}\033[0m")

                # Listen for profile choice
                choice = self._get_input()
                if choice:
                    # Try to open Chrome with the chosen profile
                    result = self.app_ctrl.open_app(f"chrome {choice}")
                    if result and not result.startswith("CHOOSE_PROFILE:"):
                        self._speak(result)
                    else:
                        self._speak(f"Opening Chrome with {choice}!")
                        self.app_ctrl.open_app(f"chrome person 1")  # fallback
                else:
                    self._speak("No profile selected. Opening default.")
                    self.app_ctrl.open_app("chrome person 1")
            else:
                self._speak(result or f"Opening {app}!")
            return ""  # Already spoken

        elif intent == "close_app":
            app = extract_app_name(text)
            response = self.app_ctrl.close_app(app)

        elif intent == "system_volume":
            text_lower = text.lower()
            if any(w in text_lower for w in ["up", "increase", "louder", "raise"]):
                self._speak("Turning volume up!")
                response = self.system.volume_up()
            elif any(w in text_lower for w in ["down", "decrease", "quieter", "lower"]):
                self._speak("Turning volume down.")
                response = self.system.volume_down()
            else:
                self._speak("Muting.")
                response = self.system.mute()

        elif intent == "system_brightness":
            text_lower = text.lower()
            if any(w in text_lower for w in ["up", "increase", "brighter", "raise"]):
                self._speak("Brightness going up!")
                response = self.system.brightness_up()
            else:
                self._speak("Dimming the screen.")
                response = self.system.brightness_down()

        elif intent == "screenshot":
            self._speak("Taking a screenshot now!")
            response = self.system.take_screenshot()

        elif intent == "shutdown":
            text_lower = text.lower()
            if "restart" in text_lower or "reboot" in text_lower:
                self._speak("Restarting your laptop. See you soon!")
                response = self.system.restart()
            elif "sleep" in text_lower or "hibernate" in text_lower:
                self._speak("Going to sleep. Goodnight!")
                response = self.system.sleep()
            elif "cancel" in text_lower:
                self._speak("Shutdown cancelled. I'll keep running!")
                response = self.system.cancel_shutdown()
            else:
                self._speak("Shutting down. Goodbye, Srini!")
                response = self.system.shutdown()

        # ── Info & Internet ───────────────────────────────────
        elif intent == "weather":
            # ── Extract city from command ─────────────────────
            # Handles: "weather in Delhi", "Delhi weather",
            #          "what's the weather in Hyderabad",
            #          "weather of Andhra Pradesh", "Telangana weather"
            _weather_city = None

            # State → capital/major city mapping
            _STATE_TO_CITY = {
                "telangana": "Hyderabad",
                "andhra pradesh": "Vijayawada",
                "andhra": "Vijayawada",
                "tamil nadu": "Chennai",
                "karnataka": "Bangalore",
                "maharashtra": "Mumbai",
                "gujarat": "Ahmedabad",
                "rajasthan": "Jaipur",
                "uttar pradesh": "Lucknow",
                "up": "Lucknow",
                "bihar": "Patna",
                "west bengal": "Kolkata",
                "bengal": "Kolkata",
                "kerala": "Thiruvananthapuram",
                "punjab": "Chandigarh",
                "haryana": "Chandigarh",
                "madhya pradesh": "Bhopal",
                "mp": "Bhopal",
                "odisha": "Bhubaneswar",
                "assam": "Guwahati",
                "jharkhand": "Ranchi",
                "uttarakhand": "Dehradun",
                "himachal pradesh": "Shimla",
                "goa": "Panaji",
                "chhattisgarh": "Raipur",
                "tripura": "Agartala",
                "manipur": "Imphal",
                "meghalaya": "Shillong",
                "nagaland": "Kohima",
                "arunachal pradesh": "Itanagar",
                "sikkim": "Gangtok",
                "mizoram": "Aizawl",
                "jammu and kashmir": "Srinagar",
                "j&k": "Srinagar",
                "ladakh": "Leh",
            }

            # Try to extract city from command text
            _wt = text_lower

            # Check for state names first (longest match first)
            for state, capital in sorted(
                _STATE_TO_CITY.items(), key=lambda x: -len(x[0])
            ):
                if state in _wt:
                    _weather_city = capital
                    break

            # If no state matched, try "weather in/of/for CITY" pattern
            if not _weather_city:
                _city_m = re.search(
                    r"(?:weather|temperature|climate|forecast)\s+(?:in|of|for|at)\s+([a-zA-Z\s]+?)(?:\?|$|,|\s+today|\s+now|\s+tonight)",
                    text_lower,
                )
                if _city_m:
                    _weather_city = _city_m.group(1).strip().title()

            # Try "CITY weather" pattern
            if not _weather_city:
                _city_m2 = re.search(
                    r"^([a-zA-Z\s]{3,25}?)\s+(?:weather|temperature|climate|forecast)",
                    text_lower,
                )
                if _city_m2:
                    _candidate = _city_m2.group(1).strip()
                    # Skip generic words that aren't cities
                    _skip = {
                        "what",
                        "the",
                        "current",
                        "today",
                        "tell",
                        "me",
                        "check",
                        "get",
                        "show",
                    }
                    if _candidate not in _skip and len(_candidate) > 2:
                        _weather_city = _candidate.title()

            # Try "in CITY" anywhere in the command
            if not _weather_city:
                _in_m = re.search(
                    r"\bin\s+([A-Za-z][a-zA-Z\s]{2,25}?)(?:\?|$|,|\s+today|\s+now)",
                    text_lower,
                )
                if _in_m:
                    _candidate = _in_m.group(1).strip()
                    _skip2 = {"my", "the", "a", "an", "india", "this", "that"}
                    if _candidate not in _skip2:
                        _weather_city = _candidate.title()

            if _weather_city:
                self._speak(f"Checking weather in {_weather_city}.")
            else:
                self._speak("Let me check the weather for you!")

            response = self.weather.get_current(_weather_city)

        elif intent == "news":
            self._speak("Fetching the latest headlines!")
            category = self.news.detect_category(text)
            response = self.news.get_headlines(category)

        elif intent == "youtube":
            query = extract_search_query(text)
            self._speak(f"Opening YouTube for {query}!")
            response = self.browser.youtube_play(query)

        elif intent == "media":
            self._speak("Got it!")
            response = self.media.execute(text)

        elif intent == "browser_search":
            query = extract_search_query(text)
            self._speak(f"Searching for {query}!")
            response = self.browser.search_in_browser(query)

        elif intent == "google_search":
            query = extract_search_query(text)
            self._speak(f"Searching for {query}!")
            # Check if Chrome/browser is the active window
            try:
                import pygetwindow as gw

                active = gw.getActiveWindow()
                if active and any(
                    b in active.title.lower()
                    for b in ["chrome", "edge", "firefox", "brave"]
                ):
                    response = self.browser.search_in_browser(query)
                else:
                    response = self.browser.google_search(query)
            except Exception:
                response = self.browser.google_search(query)

        elif intent == "shopping":
            self._speak("Let me search that for you!")
            response = self.shopping.execute(text)

        elif intent == "wikipedia":
            # Conversational / opinion / ELI5 queries → Gemini, not Wikipedia
            _wiki_casual = any(
                m in text_lower
                for m in [
                    "like i'm",
                    "like i am",
                    "like im ",
                    "like a child",
                    "in simple terms",
                    "for dummies",
                    "easy explanation",
                    "using an analogy",
                    "real world analogy",
                    "give me an analogy",
                    "what do you think",
                    "your opinion",
                    "your take",
                    "should i ",
                    "would you ",
                    "help me understand",
                    "i feel",
                    "i'm feeling",
                    "genuinely surprising",
                    "tell me something surprising",
                    "fun fact",
                    "like i was 5",
                    "like i was 10",
                    "like i was 15",
                    "like a 5 year",
                    "like a 10 year",
                    "like a 15 year",
                ]
            )
            if _wiki_casual:
                response = _ask_gemini(text)
            else:
                query = extract_search_query(text)
                if not query:
                    query = text
                self._speak(f"Looking that up...")
                response = self.browser.wikipedia_search(query)

        # ── Files ─────────────────────────────────────────────
        elif intent == "file_create":
            self._speak("Creating your note!")
            response = self.files.write_note(text)

        elif intent == "file_open":
            m = stdlib_re.search(r"open (?:file )?(.+)", text, stdlib_re.IGNORECASE)
            filename = m.group(1).strip() if m else text
            self._speak(f"Opening {filename}!")
            response = self.files.open_file(filename)

        # ── Reminders ─────────────────────────────────────────
        elif intent in ("reminder", "timer"):
            if intent == "timer":
                m = stdlib_re.search(r"(\d+)\s*(second|minute|hour)", text.lower())
                if m:
                    amount = int(m.group(1))
                    unit = m.group(2)
                    secs = amount * (
                        1 if "second" in unit else 60 if "minute" in unit else 3600
                    )
                    self._speak(f"Setting a timer for {amount} {unit}s!")
                    response = self.reminder.set_timer(secs)
                else:
                    response = "How many seconds or minutes for the timer?"
            else:
                mins, at_time, msg = self.reminder.parse_time_from_text(text)
                if mins or at_time:
                    self._speak("Got it! Setting your reminder.")
                    response = self.reminder.set_reminder(
                        msg, minutes=mins, at_time=at_time
                    )
                else:
                    response = "Please say when to remind you, like 'in 30 minutes' or 'at 6 PM'."

        # ── Vision ────────────────────────────────────────────
        elif intent == "vision_screen":
            self._speak("Let me take a look at your screen!")
            response = self.vision.analyze_screen()

        elif intent in ("vision_image",):
            self._speak("Analyzing the image now!")
            response = self.vision.analyze_screen(
                "What do you see in this image? Describe it in detail."
            )

        # ── Phase 4: Email ────────────────────────────────────
        elif intent == "send_email":
            to_name, subject, body = self.email.parse_email_command(text)
            if to_name and body:
                self._speak(f"Sending email to {to_name}. Just a moment!")
                response = self.email.send_email(to_name, subject, body)
            else:
                response = "Who should I email and what should I say? For example: email mom saying I'll be late."

        elif intent == "read_email":
            self._speak("Let me check your emails!")
            if "unread" in text.lower():
                response = self.email.check_unread()
            else:
                response = self.email.read_recent_emails(5)

        # ── Phase 4: WhatsApp ─────────────────────────────────

        # ── WA: Stats / Analytics ─────────────────────────────
        # WA: Add Contact
        # "add contact Teja" / "add Teja to contacts" / "save contact boss as Kiran"
        elif any(
            p in text_lower
            for p in ["add contact", "add to contacts", "save contact", "new contact"]
        ):
            _ac_m = re.search(
                r"(?:add|save|new)\s+contact\s+(\w+)(?:\s+as\s+(\w+))?", text_lower
            )
            if not _ac_m:
                _ac_m = re.search(r"add\s+(\w+)\s+to\s+contacts", text_lower)
            if _ac_m:
                _ac_name = _ac_m.group(1).strip()
                _ac_display = (
                    (_ac_m.group(2) or "").strip() if len(_ac_m.groups()) > 1 else ""
                )
                response = self.whatsapp.add_contact(_ac_name, _ac_display)
            else:
                response = (
                    "Say: 'add contact Teja' or 'add contact boss as Kiran', sir."
                )

        # WA: List Contacts
        elif any(
            p in text_lower
            for p in [
                "list contacts",
                "my contacts",
                "show contacts",
                "who are my contacts",
            ]
        ):
            response = self.whatsapp.list_contacts()

        # WA: Daily summary / what did I send today
        elif any(
            p in text_lower
            for p in [
                "what did i send today",
                "what did i send",
                "whatsapp daily",
                "daily summary whatsapp",
            ]
        ):
            response = self.whatsapp.daily_summary()

        # WA: Summarize chat
        elif any(
            p in text_lower
            for p in [
                "summarize my chat",
                "summarise my chat",
                "summarize chat",
                "summarise chat",
            ]
        ):
            _sum_m = re.search(
                r"(?:summarize|summarise)\s+(?:my\s+)?chat\s+with\s+(\w+)", text_lower
            )
            _sum_contact = _sum_m.group(1) if _sum_m else ""
            if _sum_contact:
                self._speak(f"Summarizing chat with {_sum_contact}, sir.")
                response = self.whatsapp.summarize_chat(_sum_contact)
            else:
                response = "Who should I summarize the chat with, sir?"

        # WA: Contact Status (online / last seen)
        # Catches: "is Sarvani online" / "last seen Sarvani" /
        #          "last seen of Sarvani" / "check Sarvani status" /
        #          "when did Sarvani come online" / "Sarvani online"
        elif re.search(
            r"(?:is\s+\w+\s+online|last\s+seen\s+(?:of\s+)?\w+|"
            r"when\s+(?:was|did)\s+\w+|check\s+\w+\s+status|"
            r"\w+\s+online\??|\w+\s+last\s+seen)",
            text_lower,
        ):
            _stat_m = re.search(
                r"(?:is\s+(\w+)\s+online|"
                r"last\s+seen\s+(?:of\s+)?(\w+)|"
                r"when\s+(?:was|did)\s+(\w+)|"
                r"check\s+(\w+)\s+status|"
                r"(\w+)\s+(?:online|last\s+seen))",
                text_lower,
            )
            if _stat_m:
                # Pick whichever group matched
                _stat_contact = next((g for g in _stat_m.groups() if g), "").strip()
                # Filter out noise words
                if _stat_contact in {"when", "is", "check", "the", "of", "a"}:
                    _stat_contact = ""
                if _stat_contact:
                    self._speak(f"Checking {_stat_contact}'s status on WhatsApp, sir.")
                    response = self.whatsapp.get_contact_status(_stat_contact)
                else:
                    response = "Who should I check status for, sir?"
            else:
                response = "Who should I check status for, sir?"

        # WA: Emoji-only send
        # "send heart emoji to mom" / "send fire emoji to Sarvani"
        # "emoji to NAME" (no emoji name → default to ❤️)
        elif re.search(r"(?:send\s+)?(?:\w+\s+)?emoji\s+to\s+\w+", text_lower):
            _em_m = re.search(r"(?:send\s+)?(\w+)\s+emoji\s+to\s+(\w+)", text_lower)
            _em_bare = re.search(r"emoji\s+to\s+(\w+)", text_lower)
            if _em_m:
                _em_emoji = _em_m.group(1).strip()
                _em_contact = _em_m.group(2).strip()
                self._speak(f"Sending {_em_emoji} emoji to {_em_contact}, sir.")
                response = self.whatsapp.send_emoji_only(_em_contact, _em_emoji)
            elif _em_bare:
                _em_contact = _em_bare.group(1).strip()
                self._speak(f"Sending heart emoji to {_em_contact}, sir.")
                response = self.whatsapp.send_emoji_only(_em_contact, "heart")
            else:
                response = "Say: 'send heart emoji to mom', sir."

        elif any(
            p in text_lower
            for p in [
                "whatsapp stats",
                "message stats",
                "who do i message most",
                "most messaged contact",
                "most messaged",
                "who do i text most",
                "whatsapp analytics",
            ]
        ):
            response = self.whatsapp.get_stats()
            # If asking specifically about most messaged
            if any(
                w in text_lower for w in ["most messaged", "message most", "text most"]
            ):
                response = self.whatsapp.most_messaged_contact()

        # ── WA: Daily summary (also handled earlier — whatsapp summary alias) ───
        elif any(
            p in text_lower
            for p in ["whatsapp summary", "daily summary whatsapp", "whatsapp daily"]
        ):
            response = self.whatsapp.daily_summary()

        # ── WA: Undo last message ─────────────────────────────
        elif any(
            p in text_lower
            for p in [
                "undo last message",
                "delete that message",
                "delete last message",
                "unsend message",
                "delete for everyone",
            ]
        ):
            self._speak("Trying to delete the last message, sir.")
            response = self.whatsapp.undo_last_message()

        # ── WA: Reply to last contact ─────────────────────────
        elif text_lower.startswith("reply ") or "reply to last" in text_lower:
            reply_text = re.sub(r"^reply\s+", "", text, flags=re.IGNORECASE).strip()
            if reply_text:
                self._speak(f"Replying: {reply_text}")
                response = self.whatsapp.reply_to_last(reply_text, self._stop_event)
            else:
                response = "What should I reply, sir?"

        # ── WA: Forward last message ──────────────────────────
        elif any(
            p in text_lower
            for p in [
                "forward last message to",
                "forward message to",
                "forward that to",
            ]
        ):
            m = re.search(r"forward (?:last )?message to (.+)", text_lower)
            if m:
                fwd_contact = m.group(1).strip()
                self._speak(f"Forwarding to {fwd_contact}, sir.")
                response = self.whatsapp.forward_last_message(
                    fwd_contact, self._stop_event
                )
            else:
                response = "Who should I forward to, sir?"

        # ── WA: Schedule message ──────────────────────────────
        elif any(
            p in text_lower
            for p in [
                "schedule message",
                "schedule a message",
                "schedule whatsapp",
                "send message at ",
                "remind me to message",
                "send good morning at",
                "send good night at",
                "message rahul at",
                "message mom at",
            ]
        ):
            con, msg, t = self.whatsapp.parse_schedule_command(text)
            if con and msg and t:
                self._speak(f"Scheduling message to {con} at {t}, sir.")
                response = self.whatsapp.schedule_message(con, msg, t)
            else:
                response = (
                    "To schedule, say: 'schedule message to mom good night at 22:00'"
                )

        # ── WA: List scheduled ────────────────────────────────
        elif any(
            p in text_lower
            for p in ["list scheduled", "show scheduled", "what's scheduled"]
        ):
            response = self.whatsapp.list_scheduled()

        # ── WA: Send screenshot ───────────────────────────────
        elif any(
            p in text_lower for p in ["send screenshot to", "share screenshot with"]
        ):
            m = re.search(r"(?:send|share) screenshot (?:to|with) (.+)", text_lower)
            if m:
                sc_contact = m.group(1).strip()
                self._speak(f"Taking and sending screenshot to {sc_contact}, sir.")
                response = self.whatsapp.send_screenshot(sc_contact)
            else:
                response = "Who should I send the screenshot to, sir?"

        # ── WA: AI Compose and send ───────────────────────────
        elif any(
            p in text_lower
            for p in [
                "compose message",
                "write message to",
                "send formal",
                "send casual",
                "compose a formal",
                "compose formal",
                "compose an apology",
                "compose apology",
                "write a formal",
                "write an apology",
                "draft a message",
                "draft message",
            ]
        ):
            # Detect tone
            tone = (
                "formal"
                if "formal" in text_lower
                else "apologetic"
                if any(
                    w in text_lower
                    for w in ["apology", "apologetic", "sorry", "apologies"]
                )
                else "friendly"
            )
            # Extract contact
            _cmp_m = re.search(
                r"(?:compose|write|draft|send)\s+(?:a\s+)?(?:message|formal|casual|apology|apologies|sorry)?\s*(?:message\s+)?to\s+(?:my\s+)?(\w+)\s*(.*)?",
                text_lower,
            )
            if _cmp_m:
                ai_contact = _cmp_m.group(1).strip()
                ai_msg_hint = (_cmp_m.group(2) or "").strip()
                # Generate the message with Gemini
                if not ai_msg_hint:
                    ai_msg_hint = f"compose a {tone} message"
                _composed = self.gemini.ask(
                    f"Write a {tone} WhatsApp message to send to '{ai_contact}'. "
                    f"Context: {ai_msg_hint}. "
                    "Return ONLY the message text, no explanation, no quotes, no markdown."
                )
                self._speak(f"Here's what I'll send to {ai_contact}: {_composed}")
                self._speak("Should I send it? Say yes to confirm.")
                try:
                    import speech_recognition as _sr_cmp

                    _rec_cmp = _sr_cmp.Recognizer()
                    with _sr_cmp.Microphone() as _src_cmp:
                        _rec_cmp.adjust_for_ambient_noise(_src_cmp, duration=0.2)
                        _aud_cmp = _rec_cmp.listen(
                            _src_cmp, timeout=4, phrase_time_limit=3
                        )
                    _conf_cmp = _rec_cmp.recognize_google(_aud_cmp).lower()
                    if any(
                        w in _conf_cmp for w in ["yes", "yeah", "send", "ok", "sure"]
                    ):
                        response = self.whatsapp.send_message(ai_contact, _composed)
                    else:
                        response = "Message not sent, sir. Kept in memory if you change your mind."
                except Exception:
                    response = f"Composed: '{_composed}' — say 'send to {ai_contact}' to send it."
            else:
                response = "Who should I compose the message for, sir? Say: 'compose formal message to boss'"

        # "tell Sarvani I'll be late" — narrow: "tell NAME ..." (not "tell me")
        elif re.match(r"tell\s+(?!me\b|the\b|a\b)(\w+)\s+(.*)", text_lower):
            _tell_m = re.match(r"tell\s+(?!me\b|the\b|a\b)(\w+)\s+(.*)", text_lower)
            _ai_tell_contact = _tell_m.group(1).strip()
            _ai_tell_msg = _tell_m.group(2).strip()
            _tell_tone = "apologetic" if "sorry" in text_lower else "friendly"
            self._speak(f"Composing message to {_ai_tell_contact}, sir.")
            response = self.whatsapp.compose_and_send(
                _ai_tell_contact, _ai_tell_msg, tone=_tell_tone
            )

        # ── WA: Translate and send ────────────────────────────
        # "send good morning in Hindi to mom" / "send in Tamil to NAME" / "translate and send"
        elif (
            re.search(
                r" in (hindi|tamil|telugu|kannada|malayalam|english|"
                r"french|spanish|arabic|chinese|japanese)",
                text_lower,
            )
            or "translate and send" in text_lower
        ):
            _lang_re = re.search(
                r"(.+?)\s+in\s+(hindi|tamil|telugu|kannada|malayalam|english|"
                r"french|spanish|arabic|chinese|japanese)",
                text_lower,
            )
            if _lang_re:
                # Strip noise prefixes from the message part
                _raw_msg = _lang_re.group(1)
                _language = _lang_re.group(2).title()
                for _pfx in ["send ", "translate ", "say ", "message "]:
                    _raw_msg = _raw_msg.replace(_pfx, "").strip()
                translate_text = _raw_msg.strip()
                language = _language
                # Extract contact from "to NAME" anywhere in the sentence
                to_match = re.search(r"\bto\s+(\w+)", text_lower)
                if to_match:
                    tl_contact = to_match.group(1)
                    self._speak(f"Translating to {language} and sending, sir.")
                    response = self.whatsapp.translate_and_send(
                        tl_contact, translate_text, language
                    )
                else:
                    response = "Who should I send the translated message to, sir?"
            else:
                response = "Say: 'send good morning in Hindi to mom'"

        # ── WA: Group message ─────────────────────────────────
        elif any(
            p in text_lower
            for p in ["send to group", "message group", "whatsapp group"]
        ):
            m = re.search(r"(?:send to|message) group (.+?) (.+)", text_lower)
            if m:
                grp_name = m.group(1).strip()
                grp_msg = m.group(2).strip()
                self._speak(f"Sending to group {grp_name}, sir.")
                response = self.whatsapp.send_to_group(
                    grp_name, grp_msg, self._stop_event
                )
            else:
                response = "Say: 'send to group College hey everyone'"

        # ── WA: Bulk send ─────────────────────────────────────
        elif any(
            p in text_lower
            for p in ["send to multiple", "message everyone", "send to all"]
        ):
            contacts_bulk = self.whatsapp.parse_bulk_contacts(text)
            bulk_msg = re.search(r"saying (.+)", text_lower)
            if contacts_bulk and bulk_msg:
                self._speak(f"Sending to {len(contacts_bulk)} contacts, sir.")
                response = self.whatsapp.send_to_multiple(
                    contacts_bulk, bulk_msg.group(1), self._stop_event
                )
            else:
                response = (
                    "Say: 'send to multiple mom dad friend saying happy new year'"
                )

        # ── WA: Auto response ─────────────────────────────────
        elif any(
            p in text_lower
            for p in ["enable auto response", "auto reply on", "turn on auto reply"]
        ):
            msg_match = re.search(
                r"(?:enable auto response|auto reply on)\s*(.*)", text_lower
            )
            ar_msg = msg_match.group(1).strip() if msg_match else ""
            response = self.whatsapp.enable_auto_response(ar_msg)

        elif any(
            p in text_lower
            for p in ["disable auto response", "auto reply off", "turn off auto reply"]
        ):
            response = self.whatsapp.disable_auto_response()

        # ── WA: Check / Read messages ─────────────────────────
        elif any(
            p in text_lower
            for p in [
                "any unread",
                "unread whatsapp",
                "what did i miss",
                "new messages",
                "any messages",
                "read whatsapp",
            ]
        ):
            self._speak("Checking your WhatsApp, sir.")
            try:
                from skills.notifications_checker import NotificationsChecker

                result = NotificationsChecker().check_whatsapp_only()
                self._speak(result)
            except Exception:
                self._speak("Please open WhatsApp Desktop to see your messages.")

        # ── WA: SEND (main flow, with confirmation) ───────────
        elif intent == "whatsapp":
            contact, message = self.whatsapp.parse_whatsapp_command(text)
            if contact:
                if not message:
                    message = "Hi"
                self._speak(
                    f"Ready to send '{message}' to {contact}. "
                    f"Say yes to confirm, or stop to cancel."
                )
                confirmed = False
                try:
                    import speech_recognition as _sr

                    _r = _sr.Recognizer()
                    with _sr.Microphone() as _src:
                        _r.adjust_for_ambient_noise(_src, duration=0.3)
                        _audio = _r.listen(_src, timeout=4, phrase_time_limit=3)
                    # Use recognize_google (fast) for yes/no; Whisper fallback
                    try:
                        _conf = _r.recognize_google(_audio).lower().strip()
                    except Exception:
                        _conf = (
                            _r.recognize_whisper(
                                _audio, model="tiny", language="english"
                            )
                            .lower()
                            .strip()
                        )
                    if any(
                        w in _conf
                        for w in [
                            "yes",
                            "yeah",
                            "yep",
                            "send",
                            "confirm",
                            "ok",
                            "okay",
                            "do it",
                        ]
                    ):
                        confirmed = True
                    elif any(w in _conf for w in ["stop", "cancel", "no", "abort"]):
                        self._speak("Cancelled, sir.")
                        response = ""
                    else:
                        self._speak(f"I heard '{_conf}'. Cancelled to be safe.")
                        response = ""
                except Exception:
                    self._speak("Couldn't hear confirmation. Cancelled, sir.")
                    response = ""
                if confirmed:
                    self._speak(f"Sending to {contact}, sir!")
                    response = self.whatsapp.send_message(
                        contact, message, stop_event=self._stop_event
                    )
            else:
                response = "Who should I message? Say: message to Sarvani hello"

        # ── Time & Date ───────────────────────────────────────
        elif intent == "time_date":
            now = datetime.now()
            text_lower = text.lower()
            # Check if asking about another city/timezone
            _tz_cities = {
                "new york": "America/New_York",
                "los angeles": "America/Los_Angeles",
                "london": "Europe/London",
                "paris": "Europe/Paris",
                "tokyo": "Asia/Tokyo",
                "dubai": "Asia/Dubai",
                "singapore": "Asia/Singapore",
                "sydney": "Australia/Sydney",
                "mumbai": "Asia/Kolkata",
                "delhi": "Asia/Kolkata",
                "chennai": "Asia/Kolkata",
                "kolkata": "Asia/Kolkata",
                "beijing": "Asia/Shanghai",
                "shanghai": "Asia/Shanghai",
                "moscow": "Europe/Moscow",
                "berlin": "Europe/Berlin",
                "toronto": "America/Toronto",
                "chicago": "America/Chicago",
                "bangkok": "Asia/Bangkok",
                "seoul": "Asia/Seoul",
                "istanbul": "Europe/Istanbul",
                "cairo": "Africa/Cairo",
                "johannesburg": "Africa/Johannesburg",
                "nairobi": "Africa/Nairobi",
                "mexico city": "America/Mexico_City",
                "sao paulo": "America/Sao_Paulo",
                "buenos aires": "America/Argentina/Buenos_Aires",
            }
            _found_tz = None
            for city, tz in _tz_cities.items():
                if city in text_lower:
                    _found_tz = (city, tz)
                    break
            if _found_tz:
                try:
                    import zoneinfo

                    _city_name, _tz_name = _found_tz
                    _tz = zoneinfo.ZoneInfo(_tz_name)
                    from datetime import timezone as _tzmod

                    _city_time = datetime.now(_tz)
                    response = f"It's {_city_time.strftime('%I:%M %p')} in {_city_name.title()} right now, sir."
                except Exception:
                    response = f"I'd check Google for the current time in {_found_tz[0].title()}, sir."
            elif "date" in text_lower or "day" in text_lower:
                response = f"Today is {now.strftime('%A, %B %d, %Y')}."
            else:
                response = f"The time is {now.strftime('%I:%M %p')}."

        # ── Conversation control ──────────────────────────────
        elif intent == "reset":
            self.gemini.reset_conversation()
            response = "Conversation cleared. Fresh start!"

        elif intent == "stop":
            # Stop notification watcher gracefully
            if self.notif_watcher:
                self.notif_watcher.stop()
            response = f"Goodbye, {self.prefs.name}! Shutting down JARVIS."
            self._speak(response)
            self._running = False
            return response

        # ── Jokes ─────────────────────────────────────────────
        elif intent == "joke":
            self._speak("Oh, I've got a good one!")
            response = self.gemini.ask(
                "Tell me a short, funny tech or nerdy joke. Keep it to 2-3 sentences max."
            )

        # ── Voice Settings ────────────────────────────────────
        # Only triggers when user explicitly says "voice" OR says a
        # known voice name. Does NOT steal weather/time/chat commands.
        elif (
            any(
                t in text_lower
                for t in [
                    "change voice",
                    "switch voice",
                    "change your voice",
                    "use voice",
                    "set voice",
                    "voice to",
                ]
            )
            or self.speaker.find_voice_in_text(text_lower) is not None
        ):
            found = self.speaker.find_voice_in_text(text_lower)
            if found:
                response = self.speaker.set_voice(found)
                # Play test sentence in new voice after small delay
                import threading as _th

                def _demo():
                    import time as _t

                    _t.sleep(1.5)
                    self.speaker.speak("Hello! This is my new voice. Do you like it?")

                _th.Thread(target=_demo, daemon=True).start()
            elif "british" in text_lower:
                response = self.speaker.set_voice("george")
            elif "female" in text_lower:
                response = self.speaker.set_voice("af_bella")
            elif "male" in text_lower or "american" in text_lower:
                response = self.speaker.set_voice("am_adam")
            elif "default" in text_lower or "original" in text_lower:
                response = self.speaker.set_voice("bm_george")
            else:
                response = (
                    "Which voice? Say: change voice to George, Bella, Adam, etc. "
                    "Or say 'show voices' for full list."
                )

        elif (
            "what voice" in text_lower
            or "which voice" in text_lower
            or "current voice" in text_lower
        ):
            response = f"Currently using {self.speaker.current_voice_name()}."

        elif (
            "list voices" in text_lower
            or "what voices" in text_lower
            or "show voices" in text_lower
        ):
            response = (
                "Voices: George, Lewis (British male). "
                "Adam, Michael (American male). "
                "Bella, Nicole, Sarah, Sky, Emma, Isabella (Female). "
                "Say: change voice to [name]."
            )

        elif "speak faster" in text_lower or "talk faster" in text_lower:
            self.speaker.set_rate(self.speaker._rate + 25)
            response = "Speaking faster now!"

        elif "speak slower" in text_lower or "talk slower" in text_lower:
            self.speaker.set_rate(self.speaker._rate - 25)
            response = "Speaking slower now!"

        # ── Fallback: WolframAlpha → Gemini AI ──────────────────
        else:
            # Check if AI is actually available
            _gemini_working = bool(self.gemini._working_model)
            _local_working = (
                self.gemini._local_llm.is_available
                if hasattr(self.gemini, "_local_llm")
                else False
            )

            if not _gemini_working and not _local_working:
                # Both AIs unavailable — give a helpful message
                response = (
                    "My AI is at full capacity right now, sir — the API quota was reached. "
                    "I can still help with system commands, weather, apps, reminders, "
                    "and files. The AI resets at midnight. What else can I do for you?"
                )
            else:
                # 1. Try WolframAlpha for factual/computational questions
                if is_wolfram_query(text):
                    _wa_ans = self.wolfram.query(text)
                    if _wa_ans:
                        response = _wa_ans
                    else:
                        # Wolfram couldn't answer — fall through to Gemini/LLM
                        mem_ctx = self.memory.get_context_for_llm()
                        enriched = (
                            f"{mem_ctx}\n\nSrini says: {text}" if mem_ctx else text
                        )
                        response = self.gemini.ask(enriched)
                else:
                    # 2. Conversational / task question → Gemini with memory context
                    mem_ctx = self.memory.get_context_for_llm()
                    enriched = f"{mem_ctx}\n\nSrini says: {text}" if mem_ctx else text
                    response = self.gemini.ask(enriched)

        # ── Save to memory (works even without AI!) ───────────
        save_response = response if response else "(no AI response — offline)"
        self.history.save(text, save_response, intent, self._session)

        # ── Track for correction learning ─────────────────────
        # Saves what JARVIS did so next message can correct it
        self.corrector.track(text, intent, response or "")

        return response

    # ─── Main Loop (always listening) ─────────────────────────
    def run(self):
        """Start the main voice interaction loop (always active)."""
        self.greet()

        # ── Startup: announce unread message counts ────────────
        try:
            startup_parts = []
            # Check Gmail/WhatsApp/Windows unread counts
            try:
                from skills.notifications_checker import NotificationsChecker
                _startup_checker = NotificationsChecker()
                structured = _startup_checker.check_all_structured()
                for item in structured:
                    if item.get("raw_text"):
                        startup_parts.append(item["raw_text"])
            except Exception as e:
                log.debug(f"Startup checker failed: {e}")

            import time as _t
            _t.sleep(1)  # brief pause after greeting
            if startup_parts:
                self._speak("Quick update. " + " ".join(startup_parts))
            else:
                self._speak("No pending notifications, sir. All clear!")
        except Exception as e:
            log.debug(f"Startup notification check failed: {e}")

        print("\n" + "=" * 55)
        print("  Say something (or type 'quit' to exit)")
        print("  Tip: Talk naturally -- JARVIS understands you!")
        print("=" * 55 + "\n")

        while self._running:
            try:
                text = self._get_input()
                if not text:
                    continue
                response = self.process_command(text)
                if response and self._running:
                    self._speak(response)
            except KeyboardInterrupt:
                print("\n")
                self._speak(f"Goodbye, {self.prefs.name}! Shutting down JARVIS.")
                log.info("JARVIS stopped by user.")
                self.shutdown()
                break
            except Exception as e:
                log.error(f"Main loop error: {e}")
                continue

    # ─── Wake Word Mode (hands-free) ─────────────────────────
    def run_wake_mode(self):
        """
        Hands-free mode:
          Sleep → 'Hey JARVIS' → Process commands for 30s → Sleep.
        Stays awake 30 seconds after each command for follow-ups!
        """
        import threading

        self._wake_event = threading.Event()

        def on_wake():
            self._wake_event.set()

        self.wake_detector = WakeWordDetector(callback=on_wake)
        self.wake_detector.start()

        # Proper startup greeting in wake mode too
        self.greet()
        import time as _t

        _t.sleep(1.5)
        self._speak(
            f"I'm in hands-free mode. Just say 'Hey JARVIS' whenever you need me!"
        )

        print("\n" + "═" * 55)
        print("  🔇 JARVIS is sleeping... Say 'Hey JARVIS' to wake!")
        print("  💡 Stays awake 30 sec after each command")
        print("  💡 Press Ctrl+C to exit")
        print("═" * 55 + "\n")

        while self._running:
            try:
                # ── SLEEP: Wait for wake word ─────────────────
                self._wake_event.wait()
                self._wake_event.clear()

                if not self._running:
                    break

                # ── WAKE UP ──────────────────────────────────
                self.wake_detector.pause()
                # Natural warm greeting instead of cold "Yes?"
                import random as _r

                _hour = datetime.now().hour
                _name = self.prefs.name
                if 5 <= _hour < 12:
                    _wake_greets = [
                        f"Good morning, {_name}! What can I do for you?",
                        f"Morning, {_name}. I'm here — go ahead.",
                        f"Good morning! How can I help you today, {_name}?",
                    ]
                elif 12 <= _hour < 17:
                    _wake_greets = [
                        f"Hey {_name}! What do you need?",
                        f"I'm here, {_name}. What can I help with?",
                        f"Hello! What's on your mind, {_name}?",
                    ]
                elif 17 <= _hour < 21:
                    _wake_greets = [
                        f"Good evening, {_name}. What can I do for you?",
                        f"Evening, {_name}! I'm all ears.",
                        f"Hey! Good evening — what do you need?",
                    ]
                else:
                    _wake_greets = [
                        f"Still up, {_name}? What do you need?",
                        f"I'm here. What can I do for you?",
                        f"Night owl mode. Go ahead, {_name}.",
                    ]
                self._speak(_r.choice(_wake_greets))

                # ── STAY AWAKE LOOP (30 sec timeout) ─────────
                while self._running:
                    text = self._get_input_with_timeout(timeout=30)

                    if not text:
                        # No command for 30 sec → go back to sleep
                        print(
                            "\n\033[90m  🔇 No command for 30 sec — going to sleep...\033[0m"
                        )
                        self._speak("Going to sleep. Say Hey JARVIS to wake me up!")
                        break

                    # Process the command
                    response = self.process_command(text)
                    if response and self._running:
                        self._speak(response)

                    # Stay awake for more commands!
                    print("\033[90m  ⏱️  Listening for 30 more seconds...\033[0m")

                # ── BACK TO SLEEP ─────────────────────────────
                time.sleep(0.5)
                self.wake_detector.resume()

            except KeyboardInterrupt:
                self.wake_detector.stop()
                self._speak(f"Goodbye, {self.prefs.name}!")
                log.info("JARVIS stopped.")
                break
            except Exception as e:
                log.error(f"Wake mode error: {e}")
                self.wake_detector.resume()

    def _get_input(self) -> str:
        """Get input via voice."""
        try:
            return self.listener.listen(timeout=15)
        except Exception as e:
            log.error(f"Listen error: {e}")
            return ""

    def _get_input_with_timeout(self, timeout: int = 30) -> str:
        """Get input with a longer timeout. Returns '' if no speech detected."""
        try:
            return self.listener.listen(timeout=timeout)
        except Exception:
            return ""


# ═══════════════════════════════════════════════════════════════
#  Entry Point
# ═══════════════════════════════════════════════════════════════


def print_banner():
    """Print the JARVIS startup banner."""
    banner = """
\033[94m
     ██╗ █████╗ ██████╗ ██╗   ██╗██╗███████╗
     ██║██╔══██╗██╔══██╗██║   ██║██║██╔════╝
     ██║███████║██████╔╝██║   ██║██║███████╗
██   ██║██╔══██║██╔══██╗╚██╗ ██╔╝██║╚════██║
╚█████╔╝██║  ██║██║  ██║ ╚████╔╝ ██║███████║
 ╚════╝ ╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚═╝╚══════╝
\033[0m
\033[92m         Just A Rather Very Intelligent System\033[0m
\033[90m         Version 2.0.0 | Built for Srini\033[0m
\033[90m         Starting up...\033[0m
"""
    try:
        print(banner)
    except UnicodeEncodeError:
        # Windows cp1252 fallback — plain ASCII banner
        print("\n" + "=" * 50)
        print("  JARVIS — Just A Rather Very Intelligent System")
        print("  Version 2.0.0 | Built for Srini")
        print("  Starting up...")
        print("=" * 50 + "\n")


def face_auth_check(jarvis_instance) -> bool:
    """
    Run face authentication before JARVIS starts.
    Returns True if access granted, False if denied.
    """
    if "--no-face" in sys.argv:
        return True  # Skip face check

    fl = jarvis_instance.face_login
    if fl is None or not fl.is_enrolled():
        # Not enrolled — skip silently (allow access)
        return True

    print()
    print("  🔒 JARVIS SECURITY: Face Authentication Required")
    print("  📷 Look at the camera...")
    print()

    ok, name = fl.authenticate(timeout=30)

    if ok:
        print(f"  ✅ Welcome back, {name}! Access granted.")
        return True
    else:
        print("  🚫 ACCESS DENIED — Unrecognized face.")
        print("  JARVIS is locked. Goodbye.")
        return False


if __name__ == "__main__":
    print_banner()

    # ── Enroll face (first time setup) ────────────────────────────
    if "--enroll-face" in sys.argv:
        from vision.face_login import FaceLogin

        name = "Srini"
        for arg in sys.argv:
            if arg.startswith("--name="):
                name = arg.split("=")[1]
        fl = FaceLogin()
        fl.enroll(name=name)
        sys.exit(0)

    # Quick test mode
    if "--test" in sys.argv:
        log.info("Running in TEST mode...")
        jarvis = JARVIS()
        tests = [
            "what time is it",
            "what's the weather",
            "tell me a joke",
            "open notepad",
        ]
        for t in tests:
            print(f"\n🧪 Test: '{t}'")
            resp = jarvis.process_command(t)
            print(f"✅ Response: {resp[:100]}")
        log.info("Test mode complete.")

    elif "--wake" in sys.argv:
        jarvis = JARVIS()
        if not face_auth_check(jarvis):
            sys.exit(1)
        jarvis.run_wake_mode()

    elif "--gui" in sys.argv:
        from gui.main_window import launch_gui

        jarvis = JARVIS()
        if not face_auth_check(jarvis):
            sys.exit(1)
        jarvis.greet()  # ← Startup greeting in GUI mode
        app, window = launch_gui(jarvis)
        sys.exit(app.exec_())

    else:
        jarvis = JARVIS()
        if not face_auth_check(jarvis):
            sys.exit(1)
        jarvis.run()
