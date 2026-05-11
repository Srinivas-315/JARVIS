"""
JARVIS — brain/vector_memory.py
Vector-based conversation memory (RAG) — JARVIS remembers everything forever.

Uses sentence-transformers for embedding + SQLite for storage.
Before each Gemini call, searches past conversations for relevant context.

Usage:
    vmem = VectorMemory()
    vmem.store("my exam is on Monday", role="user")
    results = vmem.search("when is my exam", top_k=3)
"""

import json
import os
import sqlite3
import time
import numpy as np
from datetime import datetime

from utils.logger import log

# Paths
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
VECTOR_DB_PATH = os.path.join(DATA_DIR, "vector_memory.db")

# Lazy-load the embedding model (loaded once on first use)
_model = None
_EMBED_DIM = 384  # all-MiniLM-L6-v2 output dimension


def _get_model():
    """Lazy-load the sentence-transformer model."""
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
            start = time.time()
            _model = SentenceTransformer("all-MiniLM-L6-v2")
            elapsed = (time.time() - start) * 1000
            log.info(f"VectorMemory: model loaded ({elapsed:.0f}ms)")
        except ImportError:
            log.warning(
                "VectorMemory: sentence-transformers not installed. "
                "Run: pip install sentence-transformers"
            )
            return None
        except Exception as e:
            log.warning(f"VectorMemory: model load failed: {e}")
            return None
    return _model


