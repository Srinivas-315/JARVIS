"""
JARVIS — skills/knowledge_base.py
Knowledge Base Skill — Voice commands for the RAG pipeline.

Lets the user ingest files/folders and query documents via voice:
  - "Learn this file notes.pdf"
  - "Learn my notes folder"
  - "Search my documents for transformers"
  - "What do my notes say about neural networks?"
  - "How many documents do you know?"
  - "Forget all documents"

Usage:
    from skills.knowledge_base import KnowledgeBaseSkill
    kb = KnowledgeBaseSkill()
    response = kb.handle("learn this file README.md")
"""

import os
import re
from pathlib import Path

from utils.logger import log

# Lazy-load RAG engine (heavy import)
_rag_engine = None


def _get_rag():
    """Lazy-load the RAG engine."""
    global _rag_engine
    if _rag_engine is None:
        try:
            from brain.rag_engine import RAGEngine
            _rag_engine = RAGEngine()
            if _rag_engine.is_ready:
                log.info("KnowledgeBase: RAG engine loaded ✅")
            else:
                log.warning("KnowledgeBase: RAG engine failed to initialize")
        except Exception as e:
            log.warning(f"KnowledgeBase: Could not load RAG engine: {e}")
            return None
    return _rag_engine


# ── Common user directories ─────────────────────────────────
HOME = Path.home()
DESKTOP = HOME / "OneDrive" / "Attachments" / "Desktop"
if not DESKTOP.exists():
    DESKTOP = HOME / "Desktop"
DOCUMENTS = HOME / "Documents"
DOWNLOADS = HOME / "Downloads"

# Shortcut aliases for voice commands
FOLDER_ALIASES = {
    "desktop": str(DESKTOP),
    "documents": str(DOCUMENTS),
    "downloads": str(DOWNLOADS),
    "notes": str(DOCUMENTS / "Notes"),
    "projects": str(DESKTOP / "PROJECTS"),
}


