"""
JARVIS — brain/conversation_learner.py
Auto-Learning System - Learn from conversations & retrain monthly

This module:
  1. Logs all user-JARVIS conversations automatically
  2. Analyzes patterns in how the user communicates
  3. Generates synthetic training data based on learned patterns
  4. Retrains the local Ollama model monthly
  5. Adapts JARVIS personality to user's communication style

Usage:
  from brain.conversation_learner import ConversationLearner
  learner = ConversationLearner()
  learner.log_conversation(user_input, jarvis_response)
  learner.check_and_retrain()  # Run monthly
"""

import json
import os
import pickle
import re
import sqlite3
import subprocess
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from utils.logger import log

# ══════════════════════════════════════════════════════════════
# Configuration
# ══════════════════════════════════════════════════════════════

DATA_DIR = Path("data")
CONVERSATIONS_DB = DATA_DIR / "conversations.db"
LEARNED_PATTERNS_FILE = DATA_DIR / "learned_patterns.json"
RETRAINING_LOG = DATA_DIR / "retraining_log.json"
SYNTHETIC_TRAINING_FILE = DATA_DIR / "synthetic_training_data.jsonl"

RETRAINING_THRESHOLD = 500  # Retrain after 500 conversations
DAYS_BETWEEN_RETRAINING = 30  # Auto-retrain every 30 days


class ConversationDatabase:
    """SQLite database for storing and querying conversations."""

    def __init__(self, db_path: str = str(CONVERSATIONS_DB)):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize database schema."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS conversations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                        user_input TEXT NOT NULL,
                        jarvis_response TEXT NOT NULL,
                        intent TEXT,
                        sentiment TEXT,
                        quality_score REAL,
                        api_used TEXT,
                        response_time_ms INTEGER
                    )
                    """
                )

                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS user_preferences (
                        key TEXT PRIMARY KEY,
                        value TEXT,
                        learned_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )

                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_timestamp
                    ON conversations(timestamp)
                    """
                )

                conn.commit()
                log.debug("Conversation database initialized")
        except Exception as e:
            log.error(f"Failed to initialize conversation DB: {e}")

    def log_conversation(
        self,
        user_input: str,
        jarvis_response: str,
        intent: Optional[str] = None,
        sentiment: Optional[str] = None,
        quality_score: float = 1.0,
        api_used: str = "local",
        response_time_ms: int = 0,
    ):
        """Log a conversation turn."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO conversations
                    (user_input, jarvis_response, intent, sentiment, quality_score, api_used, response_time_ms)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_input,
                        jarvis_response,
                        intent,
                        sentiment,
                        quality_score,
                        api_used,
                        response_time_ms,
                    ),
                )
                conn.commit()
        except Exception as e:
            log.warning(f"Failed to log conversation: {e}")

    def get_total_conversations(self) -> int:
        """Get total number of logged conversations."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM conversations")
                return cursor.fetchone()[0]
        except:
            return 0

    def get_recent_conversations(self, days: int = 30) -> List[Dict]:
        """Get conversations from the last N days."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cutoff_date = datetime.now() - timedelta(days=days)
                cursor.execute(
                    """
                    SELECT * FROM conversations
                    WHERE timestamp > ?
                    ORDER BY timestamp DESC
                    """,
                    (cutoff_date.isoformat(),),
                )
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            log.warning(f"Failed to retrieve conversations: {e}")
            return []

    def get_intents_distribution(self) -> Dict[str, int]:
        """Get distribution of intents from conversations."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT intent, COUNT(*) FROM conversations WHERE intent IS NOT NULL GROUP BY intent"
                )
                return dict(cursor.fetchall())
        except:
            return {}

    def save_user_preference(self, key: str, value: str):
        """Save a learned user preference."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT OR REPLACE INTO user_preferences (key, value) VALUES (?, ?)",
                    (key, value),
                )
                conn.commit()
        except Exception as e:
            log.warning(f"Failed to save preference: {e}")

    def get_user_preferences(self) -> Dict[str, str]:
        """Get all learned user preferences."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT key, value FROM user_preferences")
                return dict(cursor.fetchall())
        except:
            return {}


