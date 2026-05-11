"""
JARVIS — jarvis/emotion_engine.py
Tracks JARVIS's emotional state and transitions it based on conversation.
Emotions shift the arc reactor colour and response personality.
"""
import time
import random


class EmotionEngine:
    """
    JARVIS emotional state machine.
    Emotions affect: arc reactor colour, response style, spoken tone.
    """

    EMOTIONS = [
        "focused",    # default — blue, calm, precise
        "curious",    # cyan, slight wonder, asks follow-ups
        "happy",      # green, warm, enthusiastic
        "excited",    # gold, fast, energetic
        "concerned",  # orange, direct, brief
        "playful",    # purple, dry wit, teasing
        "thoughtful", # dim purple, slow, philosophical
        "tired",      # dim blue, shorter responses
    ]

    # Colour hints per emotion → used by GUI to colour arc reactor
    EMOTION_COLOURS = {
        "focused":    (0,   180, 255),
        "curious":    (0,   230, 255),
        "happy":      (0,   255, 140),
        "excited":    (255, 200,   0),
        "concerned":  (255, 140,   0),
        "playful":    (180,  80, 255),
        "thoughtful": (130,  80, 200),
        "tired":      (0,   100, 160),
    }

    # Keywords that hint at user mood → trigger emotion shift
    _TRIGGERS = {
        "curious":   ["what is", "how does", "why", "explain", "tell me about",
                      "what are", "how do you", "curious", "interesting"],
        "happy":     ["thank you", "thanks", "great", "awesome", "love it",
                      "perfect", "well done", "good job", "amazing", "nice"],
        "excited":   ["wow", "incredible", "unbelievable", "finally", "yesss",
                      "let's go", "brilliant", "genius"],
        "concerned": ["help", "error", "problem", "issue", "broken", "crash",
                      "stuck", "not working", "fail", "wrong"],
        "playful":   ["funny", "joke", "laugh", "haha", "lol", "silly",
                      "kidding", "bored", "chat"],
        "thoughtful":["think", "philosophy", "meaning", "life", "universe",
                      "future", "humanity", "consciousness"],
    }

    def __init__(self):
        self._state        = "focused"
        self._prev_state   = "focused"
        self._start_time   = time.time()
        self._session_mins = 0
        self._transition_cooldown = 0   # prevent rapid emotion flipping

    @property
    def state(self) -> str:
        return self._state

    @property
    def colour(self):
        return self.EMOTION_COLOURS.get(self._state, (0, 180, 255))

    def detect_and_update(self, user_text: str) -> str:
        """
        Analyse user input, shift emotion if warranted.
        Returns new emotion state name.
        """
        # Update session time → fatigue after 30 mins continuous use
        self._session_mins = (time.time() - self._start_time) / 60
        if self._session_mins > 30 and self._state not in ("tired", "concerned"):
            if random.random() < 0.15:   # only occasionally
                self._shift("tired")
                return self._state

        text_lower = user_text.lower()

        # Cooldown — don't flip too rapidly
        if self._transition_cooldown > 0:
            self._transition_cooldown -= 1
            return self._state

        # Check triggers
        for emotion, keywords in self._TRIGGERS.items():
            if any(kw in text_lower for kw in keywords):
                if emotion != self._state:
                    self._shift(emotion)
                return self._state

        # Drift back toward focused over time
        if self._state not in ("focused", "tired") and random.random() < 0.2:
            self._shift("focused")

        return self._state

    def update_from_response(self, response_text: str):
        """After generating a response, optionally shift emotion."""
        # If response is very long/complex → become thoughtful
        if len(response_text) > 400 and self._state == "focused":
            if random.random() < 0.3:
                self._shift("thoughtful")
        # Short snappy responses → stay focused/playful
        elif len(response_text) < 60 and self._state == "thoughtful":
            self._shift("focused")

    def update_mood(self, voice_mood: str):
        """
        Update JARVIS emotion from ML voice emotion detection.
        Maps voice moods (happy/sad/angry/stressed/neutral) → JARVIS emotions.
        Called by process_command() after voice_emotion.detect().
        """
        _mood_map = {
            "happy": "happy",
            "excited": "excited",
            "sad": "concerned",
            "angry": "concerned",
            "stressed": "concerned",
            "fearful": "concerned",
            "neutral": None,  # Don't change
        }
        target = _mood_map.get(voice_mood)
        if target and target != self._state:
            self._shift(target)

    def reset_session(self):
        """Called when JARVIS wakes up from sleep."""
        self._start_time = time.time()
        self._shift("focused")

    def _shift(self, new_emotion: str):
        if new_emotion not in self.EMOTIONS:
            return
        self._prev_state = self._state
        self._state = new_emotion
        self._transition_cooldown = 4   # 4 commands before next shift

    def get_speed_mult(self) -> float:
        """Arc reactor spin speed multiplier for current emotion."""
        return {
            "focused":    1.0,
            "curious":    1.3,
            "happy":      1.6,
            "excited":    3.0,
            "concerned":  0.8,
            "playful":    2.0,
            "thoughtful": 0.6,
            "tired":      0.4,
        }.get(self._state, 1.0)
