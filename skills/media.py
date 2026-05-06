"""
JARVIS — skills/media.py
Media control — Spotify, VLC, or any music/video player.

FIX: typewrite() replaced with clipboard paste (handles special chars & Unicode)
FIX: Hardcoded Spotify path fixed to use Path.home()
NEW: Sleep timer — stop music after X minutes
NEW: Volume ramp (smooth fade)
NEW: Lyrics lookup via text search
"""

import os
import re
import subprocess
import threading
import time
import urllib.parse
from pathlib import Path

import pyautogui
import pygetwindow as gw

from utils.logger import log

try:
    import pyperclip

    HAS_CLIP = True
except ImportError:
    HAS_CLIP = False

pyautogui.FAILSAFE = False

# Sleep timer state
_sleep_timer: threading.Timer | None = None


def _paste_type(text: str, interval: float = 0.05):
    """
    FIX: type text using clipboard paste (handles Unicode, special chars, spaces).
    Falls back to typewrite for ASCII-safe chars if pyperclip unavailable.
    """
    if HAS_CLIP:
        try:
            pyperclip.copy(text)
            time.sleep(0.15)
            pyautogui.hotkey("ctrl", "v")
            return
        except Exception:
            pass
    # Fallback — strip non-ASCII for typewrite
    safe = "".join(c for c in text if ord(c) < 128)
    pyautogui.typewrite(safe, interval=interval)


