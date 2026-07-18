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

# ─── FIX: Bypass SSL Certificate Verification Globally ───────
import ssl
try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError:
    pass
else:
    ssl._create_default_https_context = _create_unverified_https_context

import re
import time
from datetime import datetime
from utils.logger import log

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

# ─── Smart Router (AI-powered intent classification) ─────────
from brain.context_manager import ConversationContext
from brain.smart_router import SmartRouter
from brain.skill_executor import SkillExecutor
from brain.clarifier import Clarifier

# ─── ML Intelligence Modules ────────────────────────────────
try:
    from ml.voice_emotion import VoiceEmotionDetector
    from ml.face_emotion import FaceEmotionDetector
    from ml.gesture_recognition import GestureRecognizer
    from ml.speaker_id import SpeakerVerifier
    _ML_LOADED = True
except ImportError as _ml_err:
    log.info(f"ML modules not fully loaded: {_ml_err}")
    _ML_LOADED = False

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
from skills.whatsapp_handler import WhatsAppHandler
from skills.calendar_handler import CalendarHandler
from utils.helpers import clean_text, wait_animation

# ─── Core modules ────────────────────────────────────────────
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
        self.whatsapp_handler = WhatsAppHandler(self.whatsapp, self)
        self.wolfram = WolframSkill()
        self.shopping = ShoppingSkill()
        self.media = MediaController()
        self.screen = ScreenController()
        self.clipboard = ClipboardSkill()

        # 🎨 Image Generator — Stable Diffusion (HF) or DALL-E (OpenAI)
        try:
            from skills.image_generator import ImageGeneratorSkill
            self.image_gen = ImageGeneratorSkill()
            log.info("  🎨 ImageGenerator ready — say 'generate a car' to create AI art!")
        except Exception as _ig_err:
            log.warning(f"ImageGenerator unavailable: {_ig_err}")
            self.image_gen = None


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
        self.calendar_handler = CalendarHandler(self.calendar, self)

        # Wire Personal Assistant Layer into Gemini
        self.gemini.set_calendar(self.calendar)
        self.gemini.set_reminder(self.reminder)

        # Advanced App / Window / Smart-Mode Control
        self.app_ctrl = AppControl()
        self.app_ctrl.start_usage_tracking()

        # 📞 Call Monitor — announces incoming calls & listens for answer/decline
        try:
            from skills.call_monitor import CallMonitor

            self.call_monitor = CallMonitor(
                speak_fn=self._speak,
                listen_fn=lambda timeout=6: self.listener.listen(timeout=timeout),
                recent_notifs_fn=lambda: (self.notif_watcher._recent if getattr(self, "notif_watcher", None) else []),
                is_speaking_fn=lambda: self.speaker.is_speaking,
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

        # ── WhatsApp Draft Monitor ──
        try:
            self.whatsapp_handler.setup_notification_listener()
            log.info("📱 WhatsApp monitor active — watching for incoming messages")
        except Exception as e:
            log.warning(f"WhatsApp monitor unavailable: {e}")

        # ── Smart Router (AI-powered intent classification) ──
        self.context = ConversationContext(max_history=8)
        self.smart_router = SmartRouter(self.gemini)
        self.skill_executor = SkillExecutor(self)
        self.clarifier = Clarifier()
        log.info("  SmartRouter + ContextManager + SkillExecutor initialized")

        # ── Proactive Personal Assistant ──
        try:
            from skills.proactive_assistant import ProactiveAssistant
            self.proactive = ProactiveAssistant(self.gemini, self._speak)
            self.proactive.start()
        except Exception as e:
            log.warning(f"Proactive Assistant unavailable: {e}")
            self.proactive = None

        # ── ML Intelligence Modules ─────────────────────────────
        self.voice_emotion = None
        self.face_emotion = None
        self.gesture_recognizer = None
        self.speaker_verifier = None
        self.predictor = None
        self.scene_ai = None
        self.anomaly_detector = None

        if _ML_LOADED:
            try:
                self.voice_emotion = VoiceEmotionDetector()
                log.info("  Voice emotion detector ready")
            except Exception as e:
                log.debug(f"Voice emotion init error: {e}")

            try:
                self.face_emotion = FaceEmotionDetector()
                log.info("  Face emotion detector ready")
            except Exception as e:
                log.debug(f"Face emotion init error: {e}")

            try:
                self.gesture_recognizer = GestureRecognizer()
                log.info("  Gesture recognition ready")
            except Exception as e:
                log.debug(f"Gesture init error: {e}")

            try:
                self.speaker_verifier = SpeakerVerifier()
                log.info("  Speaker verification ready")
            except Exception as e:
                log.debug(f"Speaker ID init error: {e}")

            try:
                from ml.predictive_actions import PredictiveActions
                self.predictor = PredictiveActions()
                log.info(f"  Predictive actions ready ({self.predictor.get_stats()['commands_logged']} commands logged)")
            except Exception as e:
                log.debug(f"Predictive actions init error: {e}")

            try:
                from ml.scene_understanding import SceneUnderstanding
                self.scene_ai = SceneUnderstanding()
                log.info(f"  Scene understanding ready (YOLO={self.scene_ai._yolo.is_ready}, CLIP={self.scene_ai._scene.is_ready})")
            except Exception as e:
                log.debug(f"Scene understanding init error: {e}")

            try:
                from ml.anomaly_detector import AnomalyDetector
                self.anomaly_detector = AnomalyDetector()
                log.info(f"  Anomaly detector ready ({self.anomaly_detector.get_stats()['metrics_logged']} metrics, model={'trained' if self.anomaly_detector.is_ready else 'needs data'})")
            except Exception as e:
                log.debug(f"Anomaly detector init error: {e}")

        log.info("=" * 50)
        log.info("  JARVIS is ONLINE and ready!")

        # ── Emotion / Personality / Memory ────────────────────
        self.emotion = EmotionEngine()
        self.personality = PersonalityLayer(self.emotion)
        self.memory = MemorySystem()
        self.gemini.set_emotion_engine(self.emotion)
        # Initialize Agent Engine
        try:
            from skills.agent_engine import AgentManager
            self.agent_manager = AgentManager(self)
            self.agent_manager.start()
        except Exception as e:
            log.error(f"Agent engine init failed: {e}")
            self.agent_manager = None
            
        log.info(f"All modules mapped. Booting wake-word engine...")
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

        # ── Wire RAG Engine → GeminiHandler ──────────────────────
        # Auto-injects relevant document context into every AI call.
        self._rag_engine = None
        try:
            from brain.rag_engine import RAGEngine
            self._rag_engine = RAGEngine()
            self.gemini.set_rag_engine(self._rag_engine)
            stats = self._rag_engine.get_stats()
            log.info(f"  📚 RAG engine online — {stats.get('total_chunks', 0)} chunks from {stats.get('total_files', 0)} files")
            
            # Start auto-ingest in background
            import threading
            threading.Thread(target=self._rag_engine.auto_ingest_jarvis_data, daemon=True).start()
        except Exception as _rag_err:
            log.warning(f"RAG engine init error: {_rag_err}")
            self._rag_engine = None

        # ── Telegram Bridge (optional — needs TELEGRAM_BOT_TOKEN) ──
        self._telegram = None
        try:
            from skills.telegram_bridge import TelegramBridge
            self._telegram = TelegramBridge()
            if self._telegram.is_available:
                self._telegram.start(jarvis_instance=self)
                log.info("  📱 Telegram bridge online — control JARVIS from phone!")
            else:
                log.info("  📱 Telegram bridge: no token configured (optional)")
        except Exception as _tg_err:
            log.debug(f"Telegram bridge init: {_tg_err}")

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

        # 5c. Stop Agent Engine
        try:
            if hasattr(self, "agent_manager") and self.agent_manager:
                self.agent_manager.stop()
                log.info("  ✓ Agent Engine stopped")
        except Exception as e:
            log.debug(f"Agent Engine cleanup: {e}")

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

    def _clear_all_jarvis_memories(self):
        """NUCLEAR CLEAR — physically delete ALL memory files on disk + wipe all RAM caches.
        
        Targets:
          1. data/personal_facts.json   (PersonalMemory)
          2. data/jarvis_memory.json    (MemorySystem JSON facts/prefs/topics)
          3. data/user_memory.json      (ConversationMemory long-term facts)
          4. data/conversations_full.db (SQLite conversation log)
          5. In-RAM caches in MemorySystem, ConversationMemory, GeminiHandler, ChatHistory
          6. USER_NAME reset to "Sir" in config + .env
        """
        if not getattr(self, "_memory_delete_authorized", False):
            log.warning("Unauthorized memory wipe attempt blocked")
            return "Memory deletion blocked."

        import os
        log.info("🔥 NUCLEAR MEMORY CLEAR — wiping ALL memory stores...")

        _data_dir = Path(__file__).parent / "data"

        # ── 1. PHYSICALLY DELETE memory JSON files ────────────────
        _mem_files = [
            _data_dir / "personal_facts.json",
            _data_dir / "jarvis_memory.json",
            _data_dir / "user_memory.json",
        ]
        for fpath in _mem_files:
            try:
                if fpath.exists():
                    fpath.unlink()
                    log.info(f"  🗑️  Deleted {fpath.name}")
            except Exception as e:
                log.warning(f"  Could not delete {fpath.name}: {e}")

        # ── 2. Clear MemorySystem (also wipes conversations_full.db) ──
        if hasattr(self, "memory") and self.memory:
            try:
                self.memory.clear_all()
                # Force re-init internal data so recall_all() returns empty
                self.memory._data = {
                    "facts": [], "preferences": {}, "topics": {},
                    "corrections": [], "session_count": 0, "total_exchanges": 0,
                }
                self.memory._short_term.clear()
            except Exception as e:
                log.warning(f"  MemorySystem clear error: {e}")

        # ── 3. Clear PersonalMemory (RAM dict) ────────────────────
        if hasattr(self, "_personal_mem") and self._personal_mem:
            try:
                self._personal_mem._facts.clear()
                self._personal_mem._save()
            except Exception as e:
                log.warning(f"  PersonalMemory clear error: {e}")

        # ── 4. Clear the LIVE ConversationMemory on the local LLM ─
        #    (This is the instance actually used — NOT a new one)
        if hasattr(self, "gemini") and self.gemini:
            try:
                _llm = getattr(self.gemini, "_local_llm", None)
                if _llm:
                    _cm = getattr(_llm, "memory", None)
                    if _cm:
                        _cm._facts.clear()
                        _cm._short_term.clear()
                        _cm._save_facts()
                        log.info("  🗑️  Cleared live ConversationMemory on local LLM")
            except Exception as e:
                log.warning(f"  Live ConversationMemory clear error: {e}")
            # Also clear Gemini's own chat history RAM
            try:
                if hasattr(self.gemini, "_chat_history") and self.gemini._chat_history:
                    self.gemini._chat_history.clear()
                if hasattr(self.gemini, "_history"):
                    self.gemini._history.clear()
            except Exception as e:
                log.warning(f"  Gemini history clear error: {e}")

        # ── 5. Clear ChatHistory helper + UserPrefs ───────────────
        if hasattr(self, "history") and self.history:
            try:
                self.history.clear()
            except Exception as e:
                log.warning(f"  ChatHistory clear error: {e}")
        if hasattr(self, "prefs") and self.prefs:
            try:
                self.prefs.reset()
            except Exception as e:
                log.warning(f"  UserPrefs clear error: {e}")

        # ── 6. Reset user name everywhere ─────────────────────────
        config.USER_NAME = "Sir"
        try:
            env_path = _data_dir.parent / ".env"
            if env_path.exists():
                lines = env_path.read_text(encoding="utf-8").splitlines()
                new_lines = []
                found = False
                for line in lines:
                    if line.startswith("USER_NAME="):
                        new_lines.append("USER_NAME=Sir")
                        found = True
                    else:
                        new_lines.append(line)
                if not found:
                    new_lines.append("USER_NAME=Sir")
                env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        except Exception as _env_err:
            log.warning(f"  .env reset error: {_env_err}")

        log.info("✅ NUCLEAR CLEAR complete — all memory stores wiped.")

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

            # ── 0b. SPEAKER VERIFICATION — Is this the owner? ────────
            # If enrolled, only respond to Srini's voice
            if self.speaker_verifier and self.speaker_verifier.is_ready:
                try:
                    audio_np = getattr(self.listener, '_last_audio_np', None)
                    if audio_np is not None and len(audio_np) > 0:
                        sv_result = self.speaker_verifier.verify(audio_np)
                        if not sv_result.get("is_owner", True):
                            sim = sv_result.get("similarity", 0)
                            log.warning(f"Speaker rejected: similarity={sim:.2f}")
                            self._speak("I'm sorry, I only respond to my owner's voice.")
                            return ""
                        else:
                            log.debug(f"Speaker verified: similarity={sv_result.get('similarity', 0):.2f}")
                except Exception as e:
                    log.debug(f"Speaker verification error (allowing): {e}")

            # ── 0c. VOICE EMOTION — Detect mood from voice tone ──────
            # Analyzes pitch/energy/speed to detect happy/sad/angry/stressed
            if self.voice_emotion:
                try:
                    audio_np = getattr(self.listener, '_last_audio_np', None)
                    if audio_np is not None and len(audio_np) > 0:
                        ve_result = self.voice_emotion.detect(audio_np)
                        voice_mood = ve_result.get("emotion", "neutral")
                        voice_conf = ve_result.get("confidence", 0)
                        if voice_conf > 0.3 and voice_mood != "neutral":
                            log.info(f"Voice emotion: {voice_mood} ({voice_conf:.0%})")
                            # Feed to EmotionEngine for mood-adaptive responses
                            self.emotion.update_mood(voice_mood)
                except Exception as e:
                    log.debug(f"Voice emotion error: {e}")

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
                # Use PersonalMemory directly — clean and conversational
                if self._personal_mem:
                    pm_facts = self._personal_mem.get_all()
                    if pm_facts:
                        self._speak(self._personal_mem._recall_all())
                        return ""
                # Fallback to MemorySystem (still cleaner than before)
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

                # ── 5b. LOG TO PREDICTIVE ACTIONS — learns usage patterns ──
                if self.predictor:
                    try:
                        # Determine intent for logging (from SmartRouter or keyword match)
                        _log_intent = getattr(self, '_last_routed_intent', 'chat')
                        self.predictor.log_command(_log_intent, text)
                    except Exception:
                        pass

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

        UPGRADE: SmartRouter (AI) tries first. If it handles the command,
        we return immediately. Otherwise, fall through to the old keyword chain.
        """
        if not text or not text.strip():
            return ""

        # ── MEMORY CLEAR CONFIRMATION ────────────────────────────────────
        if getattr(self, "_waiting_for_memory_clear", False):
            if text.lower().strip() == "yes confirm delete":
                self._waiting_for_memory_clear = False
                self._memory_delete_authorized = True
                self._clear_all_jarvis_memories()
                self._memory_delete_authorized = False
                ans = "Done, sir. I've forgotten everything about you."
                self._speak(ans)
                return ans
            else:
                self._waiting_for_memory_clear = False
                ans = "Memory deletion cancelled."
                log.info("Memory deletion cancelled by user.")
                self._speak(ans)
                return ans

        # ══════════════════════════════════════════════════════════
        # 🧠 PRIORITY ZERO: Personal Memory (BEFORE SmartRouter!)
        # Must run first so "where do I study", "my name is X" etc.
        # are NEVER misrouted to Gemini/chat.
        # ══════════════════════════════════════════════════════════
        _pm_text_lower = text.lower().strip()
        try:
            if self._personal_mem is None:
                from memory.personal_memory import PersonalMemory
                self._personal_mem = PersonalMemory()

            # 1. Try RECALL first ("what's my name", "where do I study", etc.)
            _pm_recall = self._personal_mem.try_recall(text)
            if _pm_recall:
                if _pm_recall == "MEMORY_CLEAR_REQUESTED":
                    self._waiting_for_memory_clear = True
                    _pm_recall = "Are you sure you want to delete all memory? Please reply with 'yes confirm delete'."
                self._speak(_pm_recall)
                return ""

            # 2. Try LEARN ("my name is X", "I study at NIT Delhi", etc.)
            _pm_learn = self._personal_mem.try_learn(text)
            if _pm_learn:
                # Update config USER_NAME if name was learned
                _new_name = self._personal_mem.get("name")
                if _new_name and _new_name.lower() != "sir":
                    import config as _cfg
                    _cfg.USER_NAME = _new_name
                self._speak(_pm_learn)
                # Only return early if it looks like a single intent command
                if not any(w in _pm_text_lower for w in ["also ", "and ", "then "]) and len(text.split()) < 15:
                    return ""

        except Exception as _pm_early_err:
            log.warning(f"PersonalMemory early check error: {_pm_early_err}")

        # ══════════════════════════════════════════════════════════
        # 🧠 SMART ROUTER — AI-powered intent classification
        # Tries Gemini first. Falls back to keyword chain below.
        # ══════════════════════════════════════════════════════════
        try:
            # 1. Update conversation context
            self.context.add_user_input(text)

            # 2. AI classifies the intent
            intent_result = self.smart_router.route(text, self.context, jarvis=self)
            source = intent_result.get("source", "")
            action = intent_result.get("action", "unknown")
            confidence = intent_result.get("confidence", 0)

            log.info(
                f"SmartRouter result: action={action}, "
                f"confidence={confidence:.0%}, source={source}"
            )

            # Track the last intent for predictive actions logging
            self._last_routed_intent = action

            # 3. Check if entities are missing (triggers clarification)
            if action not in ("unknown", "chat", "stop", "send_typed", "_clarify"):
                clarify = self.clarifier.check_and_clarify(intent_result, self.context)
                if clarify:
                    prompt = clarify["entities"].get("prompt", "Could you clarify?")
                    self._speak(prompt)
                    return ""

            # 4. Execute via SkillExecutor if AI is confident
            if source in ("ai", "instant", "local_ml", "clarification_complete", "keyword_override", "cache") and confidence >= 0.6:
                # Handle special signals
                if action == "stop":
                    self.speaker.speak("Stopping everything, sir.")
                    self._cancel_all_tasks()
                    return ""

                if action == "_clarify":
                    prompt = intent_result["entities"].get("prompt", "Could you clarify?")
                    self._speak(prompt)
                    return ""

                if action == "chat":
                    pass  # Fall through to Gemini chat below
                else:
                    response = self.skill_executor.execute(intent_result)
                    if response:
                        # Update context with result
                        self.context.add_result(intent_result, response)

                        # Special signals
                        if response == "__STOP__":
                            self._cancel_all_tasks()
                            return ""
                        if response == "__SEND__":
                            import pyautogui
                            pyautogui.press('enter')
                            return "Sent!"

                        self._speak(response)
                        return ""

        except Exception as e:
            if 'action' in locals() and (action.startswith("email_") or action in ("send_email", "read_email")):
                err_msg = str(e)
                if not err_msg.startswith("Could not"):
                    err_msg = f"Could not execute email command: {err_msg}"
                self._speak(err_msg)
                return ""
            log.warning(f"SmartRouter error (falling back to keywords): {e}")

        # ══════════════════════════════════════════════════════════
        # 📋 KEYWORD FALLBACK — Original if/elif chain
        # Reached when: AI unavailable, low confidence, chat, or unhandled
        # ══════════════════════════════════════════════════════════

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
        text = text.replace("\u2019", "'")
        # ══════════════════════════════════════════════════════════
        # NEW HANDLERS (Task 6 Extraction)
        # ══════════════════════════════════════════════════════════
        _active_win = ""
        try:
            import pygetwindow as _gw
            _aw = _gw.getActiveWindow()
            _active_win = (_aw.title or "").lower() if _aw else ""
        except Exception:
            pass

        # Call WhatsApp Handler
        wa_response = self.whatsapp_handler.handle(text, text_lower, getattr(self, "_last_routed_intent", ""), _active_win)
        if wa_response is not None:
            if wa_response:
                self._speak(wa_response)
            return ""

        # Call Calendar Handler
        cal_response = self.calendar_handler.handle(text, text_lower)
        if cal_response is not None:
            if cal_response:
                self._speak(cal_response)
            return ""


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
            "on my screen",
            "on the screen",
            "on screen",
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
                # ── ENHANCE with Scene Understanding if available ──
                if self.scene_ai and self.scene_ai.is_ready:
                    try:
                        import os
                        _scene_img = os.path.join("data", "vision_capture.jpg")
                        if os.path.exists(_scene_img):
                            _scene_result = self.scene_ai.analyze(_scene_img)
                            if _scene_result.get("description"):
                                _vis_resp += " " + _scene_result["description"]
                    except Exception as e:
                        log.debug(f"Scene enhancement error: {e}")
                self._speak(_vis_resp)
            else:
                self._speak(
                    "Camera isn't responding, sir. "
                    "Check it's connected and not in use by another app like Teams or Zoom."
                )
            return ""

        # ── Face Emotion Detection — "check my mood" / "how do I look" ──
        _face_emo_triggers = [
            "check my mood", "how do i look", "what's my expression",
            "read my face", "face emotion", "my mood", "my expression",
            "am i happy", "am i sad", "am i angry",
        ]
        if any(t in text_lower for t in _face_emo_triggers):
            if self.face_emotion and self.face_emotion.is_ready:
                self._speak("Let me look at your face, sir.")
                try:
                    fe_result = self.face_emotion.detect_from_camera()
                    if fe_result.get("face_detected"):
                        emo = fe_result["emotion"]
                        conf = fe_result["confidence"]
                        self._speak(f"You look {emo}, sir. I'm about {conf:.0%} confident.")
                        # Feed to emotion engine
                        self.emotion.update_mood(emo)
                    else:
                        self._speak("I couldn't detect your face clearly. Try facing the camera, sir.")
                except Exception as e:
                    log.debug(f"Face emotion error: {e}")
                    self._speak("Face detection encountered an error, sir.")
            else:
                self._speak("Face emotion detection isn't available right now, sir.")
            return ""

        # ── Gesture Control — "gesture mode" / "hand control" ──
        _gesture_triggers = [
            "gesture mode", "hand control", "gesture control",
            "start gesture", "use gestures", "hand gestures",
        ]
        if any(t in text_lower for t in _gesture_triggers):
            if self.gesture_recognizer and self.gesture_recognizer.is_ready:
                self._speak("Starting gesture control mode. Show me a hand gesture, sir.")
                try:
                    result = self.gesture_recognizer.detect_from_camera()
                    gesture = result.get("gesture", "none")
                    action = result.get("action")
                    if gesture != "none" and action:
                        self._speak(f"I see a {gesture.replace('_', ' ')} gesture. That means {action}.")
                        # Execute the gesture action
                        if action == "confirm":
                            self._speak("Confirmed, sir!")
                        elif action == "stop":
                            self._cancel_all_tasks()
                            self._speak("Stopping everything.")
                        elif action == "screenshot":
                            self.process_command("take a screenshot")
                        elif action == "volume_up":
                            self.process_command("volume up")
                        elif action == "volume_down":
                            self.process_command("volume down")
                        elif action == "mute":
                            self.process_command("mute")
                    else:
                        self._speak("I didn't detect a clear gesture. Try thumbs up, peace sign, or open palm.")
                except Exception as e:
                    log.debug(f"Gesture error: {e}")
                    self._speak("Gesture detection had an error, sir.")
            else:
                self._speak("Gesture recognition isn't available right now, sir.")
            return ""

        # ── Scene Understanding — "scan the scene" / "describe the room" ──
        _scene_triggers = [
            "scan the scene", "describe the room", "what's around me",
            "scene analysis", "analyze the scene", "describe my surroundings",
            "what do you see around", "scan my room",
        ]
        if any(t in text_lower for t in _scene_triggers):
            if self.scene_ai and self.scene_ai.is_ready:
                self._speak("Analyzing the scene now, sir.")
                try:
                    description = self.scene_ai.describe_camera()
                    self._speak(description)
                except Exception as e:
                    log.debug(f"Scene analysis error: {e}")
                    self._speak("Scene analysis encountered an error, sir.")
            else:
                self._speak("Scene understanding isn't available. Install ultralytics or open-clip-torch, sir.")
            return ""

        stdlib_re = re  # Alias to avoid Python scoping issue with local imports

        # ── Greeting Detection ────────────────────────────────
        
        # ── Agent Task Execution Engine Commands ──────────────
        _agent_cmds = {
            "show active tasks": lambda: f"You have {len(self.agent_manager.list_active_tasks())} active background tasks.",
            "task status": lambda: f"Active tasks: {[t['goal'] for t in self.agent_manager.list_active_tasks()]}",
            "resume task": lambda: "Resumed background tasks." if [self.agent_manager.resume_task(t['id']) for t in self.agent_manager.list_active_tasks() if t['status'] == 'waiting_user'] else "No tasks waiting.",
            "cancel task": lambda: "Cancelled all tasks." if [self.agent_manager.cancel_task(t['id']) for t in self.agent_manager.list_active_tasks()] else "No tasks to cancel.",
            "retry task": lambda: "Retrying tasks." if [self.agent_manager.retry_task(t['id']) for t in self.agent_manager.list_active_tasks() if t['status'] == 'failed'] else "No failed tasks to retry."
        }
        for cmd, func in _agent_cmds.items():
            if text_lower == cmd:
                res = func()
                self._speak(res)
                return ""
        
        if text_lower.startswith("start task "):
            goal = text_lower.replace("start task ", "", 1).strip()
            tid = self.agent_manager.add_task(goal)
            self._speak(f"Started background task {tid} for: {goal}")
            return ""

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

        # ── Personal Memory — NO LLM, instant file-based ──────
        # "my name is X", "remember I am X", "what's my name" etc.
        try:
            if self._personal_mem is None:
                from memory.personal_memory import PersonalMemory

                self._personal_mem = PersonalMemory()


            # Then try RECALL (questions: "what's my name?", "delete my info")
            recall = self._personal_mem.try_recall(text)
            if recall:
                if recall == "MEMORY_CLEAR_REQUESTED":
                    self._waiting_for_memory_clear = True
                    recall = "Are you sure you want to delete all memory? Please reply with 'yes confirm delete'."
                self._speak(recall)
                return ""
        except Exception as _pm_err:
            log.warning(f"PersonalMemory error: {_pm_err}")

        # Must check BEFORE intent parsing so corrections are never misrouted
        if self.corrector.is_correction(text):
            response = self.corrector.learn(text)
            self._speak(response)
            return ""

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


        # "do not disturb" / "stop notifications" / "resume notifications"
        # "mute whatsapp" / "unmute whatsapp" / "notification status"
        # "what notifications did I get"
        if self.notif_watcher:
            # Do Not Disturb
            if any(p in text_lower for p in [
                "do not disturb", "don't disturb",
                "stop notifications", "mute notifications",
                "silence notifications", "quiet mode",
            ]):
                # Extract duration if mentioned
                _dnd_match = re.search(r"(\d+)\s*(?:min|minute|hour)", text_lower)
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
                _mute_match = re.search(
                    r"(?:mute|silence)\s+(.+?)\s*(?:notification|$)",
                    text_lower,
                )
                if _mute_match:
                    _app = _mute_match.group(1).strip()
                    self._speak(self.notif_watcher.mute_app(_app))
                    return ""

            # Unmute specific app (only if "notification" is mentioned)
            if "notification" in text_lower and "unmute " in text_lower:
                _unmute_match = re.search(
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
        # ── Reminder: Edit ──────────────────────────────────────────
        edit_match = None
        for pattern in [
            r"edit reminder (\S+)",
            r"change reminder (\S+) to (.+)"
        ]:
            m = re.search(pattern, text_lower)
            if m:
                edit_match = m
                break
        
        if edit_match:
            rid = edit_match.group(1).upper()
            new_time = None
            new_freq = None
            if len(edit_match.groups()) > 1:
                val = edit_match.group(2).strip()
                # quick parsing "every monday 9 am" or "10 pm"
                if "every" in val:
                    new_freq = val.replace("every", "").strip()
                    if " at " in new_freq:
                        parts = new_freq.split(" at ")
                        new_freq = parts[0].strip()
                        new_time = parts[1].strip()
                else:
                    new_time = val
            
            self._speak(self.reminder.edit_reminder(rid, new_time, new_freq))
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
        if any(
            p in text_lower
            for p in [
                "what do you remember",
                "what do you know about me",
                "what have you remembered",
                "recall",
            ]
        ):
            # PersonalMemory is PRIMARY — always check it first
            if self._personal_mem:
                pm_all = self._personal_mem.get_all()
                if pm_all:
                    self._speak(self._personal_mem._recall_all())
                    return ""
            # Fallback: LLM context memory
            if mem:
                facts = mem.get_facts_prompt()
                if facts:
                    response = facts.replace(
                        "Things I know about the user:\n- ", ""
                    ).replace("\n- ", ", ")
                    self._speak(f"I remember: {response}")
                    return ""
            self._speak(
                "I don't have any personal facts stored yet, sir. "
                "Tell me things like 'my name is X' or 'I study at NIT Delhi'."
            )
            return ""

        # NOTE: "delete my info" / "forget everything" / "clear memory"
        # is handled by PersonalMemory.try_recall(__clear__) at priority zero.

        if mem and (text_lower.startswith("remember that ") or text_lower.startswith(
            "remember "
        )):
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

        # ── Problem Solver (LeetCode / DSA / Debug) ────────────
        if self.problem_solver:
            # Try to extract language first
            language = None
            lang_match = re.search(
                r"\b(?:in|on|using|with|to)\s+(c\s*\+\+|cpp|c\s+plus\s+plus|cplusplus|python|java|javascript|js|go|golang|rust|c\s*#|csharp|c\s+sharp|typescript|ts|c)(?![a-zA-Z0-9_+#])",
                text_lower
            )
            if not lang_match:
                lang_match = re.search(
                    r"\b(c\s*\+\+|cpp|c\s+plus\s+plus|cplusplus|python|java|javascript|js|go|golang|rust|c\s*#|csharp|c\s+sharp|typescript|ts|c)(?![a-zA-Z0-9_+#])$",
                    text_lower
                )
            if lang_match:
                raw_lang = lang_match.group(1).strip()
                if raw_lang in ["c++", "cpp", "c plus plus", "cplusplus"]:
                    language = "C++"
                elif raw_lang in ["c#", "csharp", "c sharp"]:
                    language = "C#"
                elif raw_lang in ["python", "py"]:
                    language = "Python"
                elif raw_lang in ["java"]:
                    language = "Java"
                elif raw_lang in ["javascript", "js"]:
                    language = "JavaScript"
                elif raw_lang in ["typescript", "ts"]:
                    language = "TypeScript"
                elif raw_lang in ["go", "golang"]:
                    language = "Go"
                elif raw_lang in ["rust"]:
                    language = "Rust"
                elif raw_lang in ["c"]:
                    language = "C"
                else:
                    language = raw_lang.title()

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
                lang_msg = f" in {language}" if language else ""
                self._speak(f"Reading the problem from your screen{lang_msg}...")
                try:
                    response = self.problem_solver.solve_from_screen(language=language)
                except Exception as e:
                    log.exception(f"Skill error: {e}")
                    response = "I encountered an error trying to do that."
                self._speak(response)
                return ""

            # "solve two sum" / "solve reverse linked list" / "solve [problem name]"
            _solve_name_match = re.match(
                r"(?:solve|solve the|solve a)\s+(.+?)(?:\s+problem|\s+question)?$",
                text_lower,
            )
            if _solve_name_match:
                problem_name = _solve_name_match.group(1).strip()
                # Clean up language from problem name if matched
                if lang_match:
                    problem_name = problem_name.replace(lang_match.group(0), "").strip()
                if problem_name.lower().endswith(" problem"):
                    problem_name = problem_name[:-8].strip()
                elif problem_name.lower().endswith(" question"):
                    problem_name = problem_name[:-9].strip()

                # Skip if it matched a screen trigger
                if problem_name not in ["this", "the problem", "leetcode", "the question", "this code", "screen", "on screen", "on my screen"]:
                    lang_msg = f" in {language}" if language else ""
                    self._speak(f"Solving {problem_name}{lang_msg}...")
                    try:
                        response = self.problem_solver.solve_by_name(problem_name, language=language)
                    except Exception as e:
                        log.exception(f"Skill error: {e}")
                        response = "I encountered an error trying to do that."
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
                try:
                    response = self.problem_solver.debug_from_screen()
                except Exception as e:
                    log.exception(f"Skill error: {e}")
                    response = "I encountered an error trying to do that."
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
                try:
                    response = self.problem_solver.optimize_from_screen()
                except Exception as e:
                    log.exception(f"Skill error: {e}")
                    response = "I encountered an error trying to do that."
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
                try:
                    response = self.problem_solver.explain_last()
                except Exception as e:
                    log.exception(f"Skill error: {e}")
                    response = "I encountered an error trying to do that."
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
                try:
                    response = self.problem_solver.paste_solution()
                except Exception as e:
                    log.exception(f"Skill error: {e}")
                    response = "I encountered an error trying to do that."
                self._speak(response)
                return ""

            # "what's the complexity" / "time complexity"
            if "complexity" in text_lower and any(
                w in text_lower for w in ["time", "space", "what"]
            ):
                try:
                    response = self.problem_solver.get_complexity()
                except Exception as e:
                    log.exception(f"Skill error: {e}")
                    response = "I encountered an error trying to do that."
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
            "describe my screen",
            "what am i looking at",
            "what's open",
            "what app is this",
        ]
        if any(t in text_lower for t in vision_triggers):
            self._speak("Looking...")
            try:
                response = self.vision.what_is_on_screen()
            except Exception as e:
                log.exception(f"Skill error: {e}")
                response = "I encountered an error trying to do that."
            self._speak(response)
            return ""

        if "read" in text_lower and "screen" in text_lower:
            self._speak("Reading your screen...")
            try:
                response = self.vision.read_text_from_screen()
            except Exception as e:
                log.exception(f"Skill error: {e}")
                response = "I encountered an error trying to do that."
            self._speak(response)
            return ""

        if "summarize" in text_lower and "screen" in text_lower:
            self._speak("One sec...")
            try:
                response = self.vision.summarize_screen()
            except Exception as e:
                log.exception(f"Skill error: {e}")
                response = "I encountered an error trying to do that."
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
            try:
                response = self.vision.find_on_screen(query)
            except Exception as e:
                log.exception(f"Skill error: {e}")
                response = "I encountered an error trying to do that."
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
            try:
                response = self.vision.check_error_on_screen()
            except Exception as e:
                log.exception(f"Skill error: {e}")
                response = "I encountered an error trying to do that."
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
            try:
                response = self.vision.look_at_camera()
            except Exception as e:
                log.exception(f"Skill error: {e}")
                response = "I encountered an error trying to do that."
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
            try:
                response = self.vision.identify_person()
            except Exception as e:
                log.exception(f"Skill error: {e}")
                response = "I encountered an error trying to do that."
            self._speak(response)
            return ""

        # "Read what's in front of me" / "read the board" via camera
        if "read" in text_lower and any(
            t in text_lower
            for t in ["camera", "in front", "board", "paper", "book", "whiteboard"]
        ):
            self._speak("Reading...")
            try:
                response = self.vision.read_text_from_camera()
            except Exception as e:
                log.exception(f"Skill error: {e}")
                response = "I encountered an error trying to do that."
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
        # 🎨 IMAGE GENERATION — "generate a car" / "draw a sunset"
        # ══════════════════════════════════════════════════════
        _IMG_TRIGGERS = [
            "generate a ", "generate an ", "generate image of ", "generate picture of ",
            "draw a ", "draw an ", "draw me a ", "draw me an ",
            "create an image of ", "create a image of ", "create a picture of ",
            "make a picture of ", "make an image of ", "make a drawing of ",
            "paint a ", "paint an ", "show me a picture of ", "show me an image of ",
            "create art of ", "generate art of ", "ai image of ", "ai art of ",
        ]
        _img_hit = next((t for t in _IMG_TRIGGERS if text_lower.startswith(t)), None)
        if _img_hit:
            _img_prompt = text_lower[len(_img_hit):].strip().rstrip(".,!?")
            if _img_prompt and len(_img_prompt) > 2:
                if self.image_gen:
                    self._speak(f"Generating '{_img_prompt}' now, sir. Give me a moment.")
                    _img_result = self.image_gen.generate_image(_img_prompt)
                    self._speak(_img_result)
                else:
                    self._speak("Image generator failed to load at startup, sir.")
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
        if any(t in text_lower for t in ["open settings", "show settings", "launch settings", "windows settings"]):
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
            try:
                response = self.app_ctrl.close_app(app)
            except Exception as e:
                log.exception(f"Skill error: {e}")
                response = "I encountered an error trying to do that."

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

            try:
                response = self.weather.get_current(_weather_city)
            except Exception as e:
                log.exception(f"Skill error: {e}")
                response = "I encountered an error trying to do that."

        elif intent == "news":
            self._speak("Fetching the latest headlines!")
            category = self.news.detect_category(text)
            try:
                response = self.news.get_headlines(category)
            except Exception as e:
                log.exception(f"Skill error: {e}")
                response = "I encountered an error trying to do that."

        elif intent == "youtube":
            query = extract_search_query(text)
            if not query:
                # Vague command → ask what they want to watch
                self._speak("What would you like to watch on YouTube, sir?")
                followup = self.listener.listen(timeout=8)
                if followup and followup.strip():
                    query = extract_search_query(followup) or followup.lower().strip()
                    self._speak(f"Playing {query} on YouTube!")
                    response = self.browser.youtube_play(query)
                else:
                    self._speak("Opening YouTube for you, sir!")
                    response = self.browser.youtube_play("")
            else:
                self._speak(f"Playing {query} on YouTube!")
                response = self.browser.youtube_play(query)

        elif intent == "media":
            # ── First, check if we have a specific song/artist in the command ──
            media_result = self.media.execute(text)

            if media_result == "__ASK_MUSIC__":
                # Vague command ("play some music") → ASK first, then act
                self._speak("What would you like to listen to, sir?")
                # Wait for follow-up voice input
                followup = self.listener.listen(timeout=8)
                if followup and followup.strip():
                    # Strip common filler words from the follow-up
                    query = followup.lower()
                    for filler in ["play", "search", "something like", "please"]:
                        query = query.replace(filler, "").strip()
                    if query:
                        self._speak(f"Playing {followup} on Spotify!")
                        response = self.media.spotify_search_and_play(query)
                    else:
                        self._speak("Okay, resuming playback!")
                        response = self.media.play_pause()
                else:
                    # No follow-up heard → just resume/play
                    self._speak("Starting Spotify for you, sir!")
                    response = self.media.play_pause()
            else:
                self._speak("Got it!")
                response = media_result

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
            try:
                response = self.shopping.execute(text)
            except Exception as e:
                log.exception(f"Skill error: {e}")
                response = "I encountered an error trying to do that."

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
                self._speak(f"Looking that up...")
                response = self.web_search.search(text)

        # ── Files ─────────────────────────────────────────────
        elif intent == "file_create":
            self._speak("Creating your note!")
            try:
                response = self.files.write_note(text)
            except Exception as e:
                log.exception(f"Skill error: {e}")
                response = "I encountered an error trying to do that."

        elif intent == "file_open":
            m = stdlib_re.search(r"open (?:file )?(.+)", text, stdlib_re.IGNORECASE)
            filename = m.group(1).strip() if m else text
            self._speak(f"Opening {filename}!")
            try:
                response = self.files.open_file(filename)
            except Exception as e:
                log.exception(f"Skill error: {e}")
                response = "I encountered an error trying to do that."

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
                    try:
                        response = self.reminder.set_timer(secs)
                    except Exception as e:
                        log.exception(f"Skill error: {e}")
                        response = "I encountered an error trying to do that."
                else:
                    response = "How many seconds or minutes for the timer?"
            else:
                mins, at_time, msg = self.reminder.parse_time_from_text(text)
                if mins or at_time:
                    self._speak("Got it! Setting your reminder.")
                    try:
                        response = self.reminder.set_reminder(
                            msg, minutes=mins, at_time=at_time
                        )
                    except Exception as e:
                        log.exception(f"Skill error: {e}")
                        response = "I encountered an error trying to do that."
                else:
                    response = "Please say when to remind you, like 'in 30 minutes' or 'at 6 PM'."

        # ── Vision ────────────────────────────────────────────
        elif intent == "vision_screen":
            self._speak("Let me take a look at your screen!")
            try:
                response = self.vision.analyze_screen()
            except Exception as e:
                log.exception(f"Skill error: {e}")
                response = "I encountered an error trying to do that."

        elif intent in ("vision_image",):
            self._speak("Analyzing the image now!")
            try:
                response = self.vision.analyze_screen(
                    "What do you see in this image? Describe it in detail."
                )
            except Exception as e:
                log.exception(f"Skill error: {e}")
                response = "I encountered an error trying to do that."

        # ── Phase 4: Email ────────────────────────────────────
        elif intent == "send_email":
            action_str, to_name, subject, body, extra = self.email.parse_email_command(text)
            if to_name and body:
                self._speak(f"Sending email to {to_name}. Just a moment!")
                try:
                    response = self.email.send_email(to_name, subject, body)
                except Exception as e:
                    log.exception(f"Skill error: {e}")
                    response = "I encountered an error trying to do that."
            else:
                response = "Who should I email and what should I say? For example: email mom saying I'll be late."

        elif intent == "read_email":
            self._speak("Let me check your emails!")
            if "unread" in text.lower():
                try:
                    response = self.email.check_unread()
                except Exception as e:
                    log.exception(f"Skill error: {e}")
                    response = "I encountered an error trying to do that."
            else:
                try:
                    response = self.email.read_recent_emails(5)
                except Exception as e:
                    log.exception(f"Skill error: {e}")
                    response = "I encountered an error trying to do that."

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


        # ── Start anomaly detector background thread ───────────
        # Monitors system health every 60s, alerts on CPU/RAM anomalies
        if self.anomaly_detector:
            try:
                import threading
                def _anomaly_monitor():
                    import time as _t2
                    while self._running:
                        try:
                            alert = self.anomaly_detector.get_alert()
                            if alert:
                                log.warning(f"Anomaly alert: {alert}")
                                self._speak(alert)
                        except Exception as e:
                            log.debug(f"Anomaly check error: {e}")
                        _t2.sleep(60)  # Check every 60 seconds

                _anomaly_thread = threading.Thread(
                    target=_anomaly_monitor, daemon=True, name="anomaly-monitor"
                )
                _anomaly_thread.start()
                log.info("  Anomaly monitor started (checking every 60s)")
            except Exception as e:
                log.debug(f"Anomaly thread start error: {e}")

        # ── Predictive actions — suggest what you usually do now ──
        if self.predictor and self.predictor.is_ready:
            try:
                predictions = self.predictor.predict_next(top_k=1)
                if predictions:
                    p = predictions[0]
                    if p["confidence"] >= 0.4:
                        action_name = p["action"].replace("_", " ")
                        reason = p.get("reason", "")
                        self._speak(f"By the way sir, you usually {action_name} around this time. {reason}")
            except Exception as e:
                log.debug(f"Prediction error: {e}")

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

