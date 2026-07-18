"""
JARVIS — utils/logger.py
Colored console logging for JARVIS.
Default: only WARN + ERROR shown (clean startup).
Pass --verbose to see all INFO messages.
"""

import logging
import sys
from colorama import init, Fore, Style
from datetime import datetime

init(autoreset=True)

# Check if --verbose flag passed at startup
_VERBOSE = "--verbose" in sys.argv


class JarvisFormatter(logging.Formatter):
    """Custom colored log formatter for JARVIS."""

    COLORS = {
        logging.DEBUG:    Fore.CYAN,
        logging.INFO:     Fore.GREEN,
        logging.WARNING:  Fore.YELLOW,
        logging.ERROR:    Fore.RED,
        logging.CRITICAL: Fore.MAGENTA,
    }

    PREFIXES = {
        logging.DEBUG:    "🔍 DEBUG",
        logging.INFO:     "✅ JARVIS",
        logging.WARNING:  "⚠️  WARN ",
        logging.ERROR:    "❌ ERROR",
        logging.CRITICAL: "💀 FATAL",
    }

    def format(self, record):
        color  = self.COLORS.get(record.levelno, Fore.WHITE)
        prefix = self.PREFIXES.get(record.levelno, "📢")
        time   = datetime.now().strftime("%H:%M:%S")

        # Detect console encoding
        encoding = getattr(sys.stdout, 'encoding', 'utf-8') or 'utf-8'
        is_utf8 = encoding.lower() in ('utf-8', 'utf_8', 'utf8')

        # Fallback to plain text prefixes if console doesn't support unicode/emojis
        if not is_utf8:
            plain_prefixes = {
                logging.DEBUG:    "[DEBUG]",
                logging.INFO:     "[JARVIS]",
                logging.WARNING:  "[WARN]",
                logging.ERROR:    "[ERROR]",
                logging.CRITICAL: "[FATAL]",
            }
            prefix = plain_prefixes.get(record.levelno, "[INFO]")

        msg = record.getMessage()

        # Build full message
        full_msg = (
            f"{Style.DIM}[{time}]{Style.RESET_ALL} "
            f"{color}{prefix}{Style.RESET_ALL} "
            f"{msg}"
        )

        # Test encode and handle failures gracefully
        try:
            full_msg.encode(encoding)
        except UnicodeEncodeError:
            # If standard message fails to encode, sanitize the message content
            safe_msg = msg.encode(encoding, errors='replace').decode(encoding)
            try:
                # Re-verify and fallback if prefix itself is also problematic
                full_msg = (
                    f"{Style.DIM}[{time}]{Style.RESET_ALL} "
                    f"{color}{prefix}{Style.RESET_ALL} "
                    f"{safe_msg}"
                )
                full_msg.encode(encoding)
            except UnicodeEncodeError:
                # If still failing, fallback completely to ASCII format
                ascii_prefix = {
                    logging.DEBUG:    "DEBUG",
                    logging.INFO:     "JARVIS",
                    logging.WARNING:  "WARN",
                    logging.ERROR:    "ERROR",
                    logging.CRITICAL: "FATAL",
                }.get(record.levelno, "INFO")
                full_msg = (
                    f"[{time}] {ascii_prefix}: {safe_msg}"
                )

        return full_msg


def get_logger(name: str = "JARVIS") -> logging.Logger:
    """Return a configured JARVIS logger."""
    logger = logging.getLogger(name)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JarvisFormatter())
        logger.addHandler(handler)
        # Show ALL logs with --verbose, else only WARN/ERROR
        logger.setLevel(logging.DEBUG if _VERBOSE else logging.WARNING)
        logger.propagate = False

    return logger


# Shortcut — import this in all modules
log = get_logger("JARVIS")
