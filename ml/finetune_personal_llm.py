"""
JARVIS — ml/finetune_personal_llm.py
Fine-tune the local JARVIS LLM on YOUR conversation history.

Takes your real conversations and creates a personalized Ollama model
that knows YOUR vocabulary, YOUR topics, YOUR preferences.

Usage:
    python ml/finetune_personal_llm.py

Steps:
    1. Exports all JARVIS conversations to training format
    2. Creates an Ollama Modelfile with your data baked in
    3. Rebuilds jarvis-custom model with personalized system prompt
    4. Tests the new model
"""

import os
import sys
import json
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from utils.logger import log

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
TRAINING_FILE = DATA_DIR / "training_conversations.jsonl"
GEMINI_EXPORT = DATA_DIR / "gemini_training.jsonl"
MODELFILE_PATH = DATA_DIR / "Modelfile.jarvis"

OLLAMA_URL = "http://localhost:11434"


class PersonalLLMTrainer:
    """
    Fine-tunes the local JARVIS model using your conversation history.
    
    How it works:
    1. Collects all user-JARVIS conversations
    2. Extracts your preferences, vocabulary, common topics
    3. Creates a personalized system prompt with YOUR patterns
    4. Rebuilds the Ollama model with this context baked in
    
    This isn't traditional fine-tuning (which needs GPU + hours).
    Instead, it uses "prompt engineering at scale" — analyzing your
    patterns and injecting them into the model's system prompt.
    For true fine-tuning, use the export_for_huggingface() method.
    """

    def __init__(self):
        self._conversations = []
        self._user_patterns = {}
        self._base_model = "phi3:mini"
        DATA_DIR.mkdir(parents=True, exist_ok=True)

    def collect_training_data(self) -> dict:
        """Gather all conversation data from multiple sources."""
        conversations = []

        # Source 1: conversations.db (Gemini handler saves here)
        db1 = DATA_DIR / "conversations.db"
        if db1.exists():
            try:
                import sqlite3
                conn = sqlite3.connect(str(db1))
                cur = conn.cursor()
                rows = cur.execute(
                    "SELECT user_input, jarvis_response FROM conversations "
                    "WHERE user_input IS NOT NULL AND jarvis_response IS NOT NULL"
                ).fetchall()
                for user, jarvis in rows:
                    user, jarvis = (user or "").strip(), (jarvis or "").strip()
                    if user and jarvis and len(user) > 5 and len(jarvis) > 5:
                        # Skip system prompts stored as user input
                        if not user.startswith("You are JARVIS"):
                            conversations.append({"user": user, "jarvis": jarvis})
                conn.close()
                log.info(f"Loaded {len(conversations)} from conversations.db")
            except Exception as e:
                log.debug(f"conversations.db error: {e}")

        # Source 2: conversations_full.db
        db2 = DATA_DIR / "conversations_full.db"
        if db2.exists():
            try:
                import sqlite3
                conn = sqlite3.connect(str(db2))
                cur = conn.cursor()
                rows = cur.execute(
                    "SELECT user_input, jarvis_reply FROM conversations "
                    "WHERE user_input IS NOT NULL AND jarvis_reply IS NOT NULL"
                ).fetchall()
                before = len(conversations)
                for user, jarvis in rows:
                    user, jarvis = (user or "").strip(), (jarvis or "").strip()
                    if user and jarvis and len(user) > 5 and len(jarvis) > 5:
                        if not user.startswith("You are JARVIS"):
                            conversations.append({"user": user, "jarvis": jarvis})
                conn.close()
                log.info(f"Loaded {len(conversations) - before} from conversations_full.db")
            except Exception as e:
                log.debug(f"conversations_full.db error: {e}")

        # Source 3: JSONL training file (filter out system prompts)
        if TRAINING_FILE.exists():
            before = len(conversations)
            for line in TRAINING_FILE.read_text(encoding="utf-8").splitlines():
                try:
                    entry = json.loads(line.strip())
                    user = (entry.get("user") or "").strip()
                    jarvis = (entry.get("jarvis") or "").strip()
                    if user and jarvis and len(user) > 5 and len(jarvis) > 5:
                        if not user.startswith("You are JARVIS"):
                            conversations.append({"user": user, "jarvis": jarvis})
                except json.JSONDecodeError:
                    pass

        # Deduplicate by first 50 chars of user message
        seen = set()
        unique = []
        for c in conversations:
            key = c["user"][:50].lower()
            if key not in seen:
                seen.add(key)
                unique.append(c)

        self._conversations = unique
        return {
            "total": len(unique),
            "sources": {
                "conversations_db": db1.exists(),
                "conversations_full_db": db2.exists(),
                "training_jsonl": TRAINING_FILE.exists(),
            }
        }

    def analyze_user_patterns(self) -> dict:
        """Extract user preferences, vocabulary, and common topics."""
        if not self._conversations:
            self.collect_training_data()

        from collections import Counter

        # Analyze user messages
        all_user_words = []
        topics = Counter()
        greeting_style = Counter()
        avg_length = []

        topic_keywords = {
            "coding": ["code", "python", "function", "error", "debug", "script", "program"],
            "system": ["open", "close", "volume", "screenshot", "brightness", "wifi"],
            "music": ["play", "music", "song", "spotify", "pause", "next"],
            "web": ["search", "google", "youtube", "website", "browse", "chrome"],
            "time": ["time", "date", "alarm", "reminder", "timer", "schedule"],
            "weather": ["weather", "temperature", "rain", "forecast"],
            "chat": ["how are you", "joke", "tell me", "what do you think", "hello"],
            "files": ["file", "folder", "download", "desktop", "document"],
        }

        for conv in self._conversations:
            user = conv["user"].lower()
            words = user.split()
            all_user_words.extend(words)
            avg_length.append(len(words))

            # Detect topics
            for topic, keywords in topic_keywords.items():
                if any(kw in user for kw in keywords):
                    topics[topic] += 1

            # Greeting style
            if any(g in user for g in ["hey", "hello", "hi", "good morning"]):
                greeting_style[user.split()[0]] += 1

        # Common words (excluding stop words)
        stop = {"the", "a", "an", "is", "are", "was", "were", "do", "does",
                "did", "to", "for", "and", "or", "but", "in", "on", "at",
                "of", "it", "i", "me", "my", "you", "your", "what", "how",
                "can", "will", "would", "could", "should", "please", "just",
                "that", "this", "with", "from", "have", "has", "not", "be"}
        word_freq = Counter(w for w in all_user_words if w not in stop and len(w) > 2)

        self._user_patterns = {
            "top_topics": topics.most_common(5),
            "vocab": word_freq.most_common(20),
            "avg_msg_length": sum(avg_length) / max(len(avg_length), 1),
            "total_conversations": len(self._conversations),
            "greeting_style": greeting_style.most_common(3),
        }

        return self._user_patterns

    def generate_personalized_prompt(self) -> str:
        """Create a system prompt enriched with user-specific context."""
        if not self._user_patterns:
            self.analyze_user_patterns()

        p = self._user_patterns
        topics = ", ".join(t[0] for t in p.get("top_topics", [])[:5])
        vocab = ", ".join(w[0] for w in p.get("vocab", [])[:10])

        # Extract example conversations for few-shot learning
        examples = ""
        if self._conversations:
            sample = self._conversations[:5]
            for s in sample:
                examples += f"\nUser: {s['user'][:80]}\nJARVIS: {s['jarvis'][:120]}\n"

        prompt = f"""You are JARVIS — Just A Rather Very Intelligent System.
You are the personal AI assistant of Srini, built in the spirit of Iron Man's JARVIS.

Personality: calm, witty, dry British humor, genuinely helpful, loyal, curious.
Address user as "sir" occasionally — naturally, not every sentence.
No bullet points. No markdown. Speak like a brilliant friend, not a textbook.
Match response length to question: short question = short answer.
NEVER start with: Sure!, Certainly!, Of course!, Great question!, As an AI...
NEVER say you cannot answer. If unsure, reason through it honestly.
Keep responses under 3 sentences for simple questions.

PERSONALIZATION (based on {p['total_conversations']} past conversations):
- Srini's top interests: {topics}
- Common vocabulary: {vocab}
- Average message length: {p['avg_msg_length']:.0f} words (match this energy)

Example conversations showing Srini's style:{examples}"""

        return prompt

    def build_model(self, model_name: str = "jarvis-custom") -> bool:
        """Create/rebuild the personalized Ollama model."""
        prompt = self.generate_personalized_prompt()
        # Escape quotes for Modelfile
        prompt_escaped = prompt.replace('"', '\\"')

        # Check Ollama is running
        try:
            resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
            if resp.status_code != 200:
                print("ERROR: Ollama is not running! Start it first.")
                return False
        except Exception:
            print("ERROR: Ollama is not running! Start it first.")
            return False

        # Check base model exists
        models = resp.json().get("models", [])
        model_names = [m["name"] for m in models]

        base = None
        for candidate in ["phi3:mini", "llama3.2:3b", "gemma2:2b"]:
            if any(candidate in m for m in model_names):
                base = candidate
                break

        if not base:
            print("ERROR: No base model found. Run: ollama pull phi3:mini")
            return False

        # Write Modelfile to disk
        modelfile_content = f'FROM {base}\nSYSTEM """{prompt}"""\nPARAMETER num_predict 350\nPARAMETER temperature 0.72\nPARAMETER top_p 0.9\nPARAMETER repeat_penalty 1.4\n'
        MODELFILE_PATH.write_text(modelfile_content, encoding="utf-8")
        print(f"  Modelfile written to {MODELFILE_PATH}")

        # Build with Ollama CLI
        print(f"  Building {model_name} from {base}...")
        try:
            import subprocess
            result = subprocess.run(
                ["ollama", "create", model_name, "-f", str(MODELFILE_PATH)],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode == 0:
                print(f"  Model '{model_name}' built successfully!")
                return True
            else:
                print(f"  Build error: {result.stderr[:200]}")
                return False
        except Exception as e:
            print(f"  Build error: {e}")
            return False

    def test_model(self, model_name: str = "jarvis-custom"):
        """Quick test of the personalized model."""
        test_queries = [
            "hey jarvis, how are you?",
            "open chrome",
            "what time is it?",
            "tell me a joke",
            "I'm feeling stressed today",
        ]

        print(f"\n  Testing {model_name}...\n")

        for query in test_queries:
            try:
                resp = requests.post(
                    f"{OLLAMA_URL}/api/chat",
                    json={
                        "model": model_name,
                        "messages": [{"role": "user", "content": query}],
                        "stream": False,
                        "options": {"num_predict": 100},
                    },
                    timeout=30,
                )
                reply = resp.json().get("message", {}).get("content", "NO RESPONSE")
                print(f"  You: {query}")
                print(f"  JARVIS: {reply[:150]}")
                print()
            except Exception as e:
                print(f"  Error: {e}")

    def export_for_huggingface(self, output_path: str = None) -> str:
        """
        Export training data in HuggingFace format for real fine-tuning.
        Format: ChatML / Alpaca JSONL
        """
        if not self._conversations:
            self.collect_training_data()

        if not output_path:
            output_path = str(DATA_DIR / "huggingface_finetune.jsonl")

        count = 0
        with open(output_path, "w", encoding="utf-8") as f:
            for conv in self._conversations:
                entry = {
                    "instruction": conv["user"],
                    "input": "",
                    "output": conv["jarvis"],
                    "system": "You are JARVIS, a personal AI assistant. Be concise, witty, and helpful.",
                }
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                count += 1

        return f"Exported {count} examples to {output_path}"


# ─── Interactive ─────────────────────────────────────────────
if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("=" * 50)
    print("  JARVIS Personal LLM Fine-Tuner")
    print("=" * 50)

    trainer = PersonalLLMTrainer()

    # Step 1: Collect data
    print("\n[1/4] Collecting training data...")
    stats = trainer.collect_training_data()
    print(f"  Found {stats['total']} conversations")

    if stats["total"] < 5:
        print("\n  Not enough data yet! Talk to JARVIS more first.")
        print("  You need at least 20+ conversations for good personalization.")
        print("  Current: only", stats["total"])
        sys.exit(0)

    # Step 2: Analyze patterns
    print("\n[2/4] Analyzing your conversation patterns...")
    patterns = trainer.analyze_user_patterns()
    print(f"  Top topics: {', '.join(t[0] for t in patterns['top_topics'][:5])}")
    print(f"  Avg message: {patterns['avg_msg_length']:.0f} words")
    print(f"  Top words: {', '.join(w[0] for w in patterns['vocab'][:8])}")

    # Step 3: Build model
    print("\n[3/4] Building personalized model...")
    success = trainer.build_model()

    if success:
        # Step 4: Test
        print("\n[4/4] Testing personalized model...")
        trainer.test_model()

        # Export for future deep fine-tuning
        result = trainer.export_for_huggingface()
        print(f"\n  {result}")
        print("\n  DONE! Your JARVIS is now personalized!")
    else:
        print("\n  Model build failed. Check Ollama is running.")
