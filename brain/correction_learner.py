"""
JARVIS — brain/correction_learner.py
Learning from Corrections — JARVIS gets smarter every day.

When JARVIS does something wrong, you correct it.
JARVIS saves the correction and retrains itself automatically.

HOW IT WORKS:
  You:    "Open Chrome"
  JARVIS: Opens Notepad  ← wrong
  You:    "No, I meant Chrome"
          ↓
  JARVIS saves correction as training data
  JARVIS retrains ML model instantly
  Next time "Open Chrome" → always correct ✅

Storage: JARVIS/data/corrections.json  (tiny file, grows over time)
"""

import json
import os
import re
import pickle
import threading
from datetime import datetime
from utils.logger import log

# Paths
DATA_DIR        = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
CORRECTIONS_FILE = os.path.join(DATA_DIR, "corrections.json")
MODEL_PATH      = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                               "brain", "models", "intent_classifier.pkl")

# ── Correction trigger phrases ────────────────────────────────
# These tell us the user is correcting JARVIS
CORRECTION_PATTERNS = [
    r"no[,.]?\s+i (?:meant|mean|said|wanted|asked for)\s+(.+)",
    r"that'?s wrong[,.]?\s+i (?:said|meant|wanted)\s+(.+)",
    r"i didn'?t say (?:that|this)[,.]?\s+i said\s+(.+)",
    r"not (?:that|this)[,.]?\s+(?:i meant|i said|i want)\s+(.+)",
    r"wrong[,.]?\s+i (?:meant|wanted|said)\s+(.+)",
    r"i said\s+(.+)\s+not\s+.+",
    r"no[,.]?\s+(.+)\s+not\s+.+",
    r"(?:open|play|search|close|send)\s+(.+)\s+not\s+.+",
    r"i (?:meant|wanted|asked for)\s+(.+)",
    r"correct that[,.]?\s+(.+)",
    r"fix that[,.]?\s+(.+)",
    r"that'?s not (?:right|correct)[,.]?\s+(.+)",
]

# ── Intent mapping from keywords ─────────────────────────────
KEYWORD_TO_INTENT = {
    "open": "open_app",     "launch": "open_app",   "start": "open_app",
    "close": "close_app",   "quit": "close_app",    "exit": "close_app",
    "play": "media",        "pause": "media",        "next": "media",
    "search": "google_search",
    "youtube": "youtube",
    "weather": "weather",
    "news": "news",
    "message": "whatsapp",  "whatsapp": "whatsapp", "text": "whatsapp",
    "email": "send_email",
    "remind": "reminder",   "reminder": "reminder",
    "screenshot": "screenshot",
    "volume": "system_volume",
    "brightness": "system_brightness",
    "scroll": "screen_control", "click": "screen_control",
    "time": "time_date",    "date": "time_date",
    "joke": "joke",
    "stop": "stop",         "bye": "stop",
}


