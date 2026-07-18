"""
JARVIS — brain/rag_engine.py
RAG (Retrieval-Augmented Generation) Pipeline — JARVIS becomes truly intelligent.

Ingests documents (PDFs, text, code, notes) → chunks them → embeds → stores
in ChromaDB → retrieves relevant context for every Gemini API call.

This makes JARVIS answer from YOUR actual files, not just generic knowledge.

Usage:
    from brain.rag_engine import RAGEngine
    rag = RAGEngine()
    rag.ingest_file("notes/ml_lecture.pdf")
    rag.ingest_folder("C:/Users/srini/Notes/")
    context = rag.get_context_for_prompt("explain transformers")

Supported formats: .pdf, .txt, .py, .md, .json, .csv, .log, .html, .docx
"""

import hashlib
import json
import os
import re
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np

from utils.logger import log

# ── Paths ────────────────────────────────────────────────────
ROOT_DIR = Path(__file__).parent.parent
DATA_DIR = ROOT_DIR / "data"
RAG_DB_DIR = DATA_DIR / "rag_db"
RAG_META_DB = DATA_DIR / "rag_metadata.db"

# ── Embedding model (shared with vector_memory.py) ───────────
_embed_model = None
_EMBED_DIM = 384  # all-MiniLM-L6-v2 output dimension


def _get_embed_model():
    """Lazy-load the sentence-transformer model (shared with vector_memory)."""
    global _embed_model
    if _embed_model is None:
        try:
            from sentence_transformers import SentenceTransformer
            start = time.time()
            _embed_model = SentenceTransformer("all-MiniLM-L6-v2")
            elapsed = (time.time() - start) * 1000
            log.info(f"RAG: embedding model loaded ({elapsed:.0f}ms)")
        except ImportError:
            log.warning(
                "RAG: sentence-transformers not installed. "
                "Run: pip install sentence-transformers"
            )
            return None
        except Exception as e:
            log.warning(f"RAG: embedding model load failed: {e}")
            return None
    return _embed_model


# ═══════════════════════════════════════════════════════════════
#  Document Loader — reads various file formats
# ═══════════════════════════════════════════════════════════════
class DocumentLoader:
    """
    Loads text content from various file formats.
    Handles: PDF, TXT, PY, MD, JSON, CSV, LOG, HTML
    """

    SUPPORTED_EXTENSIONS = {
        ".pdf", ".txt", ".py", ".md", ".json", ".csv",
        ".log", ".html", ".htm", ".js", ".ts", ".java",
        ".c", ".cpp", ".h", ".css", ".yaml", ".yml",
        ".toml", ".ini", ".cfg", ".bat", ".ps1", ".sh",
        ".sql", ".xml", ".rst", ".tex",
    }

    @staticmethod
    def load(file_path: str) -> Optional[str]:
        """
        Load text content from a file.

        Args:
            file_path: Path to the file

        Returns:
            Text content or None if failed
        """
        path = Path(file_path)
        if not path.exists():
            log.warning(f"RAG: File not found: {file_path}")
            return None

        ext = path.suffix.lower()

        if ext not in DocumentLoader.SUPPORTED_EXTENSIONS:
            log.info(f"RAG: Unsupported file type: {ext}")
            return None

        try:
            if ext == ".pdf":
                return DocumentLoader._load_pdf(path)
            elif ext == ".json":
                return DocumentLoader._load_json(path)
            elif ext == ".html" or ext == ".htm":
                return DocumentLoader._load_html(path)
            else:
                # Plain text files (txt, py, md, csv, log, code files)
                return DocumentLoader._load_text(path)
        except Exception as e:
            log.warning(f"RAG: Error loading {file_path}: {e}")
            return None

    @staticmethod
    def _load_pdf(path: Path) -> Optional[str]:
        """Load PDF using PyPDF2 (fallback to pdfplumber)."""
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(str(path))
            pages = []
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    pages.append(text.strip())
            content = "\n\n".join(pages)
            if content.strip():
                return content
        except ImportError:
            pass
        except Exception as e:
            log.debug(f"PyPDF2 failed for {path}: {e}")

        # Fallback to pdfplumber (already in requirements.txt)
        try:
            import pdfplumber
            with pdfplumber.open(str(path)) as pdf:
                pages = []
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        pages.append(text.strip())
                content = "\n\n".join(pages)
                if content.strip():
                    return content
        except ImportError:
            log.warning("RAG: Neither PyPDF2 nor pdfplumber available for PDFs")
        except Exception as e:
            log.debug(f"pdfplumber failed for {path}: {e}")

        return None

    @staticmethod
    def _load_json(path: Path) -> Optional[str]:
        """Load JSON and convert to readable text."""
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            data = json.load(f)
        return json.dumps(data, indent=2, ensure_ascii=False)

    @staticmethod
    def _load_html(path: Path) -> Optional[str]:
        """Load HTML and strip tags."""
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            html = f.read()
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
            return soup.get_text(separator="\n", strip=True)
        except ImportError:
            # Simple regex fallback
            clean = re.sub(r'<[^>]+>', ' ', html)
            clean = re.sub(r'\s+', ' ', clean).strip()
            return clean

    @staticmethod
    def _load_text(path: Path) -> Optional[str]:
        """Load plain text file."""
        # Limit file size to 10MB
        if path.stat().st_size > 10 * 1024 * 1024:
            log.warning(f"RAG: File too large (>10MB): {path}")
            return None
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()