class PatternAnalyzer:
    """Analyze conversation patterns to understand user communication style."""

    def __init__(self, conversations: List[Dict]):
        self.conversations = conversations
        self.patterns = {}

    def analyze(self) -> Dict:
        """Run full pattern analysis."""
        self.patterns = {
            "common_phrases": self._extract_common_phrases(),
            "average_response_length": self._avg_response_length(),
            "sentiment_distribution": self._sentiment_distribution(),
            "preferred_formality": self._detect_formality(),
            "common_greetings": self._extract_common_greetings(),
            "common_sign_offs": self._extract_common_sign_offs(),
            "question_types": self._question_type_distribution(),
            "preferred_tone": self._detect_tone(),
        }
        return self.patterns

    def _extract_common_phrases(self, top_n: int = 20) -> List[tuple]:
        """Extract most common phrases from user inputs."""
        phrases = []
        for conv in self.conversations:
            user_input = str(conv.get("user_input", "")).lower()
            words = user_input.split()
            for i in range(len(words) - 2):
                phrase = " ".join(words[i : i + 3])
                if len(phrase) > 10 and phrase not in ["hello jarvis", "hi jarvis"]:
                    phrases.append(phrase)

        counter = Counter(phrases)
        return counter.most_common(top_n)

    def _avg_response_length(self) -> int:
        """Calculate average response length."""
        if not self.conversations:
            return 0
        lengths = [len(str(conv.get("jarvis_response", ""))) for conv in self.conversations]
        return int(sum(lengths) / len(lengths))

    def _sentiment_distribution(self) -> Dict[str, int]:
        """Analyze sentiment distribution."""
        sentiments = {}
        for conv in self.conversations:
            sentiment = str(conv.get("sentiment", "neutral"))
            sentiments[sentiment] = sentiments.get(sentiment, 0) + 1
        return sentiments

    def _detect_formality(self) -> str:
        """Detect if user prefers formal or casual language."""
        casual_words = ["bro", "dude", "lol", "yeah", "nah", "gonna", "wanna"]
        formal_words = ["please", "kindly", "appreciate", "sincerely"]

        casual_count = 0
        formal_count = 0

        for conv in self.conversations:
            user_input = str(conv.get("user_input", "")).lower()
            casual_count += sum(user_input.count(w) for w in casual_words)
            formal_count += sum(user_input.count(w) for w in formal_words)

        if casual_count > formal_count:
            return "casual"
        elif formal_count > casual_count:
            return "formal"
        return "neutral"

    def _extract_common_greetings(self, top_n: int = 10) -> List[str]:
        """Extract common greeting patterns."""
        greetings = []
        greeting_patterns = [
            r"^(hey|hi|hello|yo|sup)",
            r"^(good morning|good afternoon|good evening)",
            r"^(jarvis|hey jarvis|hi jarvis)",
        ]

        for conv in self.conversations[:100]:  # Sample first 100
            user_input = str(conv.get("user_input", "")).lower()
            for pattern in greeting_patterns:
                if re.match(pattern, user_input):
                    greetings.append(user_input.split()[0])

        counter = Counter(greetings)
        return [g for g, _ in counter.most_common(top_n)]

    def _extract_common_sign_offs(self, top_n: int = 10) -> List[str]:
        """Extract common ways user ends conversations."""
        sign_offs = []
        sign_off_patterns = [
            r"(thanks|thank you|appreciate|bye|goodbye|see you|thanks jarvis)",
        ]

        for conv in self.conversations[-100:]:  # Sample last 100
            user_input = str(conv.get("user_input", "")).lower()
            for pattern in sign_off_patterns:
                if re.search(pattern, user_input):
                    sign_offs.append(user_input)

        return list(set(sign_offs))[:top_n]

    def _question_type_distribution(self) -> Dict[str, int]:
        """Categorize types of questions user asks."""
        types = {}
        for conv in self.conversations:
            user_input = str(conv.get("user_input", ""))

            if "?" in user_input:
                qtype = "question"
            elif any(
                user_input.lower().startswith(cmd)
                for cmd in ["open", "close", "play", "set", "send"]
            ):
                qtype = "command"
            else:
                qtype = "statement"

            types[qtype] = types.get(qtype, 0) + 1

        return types

    def _detect_tone(self) -> str:
        """Detect user's preferred tone (humorous, serious, helpful, etc)."""
        # Simple heuristic - count exclamation marks, emojis, etc
        exclamations = sum(
            str(conv.get("user_input", "")).count("!") for conv in self.conversations
        )
        questions = sum(
            str(conv.get("user_input", "")).count("?") for conv in self.conversations
        )

        if exclamations > len(self.conversations) * 0.3:
            return "enthusiastic"
        elif questions > len(self.conversations) * 0.6:
            return "inquisitive"
        return "neutral"