class MediaController:
    """Control media playback in Spotify or any player."""

    # ─── Playback Control ────────────────────────────────────
    def play_pause(self) -> str:
        """Toggle play/pause in any media player."""
        pyautogui.press("playpause")
        log.info("Media: Play/Pause")
        return "Playing!"

    def next_track(self) -> str:
        """Skip to next track."""
        pyautogui.press("nexttrack")
        log.info("Media: Next track")
        return "Skipped to next track!"

    def previous_track(self) -> str:
        """Go to previous track."""
        pyautogui.press("prevtrack")
        log.info("Media: Previous track")
        return "Playing previous track!"

    def stop(self) -> str:
        """Stop playback."""
        pyautogui.press("stop")
        log.info("Media: Stop")
        return "Stopped playback."

    def volume_up(self) -> str:
        """Increase volume."""
        pyautogui.press("volumeup")
        pyautogui.press("volumeup")
        pyautogui.press("volumeup")
        return "Volume up!"

    def volume_down(self) -> str:
        """Decrease volume."""
        pyautogui.press("volumedown")
        pyautogui.press("volumedown")
        pyautogui.press("volumedown")
        return "Volume down!"

    # ─── Spotify-specific ────────────────────────────────────
    def spotify_search_and_play(self, song_name: str) -> str:
        """
        Search for a song in Spotify and play it.
        FIX: Uses clipboard paste — handles Telugu, Hindi, emojis, special chars.
        """
        log.info(f"Spotify: Searching for '{song_name}'")

        if not self._focus_spotify():
            self._open_spotify()
            time.sleep(5)
            self._focus_spotify()
            time.sleep(1)

        # Open Spotify search
        pyautogui.hotkey("ctrl", "l")
        time.sleep(1)

        # Clear and type song name — FIX: use clipboard paste
        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.2)
        _paste_type(song_name)  # ← was typewrite(), now clipboard-safe
        time.sleep(2)

        pyautogui.press("enter")
        time.sleep(1.5)
        pyautogui.press("enter")
        time.sleep(0.5)

        log.info(f"Spotify: Playing '{song_name}'")
        return f"Playing '{song_name}' on Spotify!"

    def spotify_play_current(self) -> str:
        """Play/resume the current song in Spotify."""
        if self._focus_spotify():
            time.sleep(0.3)
            pyautogui.press("space")
            return "Playing current song!"
        else:
            pyautogui.press("playpause")
            return "Playing!"

    def _focus_spotify(self) -> bool:
        """Focus the Spotify window."""
        for title in gw.getAllTitles():
            if "spotify" in title.lower():
                try:
                    win = gw.getWindowsWithTitle(title)[0]
                    if win.isMinimized:
                        win.restore()
                    win.activate()
                    time.sleep(0.5)
                    return True
                except Exception as e:
                    log.warning(f"Could not focus Spotify: {e}")
        return False

    def _open_spotify(self):
        """Open Spotify — FIX: dynamic path using home dir."""
        # FIX: use Path.home() instead of hardcoded 'srini'
        exe = Path.home() / "AppData" / "Roaming" / "Spotify" / "Spotify.exe"
        if exe.exists():
            subprocess.Popen(
                [str(exe)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        else:
            # Windows Search fallback
            pyautogui.press("win")
            time.sleep(1.5)
            _paste_type("spotify")
            time.sleep(2)
            pyautogui.press("enter")
        log.info("Opened Spotify")

    # ════════════════════════════════════════════════════════════
    #  ADVANCED: SLEEP TIMER
    # ════════════════════════════════════════════════════════════

    def set_sleep_timer(self, minutes: int) -> str:
        """
        Stop music after X minutes.
        Say: 'stop music in 30 minutes' / 'sleep timer 45 minutes'
        """
        global _sleep_timer

        if _sleep_timer and _sleep_timer.is_alive():
            _sleep_timer.cancel()
            log.info("Existing sleep timer cancelled")

        def _stop_music():
            pyautogui.press("stop")
            log.info(f"Sleep timer: music stopped after {minutes} min")

        _sleep_timer = threading.Timer(minutes * 60, _stop_music)
        _sleep_timer.daemon = True
        _sleep_timer.start()
        log.info(f"Sleep timer set: {minutes} minutes")
        return f"Music will stop in {minutes} minutes, sir. Sweet dreams!"

    def cancel_sleep_timer(self) -> str:
        """Cancel the active sleep timer."""
        global _sleep_timer
        if _sleep_timer and _sleep_timer.is_alive():
            _sleep_timer.cancel()
            _sleep_timer = None
            return "Sleep timer cancelled, sir."
        return "No active sleep timer, sir."

    def sleep_timer_status(self) -> str:
        """Check if sleep timer is active."""
        if _sleep_timer and _sleep_timer.is_alive():
            remaining = int(
                _sleep_timer.interval
                - (
                    time.time() - _sleep_timer._started
                    if hasattr(_sleep_timer, "_started")
                    else 0
                )
            )
            return "Sleep timer is active, sir."
        return "No active sleep timer, sir."

    # ════════════════════════════════════════════════════════════
    #  ADVANCED: VOLUME RAMP (smooth fade)
    # ════════════════════════════════════════════════════════════

    def fade_out(self, steps: int = 10) -> str:
        """Smoothly fade out volume to 0."""

        def _do_fade():
            for _ in range(steps * 2):
                pyautogui.press("volumedown")
                time.sleep(0.2)

        threading.Thread(target=_do_fade, daemon=True).start()
        return "Fading out volume, sir."

    def fade_in(self, steps: int = 10) -> str:
        """Smoothly fade in volume."""

        def _do_fade():
            for _ in range(steps * 2):
                pyautogui.press("volumeup")
                time.sleep(0.2)

        threading.Thread(target=_do_fade, daemon=True).start()
        return "Fading in volume, sir."

    # ════════════════════════════════════════════════════════════
    #  ADVANCED: LYRICS, RADIO, CURRENT SONG, PLAYLIST
    # ════════════════════════════════════════════════════════════

    def get_lyrics(self, song_name: str = None, artist: str = None) -> str:
        """
        Get lyrics for a song using lyrics.ovh free API.
        Say: 'show lyrics for Believer' / 'get lyrics of Shape of You by Ed Sheeran'
        """
        try:
            import json
            import urllib.parse
            import urllib.request

            if not song_name:
                return "Please specify a song name, sir."
            if not artist:
                # Try to guess from Spotify window title
                for title in gw.getAllTitles():
                    if "spotify" in title.lower() and "-" in title:
                        parts = title.split(" - ")
                        if len(parts) >= 2:
                            artist = parts[0].strip()
                            song_name = parts[1].strip()
                            break
                if not artist:
                    artist = "unknown"
            url = f"https://api.lyrics.ovh/v1/{urllib.parse.quote(artist)}/{urllib.parse.quote(song_name)}"
            req = urllib.request.Request(url, headers={"User-Agent": "JARVIS/2.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read())
            lyrics = data.get("lyrics", "")
            if not lyrics:
                return f"No lyrics found for '{song_name}', sir."
            # Return first verse (first ~300 chars)
            lines = [line.strip() for line in lyrics.split("\n") if line.strip()][:12]
            preview = "\n".join(lines)
            return f"Lyrics for '{song_name}':\n{preview}\n(showing first verse)"
        except Exception as e:
            log.error(f"Lyrics error: {e}")
            return f"Could not fetch lyrics for '{song_name}': {str(e)[:60]}"

    def play_radio(self, station: str = None) -> str:
        """
        Play an online radio station in the browser.
        Say: 'play radio' / 'play BBC radio' / 'play radio mirchi' / 'play AIR'
        """
        import urllib.parse
        import webbrowser

        STATIONS = {
            "bbc": "https://www.bbc.co.uk/sounds/play/live:bbc_radio_one",
            "bbc radio 1": "https://www.bbc.co.uk/sounds/play/live:bbc_radio_one",
            "bbc radio 2": "https://www.bbc.co.uk/sounds/play/live:bbc_radio_two",
            "radio mirchi": "https://www.radiomirchi.com/",
            "mirchi": "https://www.radiomirchi.com/",
            "air": "https://prasarbharati.gov.in/",
            "radio city": "https://www.radiocity.in/",
            "big fm": "https://www.bigfm.in/",
            "sun fm": "https://www.sunfm.in/",
            "fm": "https://www.radiomirchi.com/",
            "lofi": "https://www.youtube.com/watch?v=jfKfPfyJRdk",
            "jazz": "https://www.jazz24.org/",
            "classical": "https://www.classicalradio.com/",
        }
        if not station:
            station = "fm"
        station_lower = station.lower().strip()
        url = None
        for key, station_url in STATIONS.items():
            if key in station_lower or station_lower in key:
                url = station_url
                break
        if not url:
            url = f"https://www.google.com/search?q={urllib.parse.quote(station)}+radio+online+live"
        webbrowser.open(url)
        return f"Opening {station} radio, sir."

    def get_current_song(self) -> str:
        """Get the currently playing song from Spotify window title."""
        for title in gw.getAllTitles():
            if "spotify" in title.lower():
                # Spotify window title format: "Song Name - Artist"
                clean = title.replace("Spotify - ", "").replace("Spotify", "").strip()
                if clean and " - " in clean:
                    parts = clean.split(" - ")
                    song = parts[0].strip()
                    artist = " - ".join(parts[1:]).strip()
                    return f"Currently playing: '{song}' by {artist}, sir."
                elif clean:
                    return f"Spotify is playing: {clean}, sir."
        return "Spotify doesn't appear to be playing anything, sir."

    def create_playlist(self, songs: list) -> str:
        """
        Create a simple M3U playlist file from a list of songs.
        Say: 'create playlist with Believer, Shape of You, Blinding Lights'
        """
        if not songs:
            return "Please specify songs for the playlist, sir."
        from pathlib import Path

        playlist_path = Path.home() / "Desktop" / "jarvis_playlist.m3u"
        lines = ["#EXTM3U"]
        for song in songs:
            lines.append(f"#EXTINF:-1,{song}")
            yt_url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(song)}"
            lines.append(yt_url)
        playlist_path.write_text("\n".join(lines), encoding="utf-8")
        return f"Playlist created with {len(songs)} songs on Desktop: jarvis_playlist.m3u, sir."

    # ─── Parse media commands ────────────────────────────────
    def parse_media_command(self, text: str) -> tuple[str, str]:
        """
        Parse voice command → (action, detail).
        NEW: Detects sleep timer commands.
        """
        text_lower = text.lower().strip()

        # Sleep timer: "stop music in 30 minutes"
        sleep_m = re.search(
            r"(?:sleep timer|stop music in|stop in|music off in)\s*(\d+)\s*min",
            text_lower,
        )
        if sleep_m:
            return "sleep_timer", sleep_m.group(1)

        if "cancel sleep" in text_lower or "cancel timer" in text_lower:
            return "cancel_sleep", ""

        # Next / Previous
        if any(w in text_lower for w in ["next", "skip"]):
            return "next", ""
        if any(w in text_lower for w in ["previous", "back", "last track"]):
            return "previous", ""

        # Pause / Stop
        if "pause" in text_lower or "stop" in text_lower:
            return "pause", ""

        # Fade
        if "fade out" in text_lower:
            return "fade_out", ""
        if "fade in" in text_lower:
            return "fade_in", ""

        # Search and play a specific song
        if any(w in text_lower for w in ["play", "search", "find"]):
            song = text_lower
            for filler in [
                "play",
                "search for",
                "search",
                "find",
                "on spotify",
                "in spotify",
                "spotify",
                "the song",
                "song",
                "music",
            ]:
                song = song.replace(filler, "").strip()
            if song:
                return "search", song
            else:
                return "play", ""

        return "play", ""

    def execute(self, text: str) -> str:
        """Parse and execute a media command."""
        action, detail = self.parse_media_command(text)

        if action == "next":
            return self.next_track()
        elif action == "previous":
            return self.previous_track()
        elif action == "pause":
            return self.play_pause()
        elif action == "search" and detail:
            return self.spotify_search_and_play(detail)
        elif action == "sleep_timer" and detail:
            return self.set_sleep_timer(int(detail))
        elif action == "cancel_sleep":
            return self.cancel_sleep_timer()
        elif action == "fade_out":
            return self.fade_out()
        elif action == "fade_in":
            return self.fade_in()
        else:
            return self.play_pause()


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    mc = MediaController()
    tests = [
        "play Believer on Spotify",
        "next song",
        "pause",
        "stop music in 30 minutes",
    ]
    for t in tests:
        action, detail = mc.parse_media_command(t)
        print(f"'{t}' → action={action}, detail='{detail}'")
