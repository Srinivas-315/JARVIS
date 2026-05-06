"""
JARVIS — skills/code_memory.py
Persistent memory of every coding problem JARVIS has solved.

Stores problem + solution pairs in SQLite so JARVIS:
  1. Never forgets a solution
  2. Builds a training dataset for future fine-tuning
  3. Can recall similar problems without calling the API
  4. Tracks improvement stats over time

Database: data/code_memory.db
"""

import json
import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path

from utils.logger import log

# ─── Database location ───────────────────────────────────────
_DB_DIR = Path(__file__).parent.parent / "data"
_DB_PATH = _DB_DIR / "code_memory.db"

# ─── Common DSA tags for auto-detection ──────────────────────
_TAG_PATTERNS = {
    "array": r"\barray\b|\blist\b|\bnums\b|\bint\[\]",
    "string": r"\bstring\b|\bsubstring\b|\bpalindrome\b|\banagram\b",
    "hash-map": r"\bhash\s?map\b|\bdictionary\b|\bhash\s?table\b|\btwo\s?sum\b",
    "two-pointer": r"\btwo\s?pointer\b|\bsorted\s?array\b|\bcontainer\b",
    "sliding-window": r"\bsliding\s?window\b|\bsubarray\b|\bwindow\b",
    "linked-list": r"\blinked\s?list\b|\blistnode\b|\bhead\b.*\bnext\b",
    "tree": r"\bbinary\s?tree\b|\btreenode\b|\broot\b.*\bleft\b.*\bright\b|\bbst\b",
    "graph": r"\bgraph\b|\badjacency\b|\bnode\b.*\bneighbor\b|\bbfs\b|\bdfs\b",
    "dynamic-programming": r"\bdynamic\s?program\b|\bdp\b|\bmemoiz\b|\btabul\b|\boptimal\s?substruct\b",
    "greedy": r"\bgreedy\b|\binterval\b|\bactivity\b|\bschedul\b",
    "backtracking": r"\bbacktrack\b|\bpermut\b|\bcombinat\b|\bsubset\b",
    "binary-search": r"\bbinary\s?search\b|\bsorted\b.*\bfind\b|\blog\s?n\b",
    "stack": r"\bstack\b|\bparenthes\b|\bvalid\s?parenthes\b|\bmonoton\b",
    "queue": r"\bqueue\b|\bbfs\b|\blevel\s?order\b",
    "heap": r"\bheap\b|\bpriority\s?queue\b|\btop\s?k\b|\bkth\s?largest\b",
    "recursion": r"\brecurs\b|\bdivide\s?and\s?conquer\b",
    "sorting": r"\bsort\b|\bmerge\s?sort\b|\bquick\s?sort\b",
    "math": r"\bmath\b|\bprime\b|\bfactorial\b|\bgcd\b|\bmodulo\b",
    "bit-manipulation": r"\bbit\b|\bxor\b|\band\b.*\bor\b|\bbitwise\b",
    "trie": r"\btrie\b|\bprefix\s?tree\b|\bautocomplete\b",
    "union-find": r"\bunion\s?find\b|\bdisjoint\b|\bconnected\s?component\b",
    "matrix": r"\bmatrix\b|\bgrid\b|\b2d\s?array\b|\brow\b.*\bcol\b",
}