class VectorMemory:
    """
    Semantic vector memory for JARVIS.
    Stores conversation turns as embeddings in SQLite.
    Searches by cosine similarity for relevant past context.
    """

    def __init__(self, db_path: str = VECTOR_DB_PATH):
        self._db_path = db_path
        self._ready = False
        self._total_entries = 0
        self._init_db()

    def _init_db(self):
        """Initialize SQLite database for vector storage."""
        try:
            os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
            conn = sqlite3.connect(self._db_path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    text TEXT NOT NULL,
                    role TEXT NOT NULL,
                    intent TEXT DEFAULT '',
                    embedding BLOB NOT NULL,
                    timestamp TEXT NOT NULL,
                    session_id TEXT DEFAULT ''
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_memories_role
                ON memories(role)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_memories_timestamp
                ON memories(timestamp)
            """)
            conn.commit()

            # Count existing entries
            cursor = conn.execute("SELECT COUNT(*) FROM memories")
            self._total_entries = cursor.fetchone()[0]
            conn.close()

            self._ready = True
            log.info(
                f"VectorMemory: initialized ({self._total_entries} entries stored)"
            )
        except Exception as e:
            log.warning(f"VectorMemory: DB init failed: {e}")
            self._ready = False

    @property
    def is_ready(self) -> bool:
        return self._ready

    @property
    def total_entries(self) -> int:
        return self._total_entries

    def store(self, text: str, role: str = "user", intent: str = "",
              session_id: str = ""):
        """
        Store a conversation turn as a vector embedding.

        Args:
            text: The message text
            role: "user" or "assistant"
            intent: The classified intent (for filtering)
            session_id: Current session ID
        """
        if not self._ready or not text or len(text.strip()) < 3:
            return False

        model = _get_model()
        if model is None:
            return False

        try:
            # Generate embedding
            embedding = model.encode(text, normalize_embeddings=True)
            embedding_blob = embedding.astype(np.float32).tobytes()

            # Store in SQLite
            conn = sqlite3.connect(self._db_path)
            conn.execute(
                """INSERT INTO memories (text, role, intent, embedding, timestamp, session_id)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (text, role, intent, embedding_blob,
                 datetime.now().isoformat(), session_id)
            )
            conn.commit()
            conn.close()

            self._total_entries += 1
            return True

        except Exception as e:
            log.debug(f"VectorMemory store error: {e}")
            return False

    def search(self, query: str, top_k: int = 5,
               role_filter: str = None) -> list[dict]:
        """
        Search for relevant past conversations using cosine similarity.

        Args:
            query: Search query text
            top_k: Number of results to return
            role_filter: Optional filter by role ("user" or "assistant")

        Returns:
            List of {text, role, intent, timestamp, score}
        """
        if not self._ready or self._total_entries == 0:
            return []

        model = _get_model()
        if model is None:
            return []

        try:
            start = time.time()

            # Generate query embedding
            query_embedding = model.encode(query, normalize_embeddings=True)

            # Fetch all embeddings from DB
            conn = sqlite3.connect(self._db_path)
            if role_filter:
                rows = conn.execute(
                    "SELECT id, text, role, intent, embedding, timestamp "
                    "FROM memories WHERE role = ? ORDER BY id DESC LIMIT 5000",
                    (role_filter,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, text, role, intent, embedding, timestamp "
                    "FROM memories ORDER BY id DESC LIMIT 5000"
                ).fetchall()
            conn.close()

            if not rows:
                return []

            # Compute cosine similarities
            results = []
            for row in rows:
                stored_embedding = np.frombuffer(row[4], dtype=np.float32)
                # Cosine similarity (embeddings are already normalized)
                score = float(np.dot(query_embedding, stored_embedding))
                results.append({
                    "text": row[1],
                    "role": row[2],
                    "intent": row[3],
                    "timestamp": row[5],
                    "score": score,
                })

            # Sort by similarity score (descending)
            results.sort(key=lambda x: x["score"], reverse=True)

            elapsed = (time.time() - start) * 1000
            log.debug(
                f"VectorMemory: searched {len(rows)} entries in {elapsed:.0f}ms"
            )

            return results[:top_k]

        except Exception as e:
            log.debug(f"VectorMemory search error: {e}")
            return []

    def get_context_for_prompt(self, query: str, top_k: int = 5,
                                min_score: float = 0.3) -> str:
        """
        Get formatted context string for injecting into Gemini prompt.
        Only returns memories above the minimum similarity threshold.

        Args:
            query: Current user query
            top_k: Max number of memories to include
            min_score: Minimum similarity score (0-1)

        Returns:
            Formatted string of relevant past conversations
        """
        results = self.search(query, top_k=top_k)

        # Filter by minimum score
        relevant = [r for r in results if r["score"] >= min_score]

        if not relevant:
            return ""

        lines = ["Relevant past conversations:"]
        for r in relevant:
            role = "User" if r["role"] == "user" else "JARVIS"
            # Truncate long texts
            text = r["text"][:150]
            lines.append(f"- [{role}] {text} (similarity: {r['score']:.0%})")

        return "\n".join(lines)

    def get_stats(self) -> dict:
        """Get memory statistics."""
        if not self._ready:
            return {"ready": False, "total": 0}

        try:
            conn = sqlite3.connect(self._db_path)
            total = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
            user_count = conn.execute(
                "SELECT COUNT(*) FROM memories WHERE role='user'"
            ).fetchone()[0]
            assistant_count = conn.execute(
                "SELECT COUNT(*) FROM memories WHERE role='assistant'"
            ).fetchone()[0]

            # Get date range
            oldest = conn.execute(
                "SELECT timestamp FROM memories ORDER BY id ASC LIMIT 1"
            ).fetchone()
            newest = conn.execute(
                "SELECT timestamp FROM memories ORDER BY id DESC LIMIT 1"
            ).fetchone()
            conn.close()

            return {
                "ready": True,
                "total": total,
                "user_messages": user_count,
                "jarvis_messages": assistant_count,
                "oldest": oldest[0] if oldest else None,
                "newest": newest[0] if newest else None,
            }
        except Exception as e:
            return {"ready": False, "error": str(e)}


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("Initializing VectorMemory...")
    vmem = VectorMemory()

    if not vmem.is_ready:
        print("ERROR: VectorMemory not ready!")
        sys.exit(1)

    # Store some test conversations
    test_convos = [
        ("my exam is on Monday at 10am", "user"),
        ("Got it, I'll remind you about your exam on Monday.", "assistant"),
        ("play some lofi music", "user"),
        ("Playing lofi hip hop radio on YouTube.", "assistant"),
        ("my favorite food is biryani", "user"),
        ("I'll remember that you love biryani!", "assistant"),
        ("open VS Code", "user"),
        ("Opening Visual Studio Code for you.", "assistant"),
        ("what's the weather in Hyderabad", "user"),
        ("It's 35C and sunny in Hyderabad today.", "assistant"),
    ]

    print(f"\nStoring {len(test_convos)} test messages...")
    for text, role in test_convos:
        vmem.store(text, role=role)

    # Search tests
    test_queries = [
        "when is my exam",
        "what food do I like",
        "play music",
        "weather",
    ]

    for query in test_queries:
        print(f"\n🔍 Query: '{query}'")
        results = vmem.search(query, top_k=3)
        for r in results:
            print(f"  [{r['role']}] {r['text'][:60]} — score: {r['score']:.2f}")

    # Show context injection
    print("\n📋 Context for prompt:")
    ctx = vmem.get_context_for_prompt("when is my exam")
    print(ctx)

    print(f"\n📊 Stats: {vmem.get_stats()}")
    print("\n✅ VectorMemory working!")
