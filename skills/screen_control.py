"""
JARVIS — skills/screen_control.py
Voice-controlled screen: click, scroll, type, mouse move, cursor-to-element.
"""

import re
import time

import pyautogui
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
            elif "on" in t:
                # e.g. "click on send"
                target = t.split("on", 1)[-1].strip()
                return click_element_by_name(target)
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

        # ── Mouse Movement ─────────────────────────────
        if "move mouse" in t or "move cursor" in t:
            if "up" in t: return move_cursor_direction("up")
            if "down" in t: return move_cursor_direction("down")
            if "left" in t: return move_cursor_direction("left")
            if "right" in t: return move_cursor_direction("right")

        if "go to" in t or "move to" in t:
            target = re.split(r"go to|move to", t)[-1].strip()
            return move_cursor_to_element(target)

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


# ─── OCR-based cursor control ─────────────────────────────────────────────────

_ocr_reader = None  # lazy-init singleton


def _get_ocr_reader():
    """Lazy-load easyOCR reader (slow first time only)."""
    global _ocr_reader
    if _ocr_reader is None:
        try:
            import easyocr
            log.info("Initialising easyOCR for cursor control…")
            _ocr_reader = easyocr.Reader(["en"], gpu=False, verbose=False)
        except ImportError:
            raise ImportError("easyocr not installed. Run: pip install easyocr")
    return _ocr_reader


def move_cursor_to_element(target_name: str, region=None, click: bool = False) -> str:
    """
    Find a UI element by its visible text label on screen and move the
    cursor to it.  Uses easyOCR for text detection.

    Args:
        target_name: The text label of the element to find (e.g. "Send", "emoji").
        region:      Optional (x, y, w, h) screen region to restrict search.
        click:       If True, also click the element after moving.

    Returns:
        Human-readable status string.
    """
    try:
        import numpy as np
        import pyautogui as pg
    except ImportError as e:
        return f"Missing dependency: {e}."

    try:
        reader = _get_ocr_reader()

        # Screenshot
        if region:
            shot = pg.screenshot(region=region)
            offset_x, offset_y = region[0], region[1]
        else:
            shot = pg.screenshot()
            offset_x, offset_y = 0, 0

        img = np.array(shot)
        results = reader.readtext(img)  # [ ([bbox], text, conf), … ]

        target_lower = target_name.lower().strip()
        best_match = None
        best_score = 0.0

        for (bbox, text, conf) in results:
            text_lower = text.lower().strip()
            if not text_lower:
                continue
            if target_lower in text_lower or text_lower in target_lower:
                # Score: higher confidence + closer length match = better
                score = conf * (len(target_lower) / max(len(text_lower), 1))
                if score > best_score:
                    best_score = score
                    best_match = (bbox, text)

        if best_match is None:
            return (
                f"Could not find '{target_name}' on screen, sir. "
                "Make sure the element is visible."
            )

        bbox, found_text = best_match
        xs = [p[0] for p in bbox]
        ys = [p[1] for p in bbox]
        cx = int(sum(xs) / len(xs)) + offset_x
        cy = int(sum(ys) / len(ys)) + offset_y

        log.info(f"move_cursor_to_element: '{found_text}' → ({cx}, {cy})")
        pyautogui.moveTo(cx, cy, duration=0.3)
        time.sleep(0.1)

        if click:
            pyautogui.click()
            return f"Clicked '{found_text}' at ({cx}, {cy}), sir."
        return f"Moved cursor to '{found_text}' at ({cx}, {cy}), sir."

    except Exception as e:
        log.warning(f"move_cursor_to_element error: {e}")
        return f"Could not move cursor: {str(e)[:80]}"


def move_cursor_direction(direction: str, pixels: int = 100) -> str:
    """Move the cursor in a cardinal direction by a given number of pixels."""
    x, y = pyautogui.position()
    dirs = {
        "up":    (x, y - pixels),
        "down":  (x, y + pixels),
        "left":  (x - pixels, y),
        "right": (x + pixels, y),
    }
    if direction not in dirs:
        return f"Unknown direction '{direction}', sir. Use up/down/left/right."
    nx, ny = dirs[direction]
    pyautogui.moveTo(nx, ny, duration=0.2)
    return f"Moved cursor {direction} by {pixels} pixels, sir."


def click_element_by_name(target_name: str, region=None) -> str:
    """Find and click a UI element by its visible text label."""
    return move_cursor_to_element(target_name, region=region, click=True)


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    sc = ScreenController()
    print(sc.execute("scroll down"))
    print(sc.execute("select all"))