class KnowledgeBaseSkill:
    """
    JARVIS skill for managing the knowledge base via voice commands.
    """

    def __init__(self):
        self._rag = None  # Will be lazy-loaded on first use

    def _ensure_rag(self):
        """Ensure RAG engine is loaded."""
        if self._rag is None:
            self._rag = _get_rag()
        return self._rag is not None and self._rag.is_ready

    # ── Main handler — routes to sub-commands ────────────────
    def handle(self, command: str) -> str:
        """
        Handle a knowledge base voice command.

        Args:
            command: User's voice command (already classified as knowledge_base intent)

        Returns:
            JARVIS response string
        """
        cmd = command.lower().strip()

        # Route to the right sub-handler
        if any(kw in cmd for kw in ["learn this file", "ingest file", "add file",
                                      "learn file", "read file", "memorize file"]):
            return self._handle_ingest_file(command)

        elif any(kw in cmd for kw in ["learn folder", "learn my", "ingest folder",
                                        "learn directory", "scan folder",
                                        "learn the", "read folder"]):
            return self._handle_ingest_folder(command)

        elif any(kw in cmd for kw in ["search my documents", "search documents",
                                        "search my files", "find in documents",
                                        "search knowledge", "look up"]):
            return self._handle_search(command)

        elif any(kw in cmd for kw in ["what do my", "from my documents",
                                        "from my notes", "from my files",
                                        "in my documents", "according to my",
                                        "based on my"]):
            return self._handle_ask(command)

        elif any(kw in cmd for kw in ["how many documents", "knowledge base stats",
                                        "what do you know", "kb stats",
                                        "document stats"]):
            return self._handle_stats()

        elif any(kw in cmd for kw in ["forget all documents", "clear knowledge",
                                        "reset knowledge", "clear documents",
                                        "forget documents"]):
            return self._handle_clear()

        elif any(kw in cmd for kw in ["forget file", "remove file",
                                        "delete file from"]):
            return self._handle_delete_file(command)

        else:
            # Default: treat as a knowledge base question
            return self._handle_ask(command)

    # ── Ingest a single file ─────────────────────────────────
    def _handle_ingest_file(self, command: str) -> str:
        """Handle: 'learn this file notes.pdf'"""
        if not self._ensure_rag():
            return "I'm sorry sir, the knowledge base system isn't ready. Please check the installation."

        # Extract file path from command
        file_path = self._extract_file_path(command)
        if not file_path:
            return "I couldn't determine which file to learn, sir. Could you specify the file name or path?"

        # Check if file exists
        resolved = self._resolve_file_path(file_path)
        if not resolved:
            return f"I couldn't find the file '{file_path}', sir. Please check the path."

        result = self._rag.ingest_file(resolved)

        if result["status"] == "success":
            return (
                f"Done, sir. I've learned '{Path(resolved).name}' — "
                f"stored as {result['chunks']} knowledge chunks. "
                f"I can now answer questions about this file."
            )
        elif result["status"] == "skipped":
            return (
                f"I've already learned '{Path(resolved).name}', sir. "
                f"Say 'learn this file again' if you want me to re-read it."
            )
        else:
            return f"I had trouble reading that file, sir: {result.get('message', 'unknown error')}"

    # ── Ingest a folder ──────────────────────────────────────
    def _handle_ingest_folder(self, command: str) -> str:
        """Handle: 'learn my notes folder'"""
        if not self._ensure_rag():
            return "The knowledge base system isn't ready, sir."

        # Extract folder path
        folder_path = self._extract_folder_path(command)
        if not folder_path:
            return (
                "Which folder should I learn, sir? You can say things like:\n"
                "• 'Learn my desktop folder'\n"
                "• 'Learn my documents folder'\n"
                "• 'Learn my notes folder'\n"
                "• 'Learn folder C:/path/to/folder'"
            )

        if not os.path.isdir(folder_path):
            return f"I couldn't find that folder, sir: '{folder_path}'"

        result = self._rag.ingest_folder(folder_path)

        if result["status"] == "success":
            total = result["files_processed"]
            chunks = result["total_chunks"]
            skipped = result["skipped"]
            errors = result["errors"]

            response = f"Done, sir! I've learned {total} files ({chunks} knowledge chunks)"
            if skipped > 0:
                response += f", skipped {skipped} already-known files"
            if errors > 0:
                response += f", and had {errors} files I couldn't read"
            response += ". I'm now smarter about this folder's contents."
            return response
        else:
            return f"I had trouble with that folder, sir: {result.get('message', 'unknown error')}"

    # ── Search documents ─────────────────────────────────────
    def _handle_search(self, command: str) -> str:
        """Handle: 'search my documents for transformers'"""
        if not self._ensure_rag():
            return "The knowledge base system isn't ready, sir."

        # Extract search query
        query = self._extract_query(command, search_mode=True)
        if not query:
            return "What should I search for in your documents, sir?"

        results = self._rag.query(query, top_k=5)

        if not results:
            return f"I couldn't find anything about '{query}' in your documents, sir."

        response_parts = [f"Here's what I found about '{query}' in your documents, sir:\n"]
        for i, r in enumerate(results[:3], 1):
            preview = r["text"][:150].replace("\n", " ").strip()
            source = r["source"]
            score = r["score"]
            response_parts.append(
                f"{i}. From '{source}' ({score:.0%} match): {preview}..."
            )

        return "\n".join(response_parts)

    # ── Ask a question (RAG-powered Q&A) ─────────────────────
    def _handle_ask(self, command: str) -> str:
        """
        Handle: 'what do my notes say about neural networks?'
        Returns the RAG context — the actual Gemini-powered answer
        will come from gemini_handler.py using this context.
        """
        if not self._ensure_rag():
            return ""  # Return empty = let Gemini handle without RAG context

        query = self._extract_query(command, search_mode=False)
        if not query:
            return ""

        context = self._rag.get_context_for_prompt(query, top_k=5)
        return context  # This gets injected into the Gemini prompt

    # ── Stats ────────────────────────────────────────────────
    def _handle_stats(self) -> str:
        """Handle: 'how many documents do you know?'"""
        if not self._ensure_rag():
            return "The knowledge base system isn't ready, sir."

        stats = self._rag.get_stats()
        chunks = stats["total_chunks"]
        files = stats["total_files"]

        if chunks == 0:
            return (
                "My knowledge base is empty, sir. "
                "You can say 'learn my documents folder' or "
                "'learn this file notes.pdf' to teach me."
            )

        response = f"I currently know {chunks} knowledge chunks from {files} files, sir.\n"
        if stats.get("files"):
            response += "Recent files:\n"
            for f in stats["files"][:5]:
                response += f"  • {f['name']} ({f['chunks']} chunks, {f['size_kb']} KB)\n"

        return response.strip()

    # ── Clear ────────────────────────────────────────────────
    def _handle_clear(self) -> str:
        """Handle: 'forget all documents'"""
        if not self._ensure_rag():
            return "The knowledge base system isn't ready, sir."

        success = self._rag.clear()
        if success:
            return "Done, sir. I've cleared my entire knowledge base. My document memory is reset."
        else:
            return "I had trouble clearing the knowledge base, sir."

    # ── Delete specific file ─────────────────────────────────
    def _handle_delete_file(self, command: str) -> str:
        """Handle: 'forget file notes.pdf'"""
        if not self._ensure_rag():
            return "The knowledge base system isn't ready, sir."

        file_path = self._extract_file_path(command)
        if not file_path:
            return "Which file should I forget, sir?"

        resolved = self._resolve_file_path(file_path)
        if resolved:
            success = self._rag.delete_file(resolved)
        else:
            # Try with the raw name
            success = self._rag.delete_file(file_path)

        if success:
            return f"Done, sir. I've forgotten everything from '{Path(file_path).name}'."
        else:
            return f"I couldn't find '{file_path}' in my knowledge base, sir."

    # ═══════════════════════════════════════════════════════════
    #  Helper methods — extract file paths and queries
    # ═══════════════════════════════════════════════════════════

    def _extract_file_path(self, command: str) -> str:
        """Extract a file path from a voice command."""
        # Patterns to try
        patterns = [
            r'(?:learn|ingest|add|read|memorize|forget|remove|delete)\s+(?:this\s+)?file\s+(.+)',
            r'file[:\s]+(.+)',
            r'(?:learn|read)\s+(.+?\.\w{2,5})',  # Match filename with extension
        ]

        for pattern in patterns:
            match = re.search(pattern, command, re.IGNORECASE)
            if match:
                path = match.group(1).strip().strip('"\'')
                # Remove trailing phrases like "for me" or "please"
                path = re.sub(r'\s+(for me|please|sir|again)$', '', path, flags=re.IGNORECASE)
                return path

        return ""

    def _extract_folder_path(self, command: str) -> str:
        """Extract a folder path from a voice command."""
        cmd = command.lower().strip()

        # Check for folder aliases
        for alias, path in FOLDER_ALIASES.items():
            if alias in cmd:
                if os.path.isdir(path):
                    return path

        # Try to extract explicit path
        patterns = [
            r'(?:learn|ingest|scan|read)\s+(?:my\s+)?(?:the\s+)?folder\s+(.+)',
            r'(?:learn|ingest|scan|read)\s+(?:the\s+)?directory\s+(.+)',
            r'folder[:\s]+(.+)',
        ]

        for pattern in patterns:
            match = re.search(pattern, command, re.IGNORECASE)
            if match:
                path = match.group(1).strip().strip('"\'')
                path = re.sub(r'\s+(for me|please|sir)$', '', path, flags=re.IGNORECASE)
                if os.path.isdir(path):
                    return path

        return ""

    def _extract_query(self, command: str, search_mode: bool = False) -> str:
        """Extract the search query from a voice command."""
        cmd = command.strip()

        if search_mode:
            # Extract query after "search ... for" or "find ... about"
            patterns = [
                r'(?:search|find|look up).*?(?:for|about)\s+(.+)',
                r'(?:search|find|look up)\s+(.+)',
            ]
        else:
            # Extract the actual question
            patterns = [
                r'(?:what do my|from my|in my|according to my|based on my)\s+\w+\s+(?:say|mention|note|explain|describe)\s+(?:about\s+)?(.+)',
                r'(?:what do my|from my)\s+\w+\s+(.+)',
                r'(?:about|regarding|on)\s+(.+)',
            ]

        for pattern in patterns:
            match = re.search(pattern, cmd, re.IGNORECASE)
            if match:
                query = match.group(1).strip()
                # Clean trailing words
                query = re.sub(r'\s*\?$', '', query)
                query = re.sub(r'\s+(sir|please)$', '', query, flags=re.IGNORECASE)
                if len(query) > 3:
                    return query

        # Fallback: use the whole command as query (stripped of common prefixes)
        fallback = re.sub(
            r'^(search|find|look up|what|how|tell me|explain)\s+',
            '', cmd, flags=re.IGNORECASE
        ).strip()
        if len(fallback) > 3:
            return fallback

        return ""

    def _resolve_file_path(self, file_path: str) -> str:
        """Try to resolve a file path, checking common locations."""
        # Try as-is first
        if os.path.isfile(file_path):
            return str(Path(file_path).resolve())

        # Try common locations
        search_dirs = [
            Path.cwd(),
            DESKTOP,
            DOCUMENTS,
            DOWNLOADS,
            DESKTOP / "PROJECTS",
            DESKTOP / "PROJECTS" / "JARVIS",
        ]

        for directory in search_dirs:
            candidate = directory / file_path
            if candidate.is_file():
                return str(candidate.resolve())

        return ""


# ═══════════════════════════════════════════════════════════════
#  Quick Test
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("=" * 55)
    print("  JARVIS Knowledge Base Skill — Test")
    print("=" * 55)

    kb = KnowledgeBaseSkill()

    # Test 1: Ingest a file
    print("\n1. Testing: 'learn this file README.md'")
    response = kb.handle("learn this file README.md")
    print(f"   → {response}")

    # Test 2: Search
    print("\n2. Testing: 'search my documents for voice commands'")
    response = kb.handle("search my documents for voice commands")
    print(f"   → {response}")

    # Test 3: Stats
    print("\n3. Testing: 'how many documents do you know'")
    response = kb.handle("how many documents do you know")
    print(f"   → {response}")

    # Test 4: Ask
    print("\n4. Testing: 'what do my notes say about API keys'")
    response = kb.handle("what do my notes say about API keys")
    if response:
        print(f"   → {response[:300]}...")
    else:
        print("   → (empty — would use Gemini)")

    print("\n✅ Knowledge Base Skill working!")
