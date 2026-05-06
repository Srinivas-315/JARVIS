"""
JARVIS — skills/screen_control.py
Voice-controlled screen: click, scroll, type, mouse move.
"""

import pyautogui
import time
from utils.logger import log

# Safety: prevent pyautogui from locking up
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.3


class ScreenController:
    """Control mouse, keyboard, and screen by voice."""

    def execute(self, text: str) -> str:
        """Parse and execute screen control commands."""
        t = text.lower().strip()

        # ── Click ──────────────────────────────────────
        if "click" in t:
            if "double" in t:
                pyautogui.doubleClick()
                return "Double clicked."
            elif "right" in t:
                pyautogui.rightClick()
                return "Right clicked."
            else:
                pyautogui.click()
                return "Clicked."

        # ── Scroll ─────────────────────────────────────
        if "scroll" in t:
            if "up" in t:
                pyautogui.scroll(5)
                return "Scrolled up."
            elif "down" in t:
                pyautogui.scroll(-5)
                return "Scrolled down."
            elif "top" in t:
                pyautogui.hotkey("ctrl", "Home")
                return "Scrolled to top."
            elif "bottom" in t:
                pyautogui.hotkey("ctrl", "End")
                return "Scrolled to bottom."

        # ── Type text ──────────────────────────────────
        if t.startswith("type "):
            content = text[5:].strip()
            if content:
                time.sleep(0.5)
                pyautogui.typewrite(content, interval=0.03) if content.isascii() else pyautogui.write(content)
                return "Typed."
            return "What should I type?"

        # ── Press keys ─────────────────────────────────
        if "press enter" in t or "hit enter" in t:
            pyautogui.press("enter")
            return "Enter."

        if "press escape" in t or "press esc" in t:
            pyautogui.press("escape")
            return "Escape."

        if "press tab" in t:
            pyautogui.press("tab")
            return "Tab."

        if "press space" in t:
            pyautogui.press("space")
            return "Space."

        if "press backspace" in t or "delete that" in t:
            pyautogui.press("backspace")
            return "Deleted."

        # ── Select all / Copy / Paste / Undo ───────────
        if "select all" in t:
            pyautogui.hotkey("ctrl", "a")
            return "Selected all."

        if "copy" in t and ("that" in t or "this" in t or "it" in t):
            pyautogui.hotkey("ctrl", "c")
            return "Copied."

        if "paste" in t:
            pyautogui.hotkey("ctrl", "v")
            return "Pasted."

        if "undo" in t:
            pyautogui.hotkey("ctrl", "z")
            return "Undone."

        if "redo" in t:
            pyautogui.hotkey("ctrl", "y")
            return "Redone."

        # ── Save ───────────────────────────────────────
        if "save" in t and ("file" in t or "this" in t or "it" in t):
            pyautogui.hotkey("ctrl", "s")
            return "Saved."

        # ── Window snap ────────────────────────────────
        if "snap left" in t or "move left" in t or "window left" in t:
            pyautogui.hotkey("win", "left")
            return "Snapped left."

        if "snap right" in t or "move right" in t or "window right" in t:
            pyautogui.hotkey("win", "right")
            return "Snapped right."

        if "minimize" in t or "minimise" in t:
            if "all" in t:
                pyautogui.hotkey("win", "d")
                return "Done."
            pyautogui.hotkey("win", "down")
            return "Done."

        if "maximize" in t or "maximise" in t or "full screen" in t:
            pyautogui.hotkey("win", "up")
            return "Done."

        # ── Alt+Tab ────────────────────────────────────
        if "switch window" in t or "alt tab" in t or "next window" in t:
            pyautogui.hotkey("alt", "tab")
            return "Switched."

        # ── Task view ──────────────────────────────────
        if "task view" in t or "show all windows" in t:
            pyautogui.hotkey("win", "tab")
            return "Task view."

        return ""


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    sc = ScreenController()
    print(sc.execute("scroll down"))
    print(sc.execute("select all"))