# ═══════════════════════════════════════════════════════════════
#  Text Chunker — splits documents into overlapping chunks
# ═══════════════════════════════════════════════════════════════
class TextChunker:
    """
    Splits text into chunks for embedding.
    Uses sentence-aware splitting with overlap for context preservation.
    """

    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 50):
        """
        Args:
            chunk_size: Target characters per chunk (~125 tokens)
            chunk_overlap: Overlap between chunks for context
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk(self, text: str, source: str = "") -> list[dict]:
        """
        Split text into overlapping chunks.

        Args:
            text: Full document text
            source: Source file path/name for metadata

        Returns:
            List of {"text": str, "source": str, "chunk_index": int}
        """
        if not text or len(text.strip()) < 20:
            return []

        # Clean the text
        text = self._clean_text(text)

        # Split into sentences first
        sentences = self._split_sentences(text)

        # Group sentences into chunks
        chunks = []
        current_chunk = []
        current_length = 0

        for sentence in sentences:
            sentence_len = len(sentence)

            if current_length + sentence_len > self.chunk_size and current_chunk:
                # Save current chunk
                chunk_text = " ".join(current_chunk)
                chunks.append({
                    "text": chunk_text,
                    "source": source,
                    "chunk_index": len(chunks),
                })

                # Keep overlap — last few sentences
                overlap_text = ""
                overlap_sentences = []
                for s in reversed(current_chunk):
                    if len(overlap_text) + len(s) > self.chunk_overlap:
                        break
                    overlap_sentences.insert(0, s)
                    overlap_text = " ".join(overlap_sentences)

                current_chunk = overlap_sentences
                current_length = len(overlap_text)

            current_chunk.append(sentence)
            current_length += sentence_len

        # Don't forget the last chunk
        if current_chunk:
            chunk_text = " ".join(current_chunk)
            if len(chunk_text.strip()) > 20:  # Skip tiny trailing chunks
                chunks.append({
                    "text": chunk_text,
                    "source": source,
                    "chunk_index": len(chunks),
                })

        return chunks

    def _clean_text(self, text: str) -> str:
        """Clean text: normalize whitespace, remove junk."""
        # Replace tabs and multiple newlines
        text = re.sub(r'\t', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        # Remove excessive spaces
        text = re.sub(r' {3,}', ' ', text)
        return text.strip()

    def _split_sentences(self, text: str) -> list[str]:
        """Split text into sentences (handles code and regular text)."""
        # For code files, split by lines instead
        if any(kw in text[:200] for kw in ['def ', 'class ', 'import ', 'function ', '#include']):
            # Code: split by logical blocks (double newline or function boundaries)
            blocks = re.split(r'\n\n+', text)
            return [b.strip() for b in blocks if b.strip()]

        # Regular text: split by sentence boundaries
        sentences = re.split(r'(?<=[.!?])\s+', text)
        # Also split on double newlines (paragraph breaks)
        result = []
        for s in sentences:
            if '\n\n' in s:
                parts = s.split('\n\n')
                result.extend(p.strip() for p in parts if p.strip())
            else:
                if s.strip():
                    result.append(s.strip())
        return result


# ═══════════════════════════════════════════════════════════════
#  RAG Engine — the main pipeline
# ═══════════════════════════════════════════════════════════════
class RAGEngine:
    """
    Full RAG pipeline for JARVIS.

    Ingests documents → chunks → embeds → stores in ChromaDB.
    Retrieves relevant context for every Gemini API call.
    """

    # Collection name in ChromaDB
    COLLECTION_NAME = "jarvis_knowledge"

    def __init__(self):
        self._collection = None
        self._chunker = TextChunker(chunk_size=500, chunk_overlap=50)
        self._ready = False
        self._use_chromadb = False
        self._meta_db = None

        self._init_storage()
        self._init_metadata_db()

    def _init_storage(self):
        """Initialize ChromaDB or fallback to SQLite."""
        # Try ChromaDB first
        try:
            import chromadb
            RAG_DB_DIR.mkdir(parents=True, exist_ok=True)

            client = chromadb.PersistentClient(path=str(RAG_DB_DIR))
            self._collection = client.get_or_create_collection(
                name=self.COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"},
            )
            self._use_chromadb = True
            self._ready = True

            count = self._collection.count()
            log.info(f"RAG: ChromaDB ready ({count} chunks stored)")

        except ImportError:
            log.info("RAG: ChromaDB not installed, using SQLite fallback")
            self._init_sqlite_fallback()
        except Exception as e:
            log.warning(f"RAG: ChromaDB init failed ({e}), using SQLite fallback")
            self._init_sqlite_fallback()

    def _init_sqlite_fallback(self):
        """Fallback: use SQLite for vector storage (like vector_memory.py)."""
        try:
            db_path = DATA_DIR / "rag_vectors.db"
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(db_path))
            conn.execute("""
                CREATE TABLE IF NOT EXISTS rag_chunks (
                    id TEXT PRIMARY KEY,
                    text TEXT NOT NULL,
                    source TEXT NOT NULL,
                    chunk_index INTEGER,
                    embedding BLOB NOT NULL,
                    timestamp TEXT NOT NULL
                )
            """)
            conn.commit()
            conn.close()
            self._sqlite_path = str(db_path)
            self._use_chromadb = False
            self._ready = True
            log.info("RAG: SQLite fallback initialized")
        except Exception as e:
            log.warning(f"RAG: SQLite fallback failed: {e}")
            self._ready = False

    def _init_metadata_db(self):
        """Track which files have been ingested (for deduplication)."""
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            self._meta_db = sqlite3.connect(str(RAG_META_DB))
            self._meta_db.execute("""
                CREATE TABLE IF NOT EXISTS ingested_files (
                    file_path TEXT PRIMARY KEY,
                    file_hash TEXT NOT NULL,
                    chunk_count INTEGER,
                    ingested_at TEXT NOT NULL,
                    file_size INTEGER
                )
            """)
            self._meta_db.commit()
        except Exception as e:
            log.warning(f"RAG: Metadata DB init failed: {e}")

    @property
    def is_ready(self) -> bool:
        return self._ready

    # ── File hash for deduplication ───────────────────────────
    def _file_hash(self, file_path: str) -> str:
        """Generate MD5 hash of file for change detection."""
        h = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    def _is_already_ingested(self, file_path: str) -> bool:
        """Check if file has already been ingested (and hasn't changed)."""
        if not self._meta_db:
            return False
        try:
            row = self._meta_db.execute(
                "SELECT file_hash FROM ingested_files WHERE file_path = ?",
                (str(file_path),)
            ).fetchone()
            if row:
                current_hash = self._file_hash(str(file_path))
                return row[0] == current_hash  # Same hash = already ingested
            return False
        except Exception:
            return False

    def _record_ingestion(self, file_path: str, chunk_count: int):
        """Record that a file has been ingested."""
        if not self._meta_db:
            return
        try:
            path = Path(file_path)
            self._meta_db.execute(
                """INSERT OR REPLACE INTO ingested_files
                   (file_path, file_hash, chunk_count, ingested_at, file_size)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    str(file_path),
                    self._file_hash(str(file_path)),
                    chunk_count,
                    datetime.now().isoformat(),
                    path.stat().st_size if path.exists() else 0,
                )
            )
            self._meta_db.commit()
        except Exception as e:
            log.debug(f"RAG: Failed to record ingestion: {e}")

    # ── Ingest a single file ─────────────────────────────────
    def ingest_file(self, file_path: str, force: bool = False) -> dict:
        """
        Ingest a single file into the knowledge base.

        Args:
            file_path: Path to the file
            force: Re-ingest even if already in KB

        Returns:
            {"status": "success/skipped/error", "chunks": int, "file": str}
        """
        if not self._ready:
            return {"status": "error", "message": "RAG engine not initialized"}

        file_path = str(Path(file_path).resolve())

        # Check if already ingested
        if not force and self._is_already_ingested(file_path):
            log.info(f"RAG: Already ingested (skipping): {Path(file_path).name}")
            return {"status": "skipped", "chunks": 0, "file": file_path}

        # Load document
        content = DocumentLoader.load(file_path)
        if not content:
            return {"status": "error", "message": f"Could not load: {file_path}"}

        # Chunk the document
        source_name = Path(file_path).name
        chunks = self._chunker.chunk(content, source=source_name)
        if not chunks:
            return {"status": "error", "message": "No chunks generated"}

        # Get embedding model
        model = _get_embed_model()
        if model is None:
            return {"status": "error", "message": "Embedding model not available"}

        # Embed and store
        try:
            texts = [c["text"] for c in chunks]
            embeddings = model.encode(texts, normalize_embeddings=True,
                                      show_progress_bar=False)

            if self._use_chromadb:
                # Store in ChromaDB
                ids = [
                    f"{hashlib.md5(file_path.encode()).hexdigest()}_{i}"
                    for i in range(len(chunks))
                ]
                metadatas = [
                    {
                        "source": c["source"],
                        "chunk_index": c["chunk_index"],
                        "file_path": file_path,
                        "ingested_at": datetime.now().isoformat(),
                    }
                    for c in chunks
                ]

                # Delete old chunks from this file (re-ingest)
                file_hash = hashlib.md5(file_path.encode()).hexdigest()
                try:
                    existing = self._collection.get(
                        where={"file_path": file_path}
                    )
                    if existing and existing["ids"]:
                        self._collection.delete(ids=existing["ids"])
                except Exception:
                    pass

                self._collection.add(
                    ids=ids,
                    documents=texts,
                    embeddings=embeddings.tolist(),
                    metadatas=metadatas,
                )
            else:
                # SQLite fallback
                conn = sqlite3.connect(self._sqlite_path)
                # Delete old chunks from this file
                conn.execute(
                    "DELETE FROM rag_chunks WHERE source = ?",
                    (source_name,)
                )
                for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
                    chunk_id = f"{hashlib.md5(file_path.encode()).hexdigest()}_{i}"
                    conn.execute(
                        """INSERT OR REPLACE INTO rag_chunks
                           (id, text, source, chunk_index, embedding, timestamp)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (
                            chunk_id,
                            chunk["text"],
                            source_name,
                            i,
                            emb.astype(np.float32).tobytes(),
                            datetime.now().isoformat(),
                        )
                    )
                conn.commit()
                conn.close()

            # Record ingestion
            self._record_ingestion(file_path, len(chunks))

            log.info(
                f"RAG: Ingested '{source_name}' → {len(chunks)} chunks"
            )
            return {
                "status": "success",
                "chunks": len(chunks),
                "file": file_path,
            }

        except Exception as e:
            log.error(f"RAG: Ingest error: {e}")
            return {"status": "error", "message": str(e)}

    # ── Ingest an entire folder ──────────────────────────────
    def ingest_folder(self, folder_path: str, recursive: bool = True,
                      force: bool = False) -> dict:
        """
        Ingest all supported files from a folder.

        Args:
            folder_path: Path to the folder
            recursive: Search subdirectories too
            force: Re-ingest even if already in KB

        Returns:
            {"status": str, "files_processed": int, "total_chunks": int,
             "skipped": int, "errors": int}
        """
        if not self._ready:
            return {"status": "error", "message": "RAG engine not initialized"}

        folder = Path(folder_path)
        if not folder.exists() or not folder.is_dir():
            return {"status": "error", "message": f"Folder not found: {folder_path}"}

        results = {
            "status": "success",
            "files_processed": 0,
            "total_chunks": 0,
            "skipped": 0,
            "errors": 0,
        }

        # Find all supported files
        pattern = "**/*" if recursive else "*"
        for file_path in folder.glob(pattern):
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() not in DocumentLoader.SUPPORTED_EXTENSIONS:
                continue
            # Skip hidden files and __pycache__
            if any(part.startswith('.') or part == '__pycache__'
                   for part in file_path.parts):
                continue

            result = self.ingest_file(str(file_path), force=force)

            if result["status"] == "success":
                results["files_processed"] += 1
                results["total_chunks"] += result["chunks"]
            elif result["status"] == "skipped":
                results["skipped"] += 1
            else:
                results["errors"] += 1

        log.info(
            f"RAG: Folder ingestion complete — "
            f"{results['files_processed']} files, "
            f"{results['total_chunks']} chunks, "
            f"{results['skipped']} skipped"
        )
        return results

    # ── Query / Search ───────────────────────────────────────
    def query(self, query_text: str, top_k: int = 5,
              min_score: float = 0.25) -> list[dict]:
        """
        Search the knowledge base for relevant chunks.

        Args:
            query_text: Search query
            top_k: Max results to return
            min_score: Minimum similarity score (0-1)

        Returns:
            List of {"text": str, "source": str, "score": float}
        """
        if not self._ready:
            return []

        model = _get_embed_model()
        if model is None:
            return []

        try:
            if self._use_chromadb:
                return self._query_chromadb(query_text, model, top_k, min_score)
            else:
                return self._query_sqlite(query_text, model, top_k, min_score)
        except Exception as e:
            log.error(f"RAG: Query error: {e}")
            return []

    def _query_chromadb(self, query_text, model, top_k, min_score):
        """Query using ChromaDB."""
        query_embedding = model.encode(
            query_text, normalize_embeddings=True
        ).tolist()

        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )

        if not results["documents"] or not results["documents"][0]:
            return []

        output = []
        for doc, meta, distance in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            # ChromaDB returns cosine distance, convert to similarity
            score = 1 - distance
            if score >= min_score:
                output.append({
                    "text": doc,
                    "source": meta.get("source", "unknown"),
                    "score": round(score, 3),
                    "file_path": meta.get("file_path", ""),
                })

        return output

    def _query_sqlite(self, query_text, model, top_k, min_score):
        """Query using SQLite fallback (cosine similarity)."""
        query_embedding = model.encode(
            query_text, normalize_embeddings=True
        )

        conn = sqlite3.connect(self._sqlite_path)
        rows = conn.execute(
            "SELECT text, source, embedding FROM rag_chunks"
        ).fetchall()
        conn.close()

        if not rows:
            return []

        results = []
        for text, source, emb_blob in rows:
            stored_emb = np.frombuffer(emb_blob, dtype=np.float32)
            score = float(np.dot(query_embedding, stored_emb))
            if score >= min_score:
                results.append({
                    "text": text,
                    "source": source,
                    "score": round(score, 3),
                })

        results.sort(key=lambda x: -x["score"])
        return results[:top_k]

    # ── Context builder for Gemini prompts ───────────────────
    def get_context_for_prompt(self, query: str, top_k: int = 5,
                                min_score: float = 0.3) -> str:
        """
        Get formatted context string for injection into Gemini prompt.
        This is the key method that connects RAG to the AI brain.

        Args:
            query: Current user query
            top_k: Max chunks to include
            min_score: Minimum similarity threshold

        Returns:
            Formatted string of relevant document chunks
        """
        results = self.query(query, top_k=top_k, min_score=min_score)

        if not results:
            return ""

        lines = ["📚 Relevant information from your documents:"]
        for i, r in enumerate(results, 1):
            # Truncate very long chunks
            text = r["text"][:400]
            source = r["source"]
            score = r["score"]
            lines.append(f"\n[{i}] From '{source}' (relevance: {score:.0%}):")
            lines.append(f"  {text}")

        return "\n".join(lines)

    # ── Ingest raw text (for conversations, emails, etc.) ────
    def ingest_text(self, text: str, source: str,
                    metadata: dict = None) -> dict:
        """
        Ingest raw text directly (not from a file).
        Useful for ingesting conversations, emails, calendar entries.

        Args:
            text: Text content to ingest
            source: Label for the source (e.g. "email_2024_01_15")
            metadata: Optional extra metadata

        Returns:
            {"status": str, "chunks": int}
        """
        if not self._ready or not text or len(text.strip()) < 20:
            return {"status": "error", "chunks": 0}

        chunks = self._chunker.chunk(text, source=source)
        if not chunks:
            return {"status": "error", "chunks": 0}

        model = _get_embed_model()
        if model is None:
            return {"status": "error", "chunks": 0}

        try:
            texts = [c["text"] for c in chunks]
            embeddings = model.encode(texts, normalize_embeddings=True,
                                      show_progress_bar=False)

            if self._use_chromadb:
                ids = [
                    f"{hashlib.md5(source.encode()).hexdigest()}_{i}"
                    for i in range(len(chunks))
                ]
                metadatas = [
                    {
                        "source": source,
                        "chunk_index": c["chunk_index"],
                        "file_path": "",
                        "ingested_at": datetime.now().isoformat(),
                        **(metadata or {}),
                    }
                    for c in chunks
                ]
                try:
                    existing = self._collection.get(where={"source": source})
                    if existing and existing["ids"]:
                        self._collection.delete(ids=existing["ids"])
                except Exception:
                    pass

                self._collection.add(
                    ids=ids,
                    documents=texts,
                    embeddings=embeddings.tolist(),
                    metadatas=metadatas,
                )
            else:
                conn = sqlite3.connect(self._sqlite_path)
                for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
                    chunk_id = f"{hashlib.md5(source.encode()).hexdigest()}_{i}"
                    conn.execute(
                        """INSERT OR REPLACE INTO rag_chunks
                           (id, text, source, chunk_index, embedding, timestamp)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (
                            chunk_id,
                            chunk["text"],
                            source,
                            i,
                            emb.astype(np.float32).tobytes(),
                            datetime.now().isoformat(),
                        )
                    )
                conn.commit()
                conn.close()

            log.info(f"RAG: Ingested text '{source}' → {len(chunks)} chunks")
            return {"status": "success", "chunks": len(chunks)}

        except Exception as e:
            log.error(f"RAG: Text ingest error: {e}")
            return {"status": "error", "chunks": 0}

    # ── Auto-Ingest JARVIS Data ──────────────────────────────
    def auto_ingest_jarvis_data(self) -> dict:
        """
        Auto-ingest JARVIS's own data sources into the RAG knowledge base.
        Sources:
        - data/conversations.db (user & jarvis chats)
        - data/email_history.db (sent emails)
        - data/calendar.json (calendar events)
        - data/code_memory.db (code snippets)
        - data/personal_facts.json & user_memory.json
        """
        if not self._ready:
            return {"status": "error", "message": "RAG engine not initialized"}

        log.info("RAG: Starting auto-ingest of JARVIS data sources...")
        results = {"status": "success", "total_chunks": 0, "sources_processed": 0}

        def _process_text(text: str, source_name: str):
            if text and len(text.strip()) > 20:
                res = self.ingest_text(text, source=source_name)
                if res.get("status") == "success":
                    results["total_chunks"] += res.get("chunks", 0)
                    results["sources_processed"] += 1

        # 1. Conversations
        try:
            conv_db = DATA_DIR / "conversations.db"
            if conv_db.exists():
                conn = sqlite3.connect(str(conv_db))
                rows = conn.execute(
                    "SELECT timestamp, user_input, jarvis_response FROM conversations ORDER BY timestamp DESC LIMIT 500"
                ).fetchall()
                conn.close()
                if rows:
                    conv_text = "JARVIS PAST CONVERSATIONS:\n\n"
                    for ts, user_in, jarvis_res in rows:
                        conv_text += f"Time: {ts}\nUser: {user_in}\nJarvis: {jarvis_res}\n\n"
                    _process_text(conv_text, "JARVIS_Conversations")
        except Exception as e:
            log.warning(f"RAG: Failed to ingest conversations: {e}")

        # 2. Email History
        try:
            email_db = DATA_DIR / "email_history.db"
            if email_db.exists():
                conn = sqlite3.connect(str(email_db))
                rows = conn.execute(
                    "SELECT sent_at, recipient, email_addr, subject, body FROM sent_emails ORDER BY sent_at DESC LIMIT 100"
                ).fetchall()
                conn.close()
                if rows:
                    email_text = "JARVIS SENT EMAILS:\n\n"
                    for sent_at, rec, addr, subj, body in rows:
                        email_text += f"Date: {sent_at}\nTo: {rec} ({addr})\nSubject: {subj}\nBody: {body}\n\n"
                    _process_text(email_text, "JARVIS_Emails")
        except Exception as e:
            log.warning(f"RAG: Failed to ingest emails: {e}")

        # 3. Calendar Events
        try:
            cal_file = DATA_DIR / "calendar.json"
            if cal_file.exists():
                with open(cal_file, "r", encoding="utf-8") as f:
                    cal_data = json.load(f)
                if cal_data:
                    cal_text = "JARVIS CALENDAR EVENTS:\n\n" + json.dumps(cal_data, indent=2)
                    _process_text(cal_text, "JARVIS_Calendar")
        except Exception as e:
            log.warning(f"RAG: Failed to ingest calendar: {e}")

        # 4. Code Memory
        try:
            code_db = DATA_DIR / "code_memory.db"
            if code_db.exists():
                conn = sqlite3.connect(str(code_db))
                rows = conn.execute(
                    "SELECT problem_name, problem_text, approach, solution_code, language FROM solutions ORDER BY created_at DESC LIMIT 100"
                ).fetchall()
                conn.close()
                if rows:
                    code_text = "JARVIS CODE MEMORY & SOLUTIONS:\n\n"
                    for name, text, appr, code, lang in rows:
                        code_text += f"Problem: {name}\nDescription: {text}\nApproach: {appr}\nLanguage: {lang}\nCode:\n{code}\n\n"
                    _process_text(code_text, "JARVIS_Code_Memory")
        except Exception as e:
            log.warning(f"RAG: Failed to ingest code memory: {e}")

        # 5. Personal Facts & User Memory
        try:
            facts_text = "JARVIS PERSONAL FACTS & USER MEMORY:\n\n"
            has_facts = False
            for f_name in ["personal_facts.json", "user_memory.json", "jarvis_memory.json"]:
                f_path = DATA_DIR / f_name
                if f_path.exists():
                    with open(f_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if data:
                            facts_text += f"--- {f_name} ---\n" + json.dumps(data, indent=2) + "\n\n"
                            has_facts = True
            if has_facts:
                _process_text(facts_text, "JARVIS_Personal_Facts")
        except Exception as e:
            log.warning(f"RAG: Failed to ingest facts: {e}")

        log.info(f"RAG: Auto-ingest complete. Processed {results['sources_processed']} sources, {results['total_chunks']} chunks.")
        return results

    # ── Stats ────────────────────────────────────────────────
    def get_stats(self) -> dict:
        """Get knowledge base statistics."""
        stats = {
            "ready": self._ready,
            "backend": "chromadb" if self._use_chromadb else "sqlite",
            "total_chunks": 0,
            "total_files": 0,
            "files": [],
        }

        if not self._ready:
            return stats

        # Chunk count
        if self._use_chromadb:
            stats["total_chunks"] = self._collection.count()
        else:
            try:
                conn = sqlite3.connect(self._sqlite_path)
                count = conn.execute(
                    "SELECT COUNT(*) FROM rag_chunks"
                ).fetchone()[0]
                conn.close()
                stats["total_chunks"] = count
            except Exception:
                pass

        # Ingested files
        if self._meta_db:
            try:
                rows = self._meta_db.execute(
                    "SELECT file_path, chunk_count, ingested_at, file_size "
                    "FROM ingested_files ORDER BY ingested_at DESC"
                ).fetchall()
                stats["total_files"] = len(rows)
                stats["files"] = [
                    {
                        "path": r[0],
                        "name": Path(r[0]).name,
                        "chunks": r[1],
                        "ingested_at": r[2],
                        "size_kb": round(r[3] / 1024, 1) if r[3] else 0,
                    }
                    for r in rows[:20]  # Last 20 files
                ]
            except Exception:
                pass

        return stats

    # ── Clear knowledge base ─────────────────────────────────
    def clear(self) -> bool:
        """Clear all documents from the knowledge base."""
        try:
            if self._use_chromadb:
                import chromadb
                client = chromadb.PersistentClient(path=str(RAG_DB_DIR))
                client.delete_collection(self.COLLECTION_NAME)
                self._collection = client.get_or_create_collection(
                    name=self.COLLECTION_NAME,
                    metadata={"hnsw:space": "cosine"},
                )
            else:
                conn = sqlite3.connect(self._sqlite_path)
                conn.execute("DELETE FROM rag_chunks")
                conn.commit()
                conn.close()

            # Clear metadata
            if self._meta_db:
                self._meta_db.execute("DELETE FROM ingested_files")
                self._meta_db.commit()

            log.info("RAG: Knowledge base cleared ✅")
            return True
        except Exception as e:
            log.error(f"RAG: Clear failed: {e}")
            return False

    # ── Delete a specific file from KB ───────────────────────
    def delete_file(self, file_path: str) -> bool:
        """Remove a specific file's chunks from the knowledge base."""
        try:
            file_path = str(Path(file_path).resolve())
            source_name = Path(file_path).name

            if self._use_chromadb:
                existing = self._collection.get(
                    where={"file_path": file_path}
                )
                if existing and existing["ids"]:
                    self._collection.delete(ids=existing["ids"])
            else:
                conn = sqlite3.connect(self._sqlite_path)
                conn.execute(
                    "DELETE FROM rag_chunks WHERE source = ?",
                    (source_name,)
                )
                conn.commit()
                conn.close()

            # Remove from metadata
            if self._meta_db:
                self._meta_db.execute(
                    "DELETE FROM ingested_files WHERE file_path = ?",
                    (file_path,)
                )
                self._meta_db.commit()

            log.info(f"RAG: Removed '{source_name}' from knowledge base")
            return True
        except Exception as e:
            log.error(f"RAG: Delete file error: {e}")
            return False


# ═══════════════════════════════════════════════════════════════
#  Quick Test
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("=" * 55)
    print("  JARVIS RAG Engine — Test")
    print("=" * 55)

    rag = RAGEngine()
    print(f"\n  Status: {'READY' if rag.is_ready else 'NOT READY'}")
    print(f"  Backend: {'ChromaDB' if rag._use_chromadb else 'SQLite'}")

    if not rag.is_ready:
        print("\n  ERROR: RAG engine failed to initialize!")
        sys.exit(1)

    # Test 1: Ingest README
    readme_path = str(ROOT_DIR / "README.md")
    if os.path.exists(readme_path):
        print(f"\n  📄 Ingesting README.md...")
        result = rag.ingest_file(readme_path)
        print(f"     Status: {result['status']}, Chunks: {result.get('chunks', 0)}")

    # Test 2: Ingest a code file
    test_file = str(ROOT_DIR / "config.py")
    if os.path.exists(test_file):
        print(f"\n  📄 Ingesting config.py...")
        result = rag.ingest_file(test_file)
        print(f"     Status: {result['status']}, Chunks: {result.get('chunks', 0)}")

    # Test 3: Query
    test_queries = [
        "what voice commands does JARVIS support",
        "how to set up API keys",
        "what is the tech stack",
    ]

    for query in test_queries:
        print(f"\n  🔍 Query: '{query}'")
        results = rag.query(query, top_k=3)
        for r in results:
            preview = r["text"][:80].replace("\n", " ")
            print(f"     [{r['score']:.0%}] {r['source']}: {preview}...")

    # Test 4: Get context for prompt
    print("\n  📋 Context for Gemini prompt:")
    ctx = rag.get_context_for_prompt("voice commands")
    if ctx:
        # Show first 300 chars
        print(f"     {ctx[:300]}...")
    else:
        print("     (no context found)")

    # Test 5: Stats
    stats = rag.get_stats()
    print(f"\n  📊 Stats:")
    print(f"     Total chunks: {stats['total_chunks']}")
    print(f"     Total files: {stats['total_files']}")
    for f in stats.get("files", []):
        print(f"     - {f['name']}: {f['chunks']} chunks ({f['size_kb']} KB)")

    print("\n  ✅ RAG Engine working!")