class SyntheticDataGenerator:
    """Generate synthetic training data based on learned patterns."""

    def __init__(self, patterns: Dict, original_conversations: List[Dict]):
        self.patterns = patterns
        self.conversations = original_conversations

    def generate(self, count: int = 100) -> List[Dict]:
        """Generate synthetic training examples."""
        synthetic_data = []

        # Use learned patterns to generate variations
        common_phrases = self.patterns.get("common_phrases", [])
        common_greetings = self.patterns.get("common_greetings", [])
        formality = self.patterns.get("preferred_formality", "neutral")

        for i in range(count):
            if i % 3 == 0 and common_greetings:
                # Generate greeting-based example
                greeting = common_greetings[i % len(common_greetings)]
                user_input = f"{greeting} what's the time"
                jarvis_response = f"Good to hear from you. It's currently 3:45 PM."
            elif i % 3 == 1 and common_phrases:
                # Generate phrase-based example
                phrase = common_phrases[i % len(common_phrases)][0]
                user_input = phrase
                jarvis_response = f"Understood. I'll help with that."
            else:
                # Use existing conversation as template
                template = self.conversations[i % len(self.conversations)]
                user_input = template.get("user_input", "")
                jarvis_response = template.get("jarvis_response", "")

            synthetic_data.append(
                {
                    "user": user_input,
                    "jarvis": jarvis_response,
                    "synthetic": True,
                    "generated_at": datetime.now().isoformat(),
                }
            )

        return synthetic_data

    def save_synthetic_data(self, synthetic_data: List[Dict]):
        """Save synthetic data to JSONL file."""
        try:
            DATA_DIR.mkdir(exist_ok=True)
            with open(SYNTHETIC_TRAINING_FILE, "a", encoding="utf-8") as f:
                for item in synthetic_data:
                    f.write(json.dumps(item, ensure_ascii=False) + "\n")
            log.info(f"Saved {len(synthetic_data)} synthetic training examples")
        except Exception as e:
            log.error(f"Failed to save synthetic data: {e}")


