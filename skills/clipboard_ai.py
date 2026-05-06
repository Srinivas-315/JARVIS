"""
JARVIS — skills/clipboard_ai.py
Clipboard operations + AI processing. History, format conversion, QR codes, etc.
"""

import json
import re
from collections import deque
from typing import Optional

import pyperclip

# In-memory clipboard history (last 10 entries)
_HISTORY: deque = deque(maxlen=10)
_last_clipboard: str = ""


def _update_history():
    """Check clipboard and add to history if changed."""
    global _last_clipboard
    try:
        current = pyperclip.paste()
        if current and current != _last_clipboard and len(current.strip()) > 1:
            _HISTORY.appendleft(current)
            _last_clipboard = current
    except Exception:
        pass


class ClipboardSkill:
    """Read, write, and process clipboard content with history and AI tools."""

    # ─── Basic ───────────────────────────────────────────────────
    def get_clipboard(self) -> str:
        _update_history()
        try:
            text = pyperclip.paste()
            return text if text else "Clipboard is empty."
        except Exception:
            return "Can't access clipboard."

    def copy_to_clipboard(self, text: str) -> str:
        try:
            pyperclip.copy(text)
            _HISTORY.appendleft(text)
            return "Copied."
        except Exception:
            return "Failed to copy."

    def read_clipboard(self) -> str:
        text = self.get_clipboard()
        if len(text) > 300:
            return f"Clipboard has {len(text)} characters. First part: {text[:200]}..."
        return f"Clipboard says: {text}"

    def summarize_clipboard(self, llm) -> str:
        text = self.get_clipboard()
        if not text or text == "Clipboard is empty.":
            return "Nothing to summarize."
        if len(text) < 20:
            return f"Just says: {text}"
        return llm.ask(f"Summarize this in 1-2 sentences: {text[:500]}")

    # ─── Clipboard History ───────────────────────────────────────
    def get_history(self, index: Optional[int] = None) -> str:
        """Get clipboard history. index=None returns full list, index=1-10 returns specific entry."""
        _update_history()
        if not _HISTORY:
            return "Clipboard history is empty, sir."
        if index is not None:
            idx = index - 1
            if 0 <= idx < len(_HISTORY):
                entry = list(_HISTORY)[idx]
                short = entry[:100] + "..." if len(entry) > 100 else entry
                return f"Clipboard entry {index}: {short}"
            return f"No entry at position {index}. History has {len(_HISTORY)} items."
        lines = [
            f"{i + 1}. {e[:60]}{'...' if len(e) > 60 else ''}"
            for i, e in enumerate(_HISTORY)
        ]
        return "Clipboard history:\n" + "\n".join(lines)

    def restore_from_history(self, index: int = 1) -> str:
        """Restore a clipboard history entry back to clipboard."""
        _update_history()
        if not _HISTORY:
            return "Clipboard history is empty, sir."
        idx = index - 1
        items = list(_HISTORY)
        if 0 <= idx < len(items):
            pyperclip.copy(items[idx])
            return f"Restored clipboard entry {index}, sir."
        return f"No entry at position {index}, sir."

    def clear_history(self) -> str:
        """Clear clipboard history."""
        _HISTORY.clear()
        return "Clipboard history cleared, sir."

    # ─── Format Conversion ───────────────────────────────────────
    def convert_format(self, from_fmt: str, to_fmt: str) -> str:
        """Convert clipboard content between formats: json/yaml/csv/markdown/text."""
        text = self.get_clipboard()
        if text == "Clipboard is empty.":
            return text

        from_fmt = from_fmt.lower().strip()
        to_fmt = to_fmt.lower().strip()

        try:
            # JSON -> YAML
            if from_fmt == "json" and to_fmt in ("yaml", "yml"):
                try:
                    import yaml

                    data = json.loads(text)
                    result = yaml.dump(
                        data, default_flow_style=False, allow_unicode=True
                    )
                    pyperclip.copy(result)
                    return "Converted JSON to YAML and copied to clipboard, sir."
                except ImportError:
                    return "PyYAML not installed. Run: pip install pyyaml"

            # YAML -> JSON
            if from_fmt in ("yaml", "yml") and to_fmt == "json":
                try:
                    import yaml

                    data = yaml.safe_load(text)
                    result = json.dumps(data, indent=2, ensure_ascii=False)
                    pyperclip.copy(result)
                    return "Converted YAML to JSON and copied to clipboard, sir."
                except ImportError:
                    return "PyYAML not installed. Run: pip install pyyaml"

            # CSV -> Markdown table
            if from_fmt == "csv" and to_fmt in ("markdown", "md", "table"):
                import csv
                import io

                reader = csv.reader(io.StringIO(text))
                rows = list(reader)
                if not rows:
                    return "No CSV data found in clipboard."
                header = rows[0]
                sep = ["---"] * len(header)
                md_rows = [
                    f"| {' | '.join(header)} |",
                    f"| {' | '.join(sep)} |",
                ]
                for row in rows[1:]:
                    md_rows.append(f"| {' | '.join(row)} |")
                result = "\n".join(md_rows)
                pyperclip.copy(result)
                return "Converted CSV to Markdown table and copied to clipboard, sir."

            # JSON -> pretty print
            if from_fmt == "json" and to_fmt in ("pretty", "formatted"):
                data = json.loads(text)
                result = json.dumps(data, indent=2, ensure_ascii=False)
                pyperclip.copy(result)
                return "Pretty-printed JSON and copied to clipboard, sir."

            # Text -> UPPERCASE / lowercase / Title Case
            if to_fmt == "uppercase":
                pyperclip.copy(text.upper())
                return "Converted to UPPERCASE, sir."
            if to_fmt == "lowercase":
                pyperclip.copy(text.lower())
                return "Converted to lowercase, sir."
            if to_fmt in ("title", "titlecase"):
                pyperclip.copy(text.title())
                return "Converted to Title Case, sir."

            return f"Conversion from {from_fmt} to {to_fmt} not supported yet, sir."

        except json.JSONDecodeError:
            return "Clipboard doesn't contain valid JSON, sir."
        except Exception as e:
            return f"Conversion failed: {str(e)[:60]}"

    # ─── QR Code Generator ───────────────────────────────────────
    def generate_qr(self, text: Optional[str] = None) -> str:
        """Generate QR code from clipboard text or provided text. Saves to Desktop."""
        try:
            from pathlib import Path

            import qrcode

            content = text or self.get_clipboard()
            if not content or content == "Clipboard is empty.":
                return "Nothing to generate QR code from, sir."
            qr = qrcode.QRCode(version=1, box_size=10, border=4)
            qr.add_data(content)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            save_path = Path.home() / "Desktop" / "jarvis_qr.png"
            img.save(str(save_path))
            import os

            os.startfile(str(save_path))
            return "QR code generated and saved to Desktop as jarvis_qr.png, sir."
        except ImportError:
            return "QR code library not installed. Run: pip install qrcode[pil]"
        except Exception as e:
            return f"QR generation failed: {str(e)[:60]}"

    # ─── Text Diff ───────────────────────────────────────────────
    def text_diff(self) -> str:
        """Compare the last 2 clipboard history entries."""
        _update_history()
        items = list(_HISTORY)
        if len(items) < 2:
            return "Need at least 2 clipboard entries to compare. Copy two texts first, sir."
        import difflib

        a = items[1].splitlines(keepends=True)
        b = items[0].splitlines(keepends=True)
        diff = list(
            difflib.unified_diff(
                a, b, fromfile="Previous", tofile="Current", lineterm=""
            )
        )
        if not diff:
            return "Both entries are identical, sir."
        diff_text = "\n".join(diff[:30])
        lines_changed = sum(
            1 for line in diff if line.startswith("+") or line.startswith("-")
        )
        pyperclip.copy(diff_text)
        return f"Found {lines_changed} changed lines. Diff copied to clipboard, sir."

    # ─── Extract URLs / Emails / Phones ─────────────────────────
    def extract_urls(self) -> str:
        """Extract all URLs from clipboard text."""
        text = self.get_clipboard()
        if text == "Clipboard is empty.":
            return text
        urls = re.findall(r'https?://[^\s\'"<>]+', text)
        if not urls:
            return "No URLs found in clipboard, sir."
        result = f"Found {len(urls)} URL(s):\n" + "\n".join(f"* {u}" for u in urls[:10])
        pyperclip.copy("\n".join(urls))
        result += "\n(All URLs copied to clipboard)"
        return result

    def extract_emails(self) -> str:
        """Extract all email addresses from clipboard text."""
        text = self.get_clipboard()
        if text == "Clipboard is empty.":
            return text
        emails = list(
            set(re.findall(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", text))
        )
        if not emails:
            return "No email addresses found in clipboard, sir."
        result = f"Found {len(emails)} email(s):\n" + "\n".join(
            f"* {e}" for e in emails
        )
        pyperclip.copy(", ".join(emails))
        result += "\n(Copied to clipboard)"
        return result

    def extract_phones(self) -> str:
        """Extract all phone numbers from clipboard text."""
        text = self.get_clipboard()
        if text == "Clipboard is empty.":
            return text
        phones = list(
            set(
                re.findall(
                    r"(?:\+91[\-\s]?)?[6-9]\d{9}|(?:\+\d{1,3}[\s\-]?)?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{4}",
                    text,
                )
            )
        )
        if not phones:
            return "No phone numbers found in clipboard, sir."
        result = f"Found {len(phones)} phone number(s):\n" + "\n".join(
            f"* {p}" for p in phones
        )
        pyperclip.copy(", ".join(phones))
        return result

    def extract_all(self) -> str:
        """Extract URLs, emails, and phone numbers from clipboard."""
        text = self.get_clipboard()
        if text == "Clipboard is empty.":
            return text
        urls = re.findall(r'https?://[^\s\'"<>]+', text)
        emails = list(
            set(re.findall(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", text))
        )
        phones = list(
            set(
                re.findall(
                    r"(?:\+91[\-\s]?)?[6-9]\d{9}|(?:\+\d{1,3}[\s\-]?)?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{4}",
                    text,
                )
            )
        )
        parts = []
        if urls:
            parts.append(f"URLs ({len(urls)}): " + ", ".join(urls[:3]))
        if emails:
            parts.append(f"Emails ({len(emails)}): " + ", ".join(emails[:3]))
        if phones:
            parts.append(f"Phones ({len(phones)}): " + ", ".join(phones[:3]))
        return (
            "\n".join(parts)
            if parts
            else "No URLs, emails, or phone numbers found, sir."
        )

    # ─── Auto-Translate Clipboard ────────────────────────────────
    def translate_clipboard(self, target_lang: str = "English") -> str:
        """Translate clipboard content using Google Translate (free)."""
        text = self.get_clipboard()
        if text == "Clipboard is empty.":
            return text
        try:
            from deep_translator import GoogleTranslator

            lang_map = {
                "hindi": "hi",
                "telugu": "te",
                "tamil": "ta",
                "english": "en",
                "french": "fr",
                "spanish": "es",
                "german": "de",
                "arabic": "ar",
                "japanese": "ja",
                "chinese": "zh-CN",
                "kannada": "kn",
                "malayalam": "ml",
            }
            lang_code = lang_map.get(target_lang.lower(), target_lang.lower())
            translated = GoogleTranslator(source="auto", target=lang_code).translate(
                text[:500]
            )
            pyperclip.copy(translated)
            return f"Translated to {target_lang} and copied to clipboard, sir: {translated[:100]}"
        except ImportError:
            return "Translation library not installed. Run: pip install deep-translator"
        except Exception as e:
            return f"Translation failed: {str(e)[:60]}"

    # ─── Word & Char Count ───────────────────────────────────────
    def count_clipboard(self) -> str:
        """Count words and characters in clipboard."""
        text = self.get_clipboard()
        if text == "Clipboard is empty.":
            return text
        words = len(text.split())
        chars = len(text)
        lines = text.count("\n") + 1
        return f"Clipboard has {words} words, {chars} characters, {lines} lines, sir."