class CodeMemory:
    """
    Persistent SQLite memory of every coding problem JARVIS solves.
    
    Auto-detects problem tags, tracks success rates, and exports
    training data for future model fine-tuning.
    """

    def __init__(self):
        _DB_DIR.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._create_tables()
        count = self._count()
        if count > 0:
            log.info(f"CodeMemory loaded — {count} solved problems in database")
        else:
            log.info("CodeMemory initialized — empty database, ready to learn!")

    def _create_tables(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS solutions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                problem_name TEXT,
                problem_text TEXT,
                difficulty TEXT DEFAULT 'unknown',
                tags TEXT DEFAULT '[]',
                approach TEXT,
                complexity TEXT,
                solution_code TEXT NOT NULL,
                language TEXT DEFAULT 'Python',
                source_model TEXT DEFAULT 'gemini',
                passed INTEGER DEFAULT -1,
                created_at TEXT NOT NULL,
                updated_at TEXT
            );
            
            CREATE TABLE IF NOT EXISTS learning_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                details TEXT,
                created_at TEXT NOT NULL
            );
            
            CREATE INDEX IF NOT EXISTS idx_solutions_name 
                ON solutions(problem_name);
            CREATE INDEX IF NOT EXISTS idx_solutions_tags 
                ON solutions(tags);
        """)
        self._conn.commit()

    # ═══════════════════════════════════════════════════════════
    # SAVE
    # ═══════════════════════════════════════════════════════════

    def save_solution(
        self,
        problem_name: str,
        problem_text: str,
        solution_code: str,
        approach: str = "",
        complexity: str = "",
        language: str = "Python",
        source_model: str = "gemini",
        difficulty: str = "unknown",
    ) -> int:
        """
        Save a solved problem to the database.
        Auto-detects tags from the problem text.
        Returns the solution ID.
        """
        tags = self.detect_tags(problem_text)
        now = datetime.now().isoformat()

        # Check for duplicate (same problem name)
        existing = self._conn.execute(
            "SELECT id FROM solutions WHERE problem_name = ? AND language = ?",
            (problem_name.lower().strip(), language),
        ).fetchone()

        if existing:
            # Update existing solution (might be a better one)
            self._conn.execute(
                """UPDATE solutions SET 
                    solution_code = ?, approach = ?, complexity = ?,
                    source_model = ?, tags = ?, updated_at = ?
                   WHERE id = ?""",
                (solution_code, approach, complexity, source_model,
                 json.dumps(tags), now, existing["id"]),
            )
            self._conn.commit()
            log.info(f"📝 Updated existing solution: {problem_name}")

            self._log_event("solution_updated", f"{problem_name} ({source_model})")
            return existing["id"]
        else:
            cursor = self._conn.execute(
                """INSERT INTO solutions 
                    (problem_name, problem_text, difficulty, tags, approach, 
                     complexity, solution_code, language, source_model, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (problem_name.lower().strip(), problem_text, difficulty,
                 json.dumps(tags), approach, complexity, solution_code,
                 language, source_model, now),
            )
            self._conn.commit()
            sol_id = cursor.lastrowid
            log.info(f"🧠 Learned new problem: {problem_name} (#{sol_id}, tags: {tags})")

            self._log_event("solution_saved", f"{problem_name} (#{sol_id}, {source_model})")
            return sol_id

    # ═══════════════════════════════════════════════════════════
    # RECALL
    # ═══════════════════════════════════════════════════════════

    def find_exact(self, problem_name: str, language: str = "Python"):
        """Find an exact match by problem name."""
        row = self._conn.execute(
            "SELECT * FROM solutions WHERE problem_name = ? AND language = ?",
            (problem_name.lower().strip(), language),
        ).fetchone()
        return dict(row) if row else None

    def find_by_tags(self, tags: list, top_k: int = 5) -> list:
        """Find problems that share the most tags with the given list."""
        if not tags:
            return []

        all_solutions = self._conn.execute(
            "SELECT * FROM solutions ORDER BY created_at DESC"
        ).fetchall()

        scored = []
        for row in all_solutions:
            row_tags = json.loads(row["tags"]) if row["tags"] else []
            overlap = len(set(tags) & set(row_tags))
            if overlap > 0:
                scored.append((overlap, dict(row)))

        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[:top_k]

    def find_similar_text(self, problem_text: str, top_k: int = 3) -> list:
        """
        Find similar problems using keyword overlap.
        Simple but effective — no ML model needed.
        """
        # Extract key words from the problem
        words = set(re.findall(r'\b[a-z]{3,}\b', problem_text.lower()))
        # Remove common English words
        stop_words = {
            'the', 'and', 'for', 'are', 'but', 'not', 'you', 'all',
            'can', 'has', 'her', 'was', 'one', 'our', 'out', 'get',
            'with', 'that', 'this', 'from', 'they', 'been', 'have',
            'each', 'which', 'their', 'will', 'other', 'about',
            'given', 'return', 'input', 'output', 'example',
            'integer', 'number', 'value', 'where', 'such',
        }
        keywords = words - stop_words

        if not keywords:
            return []

        all_solutions = self._conn.execute(
            "SELECT * FROM solutions ORDER BY created_at DESC"
        ).fetchall()

        scored = []
        for row in all_solutions:
            row_text = (row["problem_name"] + " " + (row["problem_text"] or "")).lower()
            row_words = set(re.findall(r'\b[a-z]{3,}\b', row_text))
            overlap = len(keywords & row_words)
            similarity = overlap / max(len(keywords), 1)
            if similarity > 0.15:  # At least 15% keyword overlap
                scored.append((similarity, dict(row)))

        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[:top_k]

    # ═══════════════════════════════════════════════════════════
    # TAG DETECTION
    # ═══════════════════════════════════════════════════════════

    def detect_tags(self, text: str) -> list:
        """Auto-detect DSA tags from problem text."""
        if not text:
            return []
        text_lower = text.lower()
        detected = []
        for tag, pattern in _TAG_PATTERNS.items():
            if re.search(pattern, text_lower, re.IGNORECASE):
                detected.append(tag)
        return detected

    # ═══════════════════════════════════════════════════════════
    # STATS
    # ═══════════════════════════════════════════════════════════

    def mark_passed(self, problem_name: str, passed: bool = True):
        """Mark whether a solution passed on the platform."""
        self._conn.execute(
            "UPDATE solutions SET passed = ? WHERE problem_name = ?",
            (1 if passed else 0, problem_name.lower().strip()),
        )
        self._conn.commit()

    def get_stats(self) -> str:
        """Human-readable stats summary."""
        total = self._count()
        if total == 0:
            return "No problems solved yet. Say 'solve this' on a LeetCode problem!"

        passed = self._conn.execute(
            "SELECT COUNT(*) FROM solutions WHERE passed = 1"
        ).fetchone()[0]
        
        # Count by difficulty
        easy = self._conn.execute(
            "SELECT COUNT(*) FROM solutions WHERE difficulty = 'easy'"
        ).fetchone()[0]
        medium = self._conn.execute(
            "SELECT COUNT(*) FROM solutions WHERE difficulty = 'medium'"
        ).fetchone()[0]
        hard = self._conn.execute(
            "SELECT COUNT(*) FROM solutions WHERE difficulty = 'hard'"
        ).fetchone()[0]

        # Most common tags
        all_tags = []
        for row in self._conn.execute("SELECT tags FROM solutions").fetchall():
            all_tags.extend(json.loads(row[0]) if row[0] else [])
        tag_counts = {}
        for t in all_tags:
            tag_counts[t] = tag_counts.get(t, 0) + 1
        top_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        tag_str = ", ".join(f"{t}({c})" for t, c in top_tags) if top_tags else "none yet"

        parts = [f"I've solved {total} problems total."]
        if easy or medium or hard:
            parts.append(f"{easy} easy, {medium} medium, {hard} hard.")
        if passed > 0:
            parts.append(f"{passed} confirmed passed on the platform.")
        parts.append(f"Top topics: {tag_str}.")
        
        return " ".join(parts)

    def get_recent(self, n: int = 5) -> list:
        """Get N most recently solved problems."""
        rows = self._conn.execute(
            "SELECT problem_name, approach, complexity, language, source_model, created_at "
            "FROM solutions ORDER BY created_at DESC LIMIT ?",
            (n,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ═══════════════════════════════════════════════════════════
    # EXPORT FOR TRAINING (Phase 3 prep)
    # ═══════════════════════════════════════════════════════════

    def export_training_data(self, output_path: str = None) -> str:
        """
        Export all solved problems as JSONL for fine-tuning.
        Format: {"prompt": "Solve...", "completion": "code..."}
        """
        if output_path is None:
            output_path = str(_DB_DIR / "training_data.jsonl")

        rows = self._conn.execute(
            "SELECT * FROM solutions WHERE passed != 0 ORDER BY created_at"
        ).fetchall()

        count = 0
        with open(output_path, "w", encoding="utf-8") as f:
            for row in rows:
                entry = {
                    "prompt": (
                        f"Solve this coding problem in {row['language']}:\n\n"
                        f"{row['problem_text'] or row['problem_name']}"
                    ),
                    "completion": (
                        f"APPROACH: {row['approach']}\n"
                        f"COMPLEXITY: {row['complexity']}\n\n"
                        f"```{row['language'].lower()}\n"
                        f"{row['solution_code']}\n"
                        f"```"
                    ),
                    "tags": json.loads(row["tags"]) if row["tags"] else [],
                    "difficulty": row["difficulty"],
                }
                f.write(json.dumps(entry) + "\n")
                count += 1

        log.info(f"📦 Exported {count} solutions to {output_path}")
        return f"Exported {count} solutions to {output_path}"

    # ═══════════════════════════════════════════════════════════
    # INTERNALS
    # ═══════════════════════════════════════════════════════════

    def _count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM solutions").fetchone()[0]

    def _log_event(self, event_type: str, details: str):
        self._conn.execute(
            "INSERT INTO learning_log (event_type, details, created_at) VALUES (?, ?, ?)",
            (event_type, details, datetime.now().isoformat()),
        )
        self._conn.commit()

    def close(self):
        self._conn.close()


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    mem = CodeMemory()
    print(mem.get_stats())

    # Test save
    sid = mem.save_solution(
        problem_name="Two Sum",
        problem_text="Given an array of integers nums and an integer target, return indices of the two numbers such that they add up to target.",
        solution_code="class Solution:\n    def twoSum(self, nums, target):\n        seen = {}\n        for i, n in enumerate(nums):\n            if target - n in seen:\n                return [seen[target-n], i]\n            seen[n] = i",
        approach="Hash map for O(1) lookup of complement",
        complexity="Time O(n), Space O(n)",
        source_model="gemini-2.5-flash",
        difficulty="easy",
    )
    print(f"Saved as #{sid}")
    print(mem.get_stats())

    # Test find
    similar = mem.find_similar_text("find two numbers in array that sum to target")
    print(f"Similar: {[s[1]['problem_name'] for s in similar]}")

    tags = mem.detect_tags("Given a binary tree, find the maximum depth")
    print(f"Tags: {tags}")

    mem.close()