class CorrectionLearner:
    """
    Learns from user corrections to get smarter every day.
    Saves corrections → retrains ML model automatically.
    """

    def __init__(self):
        self._corrections = []
        self._last_command = ""      # What the user last said
        self._last_intent  = ""      # What JARVIS thought it meant
        self._last_response = ""     # What JARVIS did
        self._load_corrections()
        log.info(f"CorrectionLearner ready — {len(self._corrections)} corrections learned so far.")

    # ═══════════════════════════════════════════════════════════
    # TRACK WHAT JARVIS IS DOING
    # ═══════════════════════════════════════════════════════════

    def track(self, user_text: str, intent: str, response: str):
        """Call this after every command so we know what JARVIS did."""
        self._last_command  = user_text
        self._last_intent   = intent
        self._last_response = response

    # ═══════════════════════════════════════════════════════════
    # DETECT CORRECTION
    # ═══════════════════════════════════════════════════════════

    def is_correction(self, text: str) -> bool:
        """Check if the user is correcting JARVIS."""
        t = text.lower().strip()

        # Direct correction phrases
        if any(re.search(p, t) for p in CORRECTION_PATTERNS):
            return True

        # Simple: "No, [something]" when last command exists
        if t.startswith("no ") or t.startswith("no,"):
            return bool(self._last_command)

        return False

    def extract_correction(self, text: str) -> str:
        """Extract what the user actually meant from correction text."""
        t = text.lower().strip()

        for pattern in CORRECTION_PATTERNS:
            match = re.search(pattern, t)
            if match:
                return match.group(1).strip()

        # Simple "no, <actual command>"
        if t.startswith("no,"):
            return t[3:].strip()
        if t.startswith("no "):
            return t[3:].strip()

        return t

    def learn(self, correction_text: str) -> str:
        """
        Process a correction — save it and retrain.
        Returns a spoken response confirming the fix.
        """
        corrected_command = self.extract_correction(correction_text)
        if not corrected_command:
            return "What did you mean? Can you say that again?"

        # Guess the correct intent from the corrected command
        correct_intent = self._guess_intent(corrected_command)

        # Build training example
        example = {
            "original_heard":  self._last_command,
            "original_intent": self._last_intent,
            "corrected_command": corrected_command,
            "correct_intent":  correct_intent,
            "timestamp": datetime.now().isoformat(),
            "count": 1
        }

        # Check if similar correction already exists
        existing = self._find_similar(corrected_command)
        if existing:
            existing["count"] += 1
            log.info(f"Reinforced correction (×{existing['count']}): '{corrected_command}' → {correct_intent}")
        else:
            self._corrections.append(example)
            log.info(f"New correction learned: '{corrected_command}' → {correct_intent}")

        # Save to disk
        self._save_corrections()

        # Retrain ML model in background (non-blocking)
        threading.Thread(target=self._retrain, daemon=True).start()

        # Also update autocorrect if it was a word confusion
        self._update_autocorrect(self._last_command, corrected_command)

        return f"Got it. I'll remember that next time."


    # ═══════════════════════════════════════════════════════════
    # SMART INTENT GUESSER
    # ═══════════════════════════════════════════════════════════

    def _guess_intent(self, corrected_text: str) -> str:
        """Guess the correct intent using corrected text + original command context."""
        # Combine corrected text with original for full context
        # e.g. original="open something", correction="chrome" → "open chrome"
        if self._last_command and len(corrected_text.split()) <= 2:
            # Short correction — likely just the target, not the full command
            # Rebuild: take the verb from original + the corrected target
            original_words = self._last_command.lower().split()
            full_text = f"{original_words[0]} {corrected_text}" if original_words else corrected_text
        else:
            full_text = corrected_text

        # First: try existing ML model
        try:
            if os.path.exists(MODEL_PATH):
                with open(MODEL_PATH, "rb") as f:
                    model = pickle.load(f)
                pred = model.predict([full_text])[0]
                conf = model.predict_proba([full_text]).max()
                if conf > 0.4:
                    return pred
        except Exception:
            pass

        # Second: keyword matching on full rebuilt text
        t = full_text.lower()
        for keyword, intent in KEYWORD_TO_INTENT.items():
            if keyword in t:
                return intent

        # Third: fallback to original intent (it was probably right intent, wrong target)
        if self._last_intent and self._last_intent != "chat":
            return self._last_intent

        return "chat"


    # ═══════════════════════════════════════════════════════════
    # AUTO-RETRAIN ML MODEL
    # ═══════════════════════════════════════════════════════════

    def _retrain(self):
        """Retrain ML model with all corrections in background."""
        try:
            if not os.path.exists(MODEL_PATH):
                log.warning("Model not found — skipping retrain.")
                return

            log.info("Retraining ML model with corrections...")

            # Load existing model
            with open(MODEL_PATH, "rb") as f:
                model = pickle.load(f)

            # Get current training texts and labels from model
            # (TF-IDF pipeline stores them internally)
            extra_texts  = []
            extra_labels = []

            # Add ALL corrections as training data (repeat high-frequency ones)
            for c in self._corrections:
                cmd     = c["corrected_command"]
                intent  = c["correct_intent"]
                repeats = min(c.get("count", 1) * 3, 15)  # More repeats = stronger signal
                extra_texts.extend([cmd] * repeats)
                extra_labels.extend([intent] * repeats)

                # Also add original (wrong) command as negative example if intent differs
                if c["original_heard"] and c["original_intent"] != intent:
                    extra_texts.append(c["original_heard"])
                    extra_labels.append(intent)  # Now maps to correct intent

            if not extra_texts:
                return

            # Partial fit — add new examples to existing model
            # For sklearn Pipeline, we need to retrain with combined data
            # Extract existing training data from vectorizer vocabulary
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.linear_model import LogisticRegression
            from sklearn.pipeline import Pipeline

            # Get old training labels from the classifier
            old_classes = list(model.named_steps["classifier"].classes_)

            # Add new classes if any
            new_classes = list(set(extra_labels))
            all_classes = list(set(old_classes + new_classes))

            # Re-fit with extra data using warm_start trick
            # We transform using existing vectorizer + add new samples
            try:
                # Try incremental learning
                tfidf = model.named_steps["tfidf"]
                clf   = model.named_steps["classifier"]

                # Transform new examples using existing vocabulary
                X_new = tfidf.transform(extra_texts)

                # Partial fit (SGD or similar — LR doesn't support it natively)
                # So we use a smarter approach: retrain with all data
                # Get existing vocab coverage
                X_extra_dense = X_new

                # Use partial_fit if available, else just update with weighted samples
                if hasattr(clf, "partial_fit"):
                    clf.partial_fit(X_extra_dense, extra_labels, classes=all_classes)
                else:
                    # For LogisticRegression: retrain with boosted correction examples
                    # Load base training data from train_colab.py
                    base_texts, base_labels = self._load_base_training_data()
                    all_texts  = base_texts + extra_texts
                    all_labels = base_labels + extra_labels

                    new_model = Pipeline([
                        ("tfidf", TfidfVectorizer(
                            ngram_range=(1, 3),
                            max_features=15000,
                            sublinear_tf=True,
                            lowercase=True,
                        )),
                        ("classifier", LogisticRegression(
                            max_iter=3000, C=10.0,
                            class_weight="balanced",
                            solver="lbfgs",
                        ))
                    ])
                    new_model.fit(all_texts, all_labels)
                    model = new_model

            except Exception as e:
                log.warning(f"Incremental fit failed, doing full retrain: {e}")
                base_texts, base_labels = self._load_base_training_data()
                from sklearn.feature_extraction.text import TfidfVectorizer
                from sklearn.linear_model import LogisticRegression
                from sklearn.pipeline import Pipeline

                all_texts  = base_texts + extra_texts
                all_labels = base_labels + extra_labels

                model = Pipeline([
                    ("tfidf", TfidfVectorizer(ngram_range=(1, 3), max_features=15000,
                                               sublinear_tf=True, lowercase=True)),
                    ("classifier", LogisticRegression(max_iter=3000, C=10.0,
                                                       class_weight="balanced", solver="lbfgs"))
                ])
                model.fit(all_texts, all_labels)

            # Save updated model
            os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
            with open(MODEL_PATH, "wb") as f:
                pickle.dump(model, f)

            log.info(f"✅ ML model retrained with {len(extra_texts)} correction examples!")

        except Exception as e:
            log.error(f"Retrain error: {e}")

    def _load_base_training_data(self):
        """Load base training data for full retrain."""
        try:
            # Import base data from train script
            import importlib.util, sys
            train_path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                                      "brain", "train_colab.py")
            spec = importlib.util.spec_from_file_location("train_colab", train_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Get TRAINING_DATA and CUSTOM_DATA from train script
            base_data = []
            if hasattr(module, "TRAINING_DATA"):
                base_data.extend(module.TRAINING_DATA)
            if hasattr(module, "CUSTOM_DATA"):
                base_data.extend(module.CUSTOM_DATA)

            texts  = [d[0] for d in base_data]
            labels = [d[1] for d in base_data]
            return texts, labels

        except Exception as e:
            log.warning(f"Could not load base training data: {e}")
            return [], []

    # ═══════════════════════════════════════════════════════════
    # UPDATE AUTOCORRECT DICTIONARY
    # ═══════════════════════════════════════════════════════════

    def _update_autocorrect(self, wrong: str, right: str):
        """If words differ, add to autocorrect dictionary."""
        if not wrong or not right:
            return
        try:
            wrong_words = wrong.lower().split()
            right_words = right.lower().split()
            # If single word differs, add it
            if len(wrong_words) == 1 and len(right_words) == 1:
                from brain.autocorrect import WORD_FIXES
                if wrong_words[0] not in WORD_FIXES:
                    WORD_FIXES[wrong_words[0]] = right_words[0]
                    log.info(f"Autocorrect updated: '{wrong_words[0]}' → '{right_words[0]}'")
        except Exception:
            pass

    # ═══════════════════════════════════════════════════════════
    # STORAGE
    # ═══════════════════════════════════════════════════════════

    def _find_similar(self, text: str) -> dict:
        """Find an existing correction with same text."""
        t = text.lower().strip()
        for c in self._corrections:
            if c["corrected_command"].lower().strip() == t:
                return c
        return None

    def _load_corrections(self):
        """Load saved corrections from disk."""
        try:
            if os.path.exists(CORRECTIONS_FILE):
                with open(CORRECTIONS_FILE, "r", encoding="utf-8") as f:
                    self._corrections = json.load(f)
        except Exception as e:
            log.warning(f"Could not load corrections: {e}")
            self._corrections = []

    def _save_corrections(self):
        """Save corrections to disk."""
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(CORRECTIONS_FILE, "w", encoding="utf-8") as f:
                json.dump(self._corrections, f, indent=2, ensure_ascii=False)
        except Exception as e:
            log.error(f"Could not save corrections: {e}")

    def get_stats(self) -> str:
        """How many corrections has JARVIS learned?"""
        n = len(self._corrections)
        total = sum(c.get("count", 1) for c in self._corrections)
        if n == 0:
            return "No corrections learned yet. Just correct me when I'm wrong!"
        return f"I've learned {n} corrections, reinforced {total} times."


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    learner = CorrectionLearner()

    # Simulate wrong command + correction
    learner.track("open crome", "open_app", "Opened Notepad")
    print("Is correction:", learner.is_correction("no I meant chrome"))
    print("Extracted:", learner.extract_correction("no I meant chrome"))
    result = learner.learn("no I meant chrome")
    print("Response:", result)
    print("Stats:", learner.get_stats())