class ConversationLearner:
    """
    Main class for conversation learning and retraining.
    Manages the full cycle of logging, analyzing, and retraining.
    """

    def __init__(self):
        self.db = ConversationDatabase()
        self.should_check_retrain = True

    def log_conversation(
        self,
        user_input: str,
        jarvis_response: str,
        intent: Optional[str] = None,
        quality_score: float = 1.0,
        api_used: str = "local",
        response_time_ms: int = 0,
    ):
        """Log a conversation for learning."""
        sentiment = self._detect_sentiment(user_input)

        self.db.log_conversation(
            user_input=user_input,
            jarvis_response=jarvis_response,
            intent=intent,
            sentiment=sentiment,
            quality_score=quality_score,
            api_used=api_used,
            response_time_ms=response_time_ms,
        )

        # Check if we should retrain
        if self.should_check_retrain:
            self.check_and_retrain()

    def _detect_sentiment(self, text: str) -> str:
        """Simple sentiment detection."""
        negative_words = ["angry", "sad", "bad", "hate", "terrible", "awful"]
        positive_words = ["happy", "great", "love", "awesome", "excellent", "perfect"]

        text_lower = text.lower()
        neg_count = sum(text_lower.count(w) for w in negative_words)
        pos_count = sum(text_lower.count(w) for w in positive_words)

        if neg_count > pos_count:
            return "negative"
        elif pos_count > neg_count:
            return "positive"
        return "neutral"

    def check_and_retrain(self):
        """Check if retraining is needed and execute if necessary."""
        conversation_count = self.db.get_total_conversations()
        last_retrain = self._get_last_retrain_time()
        days_since = (datetime.now() - last_retrain).days if last_retrain else 999

        should_retrain_by_count = conversation_count > RETRAINING_THRESHOLD
        should_retrain_by_time = days_since >= DAYS_BETWEEN_RETRAINING

        if should_retrain_by_count or should_retrain_by_time:
            log.info(
                f"Starting retraining (conversations: {conversation_count}, days: {days_since})"
            )
            self.execute_retraining()

    def execute_retraining(self):
        """Execute the full retraining pipeline."""
        try:
            log.info("🔄 Starting JARVIS retraining cycle...")

            # 1. Get recent conversations
            recent_convs = self.db.get_recent_conversations(days=30)
            if len(recent_convs) < 100:
                log.warning("Not enough conversations for meaningful retraining")
                return

            # 2. Analyze patterns
            log.info("Analyzing conversation patterns...")
            analyzer = PatternAnalyzer(recent_convs)
            patterns = analyzer.analyze()
            self._save_patterns(patterns)

            # 3. Generate synthetic data
            log.info("Generating synthetic training data...")
            generator = SyntheticDataGenerator(patterns, recent_convs)
            synthetic_data = generator.generate(count=len(recent_convs) // 2)
            generator.save_synthetic_data(synthetic_data)

            # 4. Create updated Modelfile
            log.info("Updating model personality...")
            self._create_updated_modelfile(patterns)

            # 5. Retrain Ollama model
            log.info("Retraining Ollama model...")
            self._retrain_ollama_model()

            # 6. Record retraining event
            self._record_retraining_event(patterns)

            log.info("✅ Retraining complete!")

        except Exception as e:
            log.error(f"Retraining failed: {e}")

    def _save_patterns(self, patterns: Dict):
        """Save learned patterns to file."""
        try:
            DATA_DIR.mkdir(exist_ok=True)
            with open(LEARNED_PATTERNS_FILE, "w", encoding="utf-8") as f:
                json.dump(patterns, f, indent=2, ensure_ascii=False)
        except Exception as e:
            log.warning(f"Failed to save patterns: {e}")

    def _create_updated_modelfile(self, patterns: Dict):
        """Create an updated Modelfile incorporating learned patterns."""
        formality = patterns.get("preferred_formality", "neutral")
        tone = patterns.get("preferred_tone", "neutral")
        common_phrases = patterns.get("common_phrases", [])[:5]

        formality_note = (
            "Be casual and friendly"
            if formality == "casual"
            else "Be formal and professional"
            if formality == "formal"
            else "Be balanced"
        )

        tone_note = (
            "Use humor and enthusiasm"
            if tone == "enthusiastic"
            else "Be thorough and inquisitive in responses"
            if tone == "inquisitive"
            else "Maintain a neutral, helpful tone"
        )

        modelfile_content = f"""FROM llama3.2:3b

# JARVIS - Learned from {self.db.get_total_conversations()} conversations
# Updated: {datetime.now().strftime("%Y-%m-%d")}

SYSTEM \"\"\"You are JARVIS - the personal AI assistant.

LEARNED COMMUNICATION STYLE:
- {formality_note}
- {tone_note}
- User commonly uses phrases like: {", ".join([p[0][:20] for p in common_phrases])}

[Include your standard JARVIS system prompt here]
\"\"\"

PARAMETER temperature 0.75
PARAMETER top_p 0.9
PARAMETER repeat_penalty 1.3
PARAMETER num_predict 200
"""

        try:
            with open("Modelfile.learned", "w", encoding="utf-8") as f:
                f.write(modelfile_content)
            log.info("Created updated Modelfile.learned")
        except Exception as e:
            log.warning(f"Failed to create updated Modelfile: {e}")

    def _retrain_ollama_model(self):
        """Execute ollama create to retrain the model."""
        try:
            # Build new model
            result = subprocess.run(
                ["ollama", "create", "jarvis-custom", "-f", "Modelfile.learned"],
                capture_output=True,
                timeout=300,
            )

            if result.returncode == 0:
                log.info("✅ Ollama model retrained successfully")
            else:
                log.warning(f"Ollama retraining warning: {result.stderr.decode()}")

        except FileNotFoundError:
            log.warning("Ollama not found - skipping model retraining")
        except subprocess.TimeoutExpired:
            log.warning("Ollama retraining timed out")
        except Exception as e:
            log.warning(f"Ollama retraining failed: {e}")

    def _record_retraining_event(self, patterns):
        """Record that retraining was performed."""
        try:
            DATA_DIR.mkdir(exist_ok=True)

            event = {
                "timestamp": datetime.now().isoformat(),
                "conversation_count": self.db.get_total_conversations(),
                "patterns_learned": len(patterns) if hasattr(patterns, '__len__') else 0,
                "intents": self.db.get_intents_distribution(),
            }

            retraining_log = []
            if RETRAINING_LOG.exists():
                with open(RETRAINING_LOG, "r") as f:
                    retraining_log = json.load(f)

            retraining_log.append(event)

            with open(RETRAINING_LOG, "w") as f:
                json.dump(retraining_log, f, indent=2)

        except Exception as e:
            log.warning(f"Failed to record retraining: {e}")

    def _get_last_retrain_time(self) -> Optional[datetime]:
        """Get timestamp of last retraining."""
        try:
            if RETRAINING_LOG.exists():
                with open(RETRAINING_LOG, "r") as f:
                    log_data = json.load(f)
                    if log_data:
                        last = log_data[-1]
                        return datetime.fromisoformat(last["timestamp"])
        except:
            pass
        return None

    def get_stats(self) -> Dict:
        """Get learning statistics."""
        return {
            "total_conversations": self.db.get_total_conversations(),
            "last_retrain": self._get_last_retrain_time(),
            "user_preferences": self.db.get_user_preferences(),
            "intent_distribution": self.db.get_intents_distribution(),
        }


# ══════════════════════════════════════════════════════════════
# Testing & Validation
# ══════════════════════════════════════════════════════════════


def test_conversation_learner():
    """Test the conversation learner."""
    print("\n🧪 Testing Conversation Learner...\n")

    learner = ConversationLearner()

    # Log some test conversations
    test_conversations = [
        ("Hey Jarvis what's the weather", "It's sunny and 28°C in Chennai"),
        ("Open chrome", "Opening Google Chrome..."),
        ("What's the time", "It's currently 3:45 PM"),
        (
            "Tell me a joke",
            "Why do programmers prefer dark mode? Because light attracts bugs",
        ),
    ]

    for user_input, response in test_conversations:
        learner.log_conversation(user_input, response)

    stats = learner.get_stats()
    print(f"Stats: {json.dumps(stats, indent=2, default=str)}")


if __name__ == "__main__":
    test_conversation_learner()
