"""
JARVIS — skills/telegram_bridge.py
Telegram Bot Bridge — control JARVIS remotely from your phone.

Commands via Telegram:
  /start          — Welcome message
  /status         — JARVIS system status
  /cmd <anything> — Send a voice command to JARVIS
  /memory         — Show what JARVIS remembers
  /stats          — Routing & memory statistics
  Any message     — Processed as a JARVIS command

Setup:
  1. Create bot with @BotFather on Telegram → get token
  2. Add TELEGRAM_BOT_TOKEN to your .env file
  3. JARVIS will auto-start the bot on launch
"""

import asyncio
import logging
import os
import threading
import time

# Silence telegram's internal network-retry traceback logger
# It prints 60-line tracebacks for simple connection timeouts — unhelpful noise
logging.getLogger("telegram.ext").setLevel(logging.CRITICAL)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

from utils.logger import log


# Ensure .env is loaded before reading token
from pathlib import Path as _Path
try:
    from dotenv import load_dotenv
    load_dotenv(_Path(__file__).parent.parent / ".env")
except ImportError:
    pass

def _get_token() -> str:
    """Read token at call time (after dotenv has loaded)."""
    return os.getenv("TELEGRAM_BOT_TOKEN", "")


class TelegramBridge:
    """
    Telegram bot that bridges commands to JARVIS.
    Runs in a background thread, forwards messages to process_command().
    """

    def __init__(self, jarvis_instance=None):
        self._jarvis = jarvis_instance
        self._bot = None
        self._app = None
        self._running = False
        self._thread = None
        self._token = _get_token()

        # Diagnostics stats
        self.stats = {
            "token_loaded": bool(self._token),
            "bot_initialized": False,
            "polling_started": False,
            "last_successful_api_call": None,
            "last_message_time": None,
            "last_user": None,
            "last_command": None,
            "connection_status": "disconnected",
            "error_count": 0,
            "last_update_id": None
        }

    @property
    def is_available(self) -> bool:
        return bool(self._token)

    def start(self, jarvis_instance=None):
        """Start the Telegram bot in a background thread."""
        if jarvis_instance:
            self._jarvis = jarvis_instance

        if not self._token:
            log.info("Telegram bridge: no TELEGRAM_BOT_TOKEN in .env — skipping")
            return False

        try:
            from telegram import Update
            from telegram.ext import (
                ApplicationBuilder,
                CommandHandler,
                MessageHandler,
                filters,
            )
        except ImportError:
            log.warning(
                "Telegram bridge: python-telegram-bot not installed. "
                "Run: pip install python-telegram-bot"
            )
            return False

        self._running = True
        self._thread = threading.Thread(
            target=self._run_bot, daemon=True, name="TelegramBridge"
        )
        self._thread.start()
        
        # Log startup diagnostics
        log.info(
            f"\n[TELEGRAM]\n"
            f"bot initialized: {self.stats['bot_initialized']}\n"
            f"token loaded: {self.stats['token_loaded']}\n"
            f"polling started: {self.stats['polling_started']}\n"
            f"last successful Telegram API call: {self.stats['last_successful_api_call']}\n"
            f"last received message timestamp: {self.stats['last_message_time']}\n"
            f"last received user: {self.stats['last_user']}\n"
            f"last received command: {self.stats['last_command']}\n"
            f"connection status: {self.stats['connection_status']}\n"
            f"listener thread id: {self._thread.ident if self._thread else None}\n"
        )
        log.info("✅ Telegram bridge started in background thread")
        return True

    def stop(self):
        """Stop the Telegram bot."""
        self._running = False
        if self._app:
            try:
                asyncio.run_coroutine_threadsafe(
                    self._app.stop(), self._app.loop
                )
            except Exception:
                pass
        log.info("Telegram bridge stopped")

    def _run_bot(self):
        """Run the bot event loop (called from background thread)."""
        try:
            from telegram import Update
            from telegram.ext import (
                ApplicationBuilder,
                CommandHandler,
                ContextTypes,
                MessageHandler,
                filters,
            )
            self.stats["bot_initialized"] = True
        except ImportError:
            return

        async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
            await update.message.reply_text(
                "🤖 JARVIS Online\n\n"
                "I'm your personal AI assistant. Send me any command!\n\n"
                "📋 Commands:\n"
                "/cmd <command> — Run a JARVIS command\n"
                "/type <code> — Type code directly into current PC window\n"
                "/status — System status\n"
                "/memory — What I remember\n"
                "/stats — Routing statistics\n\n"
                "Or just type anything and I'll handle it!"
            )

        async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
            if not self._jarvis:
                await update.message.reply_text("⚠️ JARVIS not connected")
                return

            status_parts = ["🤖 JARVIS Status\n"]

            # Voice engine
            try:
                voice = self._jarvis.speaker.current_voice_name()
                status_parts.append(f"🗣️ Voice: {voice}")
            except Exception:
                status_parts.append("🗣️ Voice: unknown")

            # Language
            try:
                lang = self._jarvis.lang.current_name
                status_parts.append(f"🌐 Language: {lang}")
            except Exception:
                pass

            # Router stats
            try:
                stats = self._jarvis.smart_router.routing_stats
                total = sum(stats.values())
                status_parts.append(
                    f"📊 Routes: {total} total "
                    f"(ML: {stats.get('local_ml', 0)}, "
                    f"AI: {stats.get('ai', 0)}, "
                    f"Cache: {stats.get('cache', 0)})"
                )
            except Exception:
                pass

            await update.message.reply_text("\n".join(status_parts))

        async def cmd_memory(update: Update, context: ContextTypes.DEFAULT_TYPE):
            if not self._jarvis:
                await update.message.reply_text("⚠️ JARVIS not connected")
                return

            try:
                recall = self._jarvis.memory.recall_all()
                await update.message.reply_text(f"🧠 Memory Recall\n\n{recall}")
            except Exception as e:
                await update.message.reply_text(f"Memory error: {e}")

        async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
            if not self._jarvis:
                await update.message.reply_text("⚠️ JARVIS not connected")
                return

            try:
                spoken = self._jarvis.memory.get_stats_spoken()
                await update.message.reply_text(f"📊 Statistics\n\n{spoken}")
            except Exception as e:
                await update.message.reply_text(f"Stats error: {e}")

        async def cmd_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
            """Handle /cmd <command> — forward to JARVIS."""
            if not self._jarvis:
                await update.message.reply_text("⚠️ JARVIS not connected")
                return

            command_text = " ".join(context.args) if context.args else ""
            if not command_text:
                await update.message.reply_text("Usage: /cmd <your command>")
                return

            await self._process_and_reply(update, command_text)

        async def cmd_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
            """Handle /type <code> — auto-type code into the active window."""
            text = update.message.text
            # Extract code after /type
            if text.lower().startswith("/type"):
                code = text[5:].lstrip()
            else:
                code = text

            if not code:
                await update.message.reply_text("Usage: /type <code to type>\nExample:\n/type print('Hello')")
                return

            await update.message.reply_text("⏳ Typing code in active window...")
            
            def do_type():
                import pyautogui
                import time
                pyautogui.FAILSAFE = False
                
                # Wait for user to switch to target window
                time.sleep(1.5)
                
                # Split code into lines
                lines = code.replace('\r\n', '\n').split('\n')
                
                for i, line in enumerate(lines):
                    if i > 0:
                        pyautogui.press('escape')
                        pyautogui.press('enter')
                        time.sleep(0.05)
                        pyautogui.press('escape')
                        # Clear any auto-indent
                        pyautogui.press('space')
                        pyautogui.press('home')
                        pyautogui.hotkey('shift', 'end')
                        pyautogui.press('backspace')
                    
                    # Type the whole line at once — fast
                    if line:
                        pyautogui.write(line, interval=0.08)
                
                return "✅ Finished typing."

            import concurrent.futures
            import asyncio
            try:
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    resp = await asyncio.get_running_loop().run_in_executor(pool, do_type)
                await update.message.reply_text(resp)
            except Exception as e:
                log.warning(f"Telegram type error: {e}")
                await update.message.reply_text(f"❌ Error: {e}")


        async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
            """Handle any text message — forward to JARVIS as command."""
            text = update.message.text
            user = update.message.from_user.username or update.message.from_user.first_name if update.message.from_user else "unknown"
            
            # Update stats
            t_now = time.strftime("%Y-%m-%d %H:%M:%S")
            self.stats["last_message_time"] = t_now
            self.stats["last_user"] = user
            self.stats["last_command"] = text
            self.stats["last_successful_api_call"] = t_now
            self.stats["connection_status"] = "connected"
            self.stats["last_update_id"] = update.update_id

            log.info(f"\n[TELEGRAM]\nmessage received: {text}\nuser: {user}\ntimestamp: {t_now}\n")

            if text and text.strip().lower() == "ping":
                await update.message.reply_text("pong")
                return

            if not self._jarvis:
                await update.message.reply_text("⚠️ JARVIS not connected")
                return

            if not text or not text.strip():
                return

            await self._process_and_reply(update, text)

        async def _error_handler(update, context: ContextTypes.DEFAULT_TYPE):
            self.stats["error_count"] += 1
            log.warning(f"Telegram error: {context.error}")

        # Build the bot
        app = ApplicationBuilder().token(self._token).build()

        # Register handlers
        app.add_handler(CommandHandler("start", cmd_start))
        app.add_handler(CommandHandler("status", cmd_status))
        app.add_handler(CommandHandler("memory", cmd_memory))
        app.add_handler(CommandHandler("stats", cmd_stats))
        app.add_handler(CommandHandler("cmd", cmd_command))
        app.add_handler(CommandHandler("type", cmd_type))
        app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
        )
        app.add_error_handler(_error_handler)

        self._app = app

        # Comprehensive network diagnostics
        network_stats = {
            "dns_resolved": False,
            "https_reachable": False,
            "api_reachable": False,
            "bot_validation_attempted": False
        }

        import socket
        import urllib.request

        # 1. DNS Resolution
        try:
            socket.setdefaulttimeout(3)
            socket.getaddrinfo("api.telegram.org", 443)
            network_stats["dns_resolved"] = True
        except Exception:
            pass

        # 2. General HTTPS
        try:
            urllib.request.urlopen("https://www.google.com", timeout=3)
            network_stats["https_reachable"] = True
        except Exception:
            pass

        # 3. Telegram API Reachability
        try:
            req = urllib.request.Request("https://api.telegram.org", method="GET")
            urllib.request.urlopen(req, timeout=3)
            network_stats["api_reachable"] = True
        except urllib.error.HTTPError as e:
            # 302, 401, 404 means the server responded -> reachable
            if e.code in [302, 401, 404]:
                network_stats["api_reachable"] = True
        except Exception:
            pass

        log.info(
            f"\n[TELEGRAM NETWORK]\n"
            f"DNS resolved: {network_stats['dns_resolved']}\n"
            f"HTTPS reachable: {network_stats['https_reachable']}\n"
            f"api.telegram.org reachable: {network_stats['api_reachable']}\n"
            f"bot token validation attempted: False\n"
        )

        if not network_stats["api_reachable"]:
            self.stats["connection_status"] = "disconnected (network unreachable)"
            log.info("Telegram API unreachable from current network.")
            return

        self.stats["connection_status"] = "connected"
        network_stats["bot_validation_attempted"] = True

        # Run polling
        log.info("Telegram bot polling started...")
        self.stats["polling_started"] = True
        
        # Start heartbeat thread
        def _heartbeat():
            while self._running:
                time.sleep(60)
                log.info(
                    f"\n[TELEGRAM]\n"
                    f"poller alive: {self._thread.is_alive() if self._thread else False}\n"
                    f"last update id: {self.stats.get('last_update_id')}\n"
                    f"last successful API call: {self.stats.get('last_successful_api_call')}\n"
                )
        
        hb_thread = threading.Thread(target=_heartbeat, daemon=True, name="TelegramHeartbeat")
        hb_thread.start()

        try:
            app.run_polling(drop_pending_updates=True)
        except Exception as _tg_err:
            self.stats["error_count"] += 1
            err_s = str(_tg_err).lower()
            if any(x in err_s for x in ["timedout", "timed out", "connecttimeout", "network"]):
                self.stats["connection_status"] = "disconnected (timeout)"
                log.warning("Telegram bridge: connection timed out — no internet or Telegram blocked")
            else:
                self.stats["connection_status"] = f"error: {_tg_err}"
                log.warning(f"Telegram bridge stopped: {_tg_err}")

    def get_status(self) -> str:
        return (
            f"bridge alive: {self._running}\n"
            f"polling alive: {self._thread.is_alive() if self._thread else False}\n"
            f"telegram connected: {self.stats['connection_status'] == 'connected'}\n"
            f"bot authenticated: {self.stats['bot_initialized']}\n"
            f"last update id: {self.stats.get('last_update_id')}\n"
            f"last message received: {self.stats['last_message_time']}\n"
            f"last command processed: {self.stats['last_command']}\n"
            f"last API success: {self.stats['last_successful_api_call']}\n"
            f"error count: {self.stats['error_count']}"
        )

    async def _process_and_reply(self, update, text: str):
        """Process a command through JARVIS and send the reply."""
        try:
            await update.message.reply_text(f"⏳ Processing: {text}...")
            
            print(f"\n\033[93m📱 Telegram:\033[0m {text}")

            # Run JARVIS command in thread pool to avoid blocking
            import concurrent.futures
            import asyncio
            
            def run_jarvis_cmd():
                import sys
                if sys.platform == "win32":
                    try:
                        import pythoncom
                        pythoncom.CoInitialize()
                    except ImportError:
                        pass
                try:
                    return self._jarvis.process_command(text)
                finally:
                    if sys.platform == "win32":
                        try:
                            import pythoncom
                            pythoncom.CoUninitialize()
                        except ImportError:
                            pass

            with concurrent.futures.ThreadPoolExecutor() as pool:
                response = await asyncio.get_running_loop().run_in_executor(
                    pool, run_jarvis_cmd
                )

            if response:
                # Telegram has a 4096 char limit
                if len(response) > 4000:
                    response = response[:4000] + "..."
                await update.message.reply_text(f"🤖 {response}")
            else:
                await update.message.reply_text("✅ Done (no text response)")

        except Exception as e:
            log.warning(f"Telegram process error: {e}")
            await update.message.reply_text(f"❌ Error: {e}")

    def send_notification(self, chat_id: str, message: str):
        """Send a proactive notification to a Telegram chat."""
        if not self._app or not self._running:
            return False

        try:
            import asyncio

            async def _send():
                await self._app.bot.send_message(
                    chat_id=chat_id, text=message, parse_mode="Markdown"
                )

            asyncio.run(_send())
            return True
        except Exception as e:
            log.debug(f"Telegram notification error: {e}")
            return False


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    print("Telegram Bridge Module")
    token = _get_token()
    print(f"Token configured: {'YES' if token else 'NO'}")

    if token:
        bridge = TelegramBridge()
        print("Starting bot (Ctrl+C to stop)...")
        bridge.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            bridge.stop()
    else:
        print("Set TELEGRAM_BOT_TOKEN in .env to use Telegram bridge")
