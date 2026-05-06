"""
JARVIS — skills/browser.py
Browser automation using Playwright — search, YouTube, websites.
"""

import urllib.parse
import webbrowser

from utils.logger import log

# Try importing Playwright (installed separately)
try:
    from playwright.sync_api import sync_playwright

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    log.warning("Playwright not installed. Using webbrowser fallback.")
    log.warning("Install: pip install playwright && playwright install chromium")


class BrowserSkill:
    """Controls the browser for web searches and automation."""

    def search_in_browser(self, query: str) -> str:
        """
        Search directly in the current browser tab.
        Ctrl+L → type query → Enter. Works in Chrome, Edge, Firefox.
        """
        import time

        import pyautogui

        pyautogui.FAILSAFE = False

        log.info(f"Searching in browser: '{query}'")
        try:
            # Focus address bar
            pyautogui.hotkey("ctrl", "l")
            time.sleep(0.5)

            # Type the search query
            pyautogui.typewrite(query, interval=0.05)
            time.sleep(0.3)

            # Press Enter to search
            pyautogui.press("enter")

            return f"Searching for: {query}"
        except Exception as e:
            log.error(f"Browser search error: {e}")
            return self.google_search(query)  # Fallback to new tab

    def google_search(self, query: str) -> str:
        """Open Google search for a query."""
        url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
        webbrowser.open(url)
        log.info(f"Google search: '{query}'")
        return f"Searching Google for: {query}"

    def youtube_search(self, query: str) -> str:
        """Open YouTube search for a query."""
        url = (
            f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}"
        )
        webbrowser.open(url)
        log.info(f"YouTube search: '{query}'")
        return f"Searching YouTube for: {query}"

    def youtube_play(self, query: str) -> str:
        """Search and auto-play first YouTube result using pywhatkit."""
        try:
            import pywhatkit as pwk

            pwk.playonyt(query)
            return f"Playing '{query}' on YouTube"
        except Exception as e:
            log.error(f"YouTube play error: {e}")
            return self.youtube_search(query)  # Fallback to search

    def open_website(self, url: str) -> str:
        """Open a specific website in the default browser."""
        if not url.startswith("http"):
            url = "https://" + url
        webbrowser.open(url)
        log.info(f"Opened: {url}")
        return f"Opening {url}"

    def wikipedia_search(self, query: str) -> str:
        """Get Wikipedia summary for a topic."""
        try:
            import wikipedia

            wikipedia.set_lang("en")
            summary = wikipedia.summary(query, sentences=3, auto_suggest=True)
            log.info(f"Wikipedia: '{query}'")
            return summary
        except Exception as e:
            log.error(f"Wikipedia error: {e}")
            return self.google_search(f"{query} wikipedia")

    def amazon_search(self, query: str) -> str:
        """Search Amazon India for products."""
        url = f"https://www.amazon.in/s?k={urllib.parse.quote(query)}"
        webbrowser.open(url)
        return f"Searching Amazon for: {query}"

    def flipkart_search(self, query: str) -> str:
        """Search Flipkart for products."""
        url = f"https://www.flipkart.com/search?q={urllib.parse.quote(query)}"
        webbrowser.open(url)
        return f"Searching Flipkart for: {query}"

    # ─── Playwright-powered automation ───────────────────────
    def fill_form(self, url: str, fields: dict) -> str:
        """Fill a web form using Playwright. fields = {selector: value}"""
        if not PLAYWRIGHT_AVAILABLE:
            return "Playwright not installed. Run: pip install playwright && playwright install"

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=False)
                page = browser.new_page()
                page.goto(url, timeout=15000)

                for selector, value in fields.items():
                    page.fill(selector, value)

                browser.close()
            return f"Form filled at {url}"
        except Exception as e:
            log.error(f"Form fill error: {e}")
            return f"Couldn't fill form: {str(e)[:80]}"

    def extract_page_text(self, url: str) -> str:
        """Extract visible text from a web page using Playwright."""
        if not PLAYWRIGHT_AVAILABLE:
            return "Playwright not available."

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(url, timeout=15000)
                text = page.inner_text("body")
                browser.close()
            return text[:2000]  # First 2000 chars
        except Exception as e:
            log.error(f"Extract page error: {e}")
            return ""

    def bookmark_current_page(self) -> str:
        """Bookmark the current browser page with Ctrl+D."""
        import time

        import pyautogui

        try:
            pyautogui.hotkey("ctrl", "d")
            time.sleep(0.8)
            pyautogui.press("enter")  # Confirm save in Chrome/Edge
            return "Page bookmarked, sir."
        except Exception as e:
            return f"Couldn't bookmark: {str(e)[:60]}"

    def clear_browsing_data(self) -> str:
        """Clear browsing data in Chrome/Edge using keyboard shortcut."""
        import time

        import pyautogui

        try:
            pyautogui.hotkey("ctrl", "shift", "delete")
            time.sleep(1.5)
            pyautogui.press("enter")  # Clear with default settings
            return "Browsing data cleared, sir."
        except Exception as e:
            return f"Couldn't clear data: {str(e)[:60]}"

    def close_duplicate_tabs(self) -> str:
        """Close duplicate browser tabs by comparing titles (uses pygetwindow)."""
        try:
            import pygetwindow as gw

            wins = gw.getAllWindows()
            browser_wins = [
                w
                for w in wins
                if any(
                    b in w.title.lower() for b in ["chrome", "edge", "firefox", "brave"]
                )
            ]
            return f"Found {len(browser_wins)} browser window(s). Use Ctrl+W to close individual tabs, sir."
        except Exception as e:
            return f"Tab management: {str(e)[:60]}"

    def extract_emails_from_page(self) -> str:
        """Extract email addresses from the current web page."""
        import re
        import time

        import pyautogui
        import pyperclip

        try:
            pyautogui.hotkey("ctrl", "a")
            time.sleep(0.3)
            pyautogui.hotkey("ctrl", "c")
            time.sleep(0.3)
            text = pyperclip.paste()
            emails = list(
                set(
                    re.findall(
                        r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", text
                    )
                )
            )
            if not emails:
                return "No email addresses found on this page, sir."
            pyperclip.copy(", ".join(emails))
            return f"Found {len(emails)} email(s): {', '.join(emails[:5])}. Copied to clipboard!"
        except Exception as e:
            return f"Extract failed: {str(e)[:60]}"

    def extract_phones_from_page(self) -> str:
        """Extract phone numbers from the current web page."""
        import re
        import time

        import pyautogui
        import pyperclip

        try:
            pyautogui.hotkey("ctrl", "a")
            time.sleep(0.3)
            pyautogui.hotkey("ctrl", "c")
            time.sleep(0.3)
            text = pyperclip.paste()
            phones = list(
                set(
                    re.findall(
                        r"(?:\+91[\-\s]?)?[6-9]\d{9}|(?:\+\d{1,3}[\s\-]?)?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{4}",
                        text,
                    )
                )
            )
            if not phones:
                return "No phone numbers found on this page, sir."
            pyperclip.copy(", ".join(phones))
            return f"Found {len(phones)} phone number(s): {', '.join(phones[:5])}. Copied to clipboard!"
        except Exception as e:
            return f"Extract failed: {str(e)[:60]}"

    def toggle_dark_mode(self) -> str:
        """Toggle dark mode in Chrome/Edge using an extension shortcut or Dev Tools."""
        import time

        import pyautogui

        try:
            pyautogui.hotkey("ctrl", "shift", "j")
            time.sleep(0.5)
            import pyperclip

            dark_css = "document.body.style.filter='invert(1) hue-rotate(180deg)'"
            pyperclip.copy(dark_css)
            pyautogui.hotkey("ctrl", "v")
            pyautogui.press("enter")
            time.sleep(0.3)
            pyautogui.hotkey("ctrl", "shift", "j")  # Close DevTools
            return "Dark mode toggled on current page, sir."
        except Exception as e:
            return f"Dark mode toggle failed: {str(e)[:60]}"

    def open_developer_tools(self) -> str:
        """Open browser developer tools."""
        import pyautogui

        pyautogui.press("f12")
        return "Developer tools opened, sir."

    def zoom_in(self) -> str:
        import pyautogui

        pyautogui.hotkey("ctrl", "+")
        return "Zoomed in, sir."

    def zoom_out(self) -> str:
        import pyautogui

        pyautogui.hotkey("ctrl", "-")
        return "Zoomed out, sir."

    def zoom_reset(self) -> str:
        import pyautogui

        pyautogui.hotkey("ctrl", "0")
        return "Zoom reset to 100%, sir."

    def print_page(self) -> str:
        import pyautogui

        pyautogui.hotkey("ctrl", "p")
        return "Print dialog opened, sir."

    def view_source(self) -> str:
        import pyautogui

        pyautogui.hotkey("ctrl", "u")
        return "Page source opened, sir."

    def go_back(self) -> str:
        import pyautogui

        pyautogui.hotkey("alt", "left")
        return "Going back, sir."

    def go_forward(self) -> str:
        import pyautogui

        pyautogui.hotkey("alt", "right")
        return "Going forward, sir."

    def reload_page(self) -> str:
        import pyautogui

        pyautogui.press("f5")
        return "Page reloaded, sir."

    def hard_reload(self) -> str:
        import pyautogui

        pyautogui.hotkey("ctrl", "shift", "r")
        return "Hard reload done, sir."

    def find_in_page(self, text: str) -> str:
        """Find text on current page."""
        import time

        import pyautogui
        import pyperclip

        pyautogui.hotkey("ctrl", "f")
        time.sleep(0.5)
        pyperclip.copy(text)
        pyautogui.hotkey("ctrl", "v")
        return f"Searching for '{text}' on current page, sir."


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    browser = BrowserSkill()
    print(browser.google_search("JARVIS AI assistant"))
    print(browser.wikipedia_search("Artificial Intelligence"))
