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
import os
import threading
import time

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
        except ImportError:
            return

        async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
            await update.message.reply_text(
                "🤖 JARVIS Online\n\n"
                "I'm your personal AI assistant. Send me any command!\n\n"
                "📋 Commands:\n"
                "/cmd <command> — Run a JARVIS command\n"
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

        async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
            """Handle any text message — forward to JARVIS as command."""
            if not self._jarvis:
                await update.message.reply_text("⚠️ JARVIS not connected")
                return

            text = update.message.text
            if not text or not text.strip():
                return

            await self._process_and_reply(update, text)

        async def _error_handler(update, context: ContextTypes.DEFAULT_TYPE):
            log.warning(f"Telegram error: {context.error}")

        # Build the bot
        app = ApplicationBuilder().token(self._token).build()

        # Register handlers
        app.add_handler(CommandHandler("start", cmd_start))
        app.add_handler(CommandHandler("status", cmd_status))
        app.add_handler(CommandHandler("memory", cmd_memory))
        app.add_handler(CommandHandler("stats", cmd_stats))
        app.add_handler(CommandHandler("cmd", cmd_command))
        app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
        )
        app.add_error_handler(_error_handler)

        self._app = app

        # Run polling
        log.info("Telegram bot polling started...")
        app.run_polling(drop_pending_updates=True)

    async def _process_and_reply(self, update, text: str):
        """Process a command through JARVIS and send the reply."""
        try:
            await update.message.reply_text(f"⏳ Processing: {text}...")

            # Run JARVIS command in thread pool to avoid blocking
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                response = await asyncio.get_event_loop().run_in_executor(
                    pool, self._jarvis.process_command, text
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
