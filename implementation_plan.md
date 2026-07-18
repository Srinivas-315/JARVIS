# RAG Pipeline for JARVIS — Make JARVIS Truly Intelligent

Adding a full Retrieval-Augmented Generation (RAG) pipeline so JARVIS can ingest, search, and answer from your personal documents, code, notes, and past conversations — all running **locally** on your machine.

## What Changes

Right now, JARVIS has a basic `vector_memory.py` that only stores **conversation turns**. The new RAG pipeline will let JARVIS ingest **any document** (PDFs, text files, Python code, notes) and retrieve relevant chunks before every Gemini API call — making responses grounded in YOUR actual data.

## User Review Required

> [!IMPORTANT]
> This will add 2 new dependencies: `chromadb` (vector database, ~50MB) and `PyPDF2` (PDF reader, ~1MB). Both are free, local, and don't need any API keys.

> [!NOTE]
> Your existing `vector_memory.py` (conversation memory) will NOT be touched. The RAG pipeline is a separate, additional system that handles documents.

## Proposed Changes

### Phase 1 — RAG Core Engine

#### [NEW] [rag_engine.py](file:///c:/Users/srini/OneDrive/Attachments/Desktop/PROJECTS/JARVIS/brain/rag_engine.py)

The core RAG pipeline with these capabilities:

| Feature | What It Does |
|---------|-------------|
| **Document Loader** | Reads `.pdf`, `.txt`, `.py`, `.md`, `.json`, `.docx` files |
| **Smart Chunker** | Splits documents into 500-token chunks with 50-token overlap |
| **Embedder** | Uses `all-MiniLM-L6-v2` (same model you already have!) |
| **Vector Store** | ChromaDB persistent collection stored in `data/rag_db/` |
| **Retriever** | Top-5 semantic search with similarity scoring |
| **Context Builder** | Formats retrieved chunks for injection into Gemini prompt |

Key classes:
- `DocumentLoader` — loads and parses different file types
- `TextChunker` — splits text into overlapping chunks
- `RAGEngine` — main class that ties everything together

```python
# Usage:
rag = RAGEngine()
rag.ingest_file("notes/ml_lecture.pdf")        # Ingest a PDF
rag.ingest_folder("C:/Users/srini/Notes/")     # Ingest entire folder
results = rag.query("what are transformers?")   # Semantic search
context = rag.get_context_for_prompt("explain attention mechanism")
```

---

### Phase 2 — RAG Skill (Voice Commands)

#### [NEW] [knowledge_base.py](file:///c:/Users/srini/OneDrive/Attachments/Desktop/PROJECTS/JARVIS/skills/knowledge_base.py)

New JARVIS skill so you can control RAG via voice:

| Voice Command | Action |
|---------------|--------|
| "Jarvis, learn this file: notes.pdf" | Ingests a specific file |
| "Jarvis, learn my notes folder" | Ingests entire folder |
| "Jarvis, search my documents for transformers" | Searches knowledge base |
| "Jarvis, what do my notes say about neural networks?" | RAG-powered Q&A |
| "Jarvis, how many documents do you know?" | Shows KB stats |
| "Jarvis, forget all documents" | Clears the knowledge base |

---

### Phase 3 — Gemini Prompt Augmentation

#### [MODIFY] [gemini_handler.py](file:///c:/Users/srini/OneDrive/Attachments/Desktop/PROJECTS/JARVIS/brain/gemini_handler.py)

Modify the `ask()` method to automatically retrieve relevant document chunks before every Gemini API call:

```diff
 # In ask() method, before building full_text:
+# ── RAG: Retrieve relevant document context ──
+rag_context = ""
+if self._rag_engine and self._rag_engine.is_ready:
+    rag_context = self._rag_engine.get_context_for_prompt(prompt, top_k=5)
+
 full_text = f"{system}\n\n"
 if history:
     full_text += f"Conversation so far:\n{history}\n\n"
+if rag_context:
+    full_text += f"Relevant knowledge from user's documents:\n{rag_context}\n\n"
 if context:
     full_text += f"Context: {context}\n\n"
```

Also add a `set_rag_engine()` method (same pattern as `set_memory_system()`).

---

### Phase 4 — Intent Router Integration

#### [MODIFY] [smart_router.py](file:///c:/Users/srini/OneDrive/Attachments/Desktop/PROJECTS/JARVIS/brain/smart_router.py)

Add new intent patterns so the router recognizes knowledge base commands:

```python
# New intents to add:
"knowledge_ingest"  → triggers knowledge_base.py ingest
"knowledge_search"  → triggers knowledge_base.py search
"knowledge_ask"     → triggers RAG-powered Q&A via Gemini
```

Trigger phrases: "learn this file", "search my documents", "what do my notes say", "from my files", "in my documents"

---

### Phase 5 — Auto-Ingest Important Data

#### [MODIFY] [rag_engine.py](file:///c:/Users/srini/OneDrive/Attachments/Desktop/PROJECTS/JARVIS/brain/rag_engine.py)

Add auto-ingest for JARVIS's own data sources:

| Auto-Ingest Source | What Gets Indexed |
|-------------------|-------------------|
| Past conversations | `data/conversations.db` → all past chats become searchable |
| Email history | `data/email_history.db` → past emails become queryable |
| Calendar events | `data/calendar.json` → schedule becomes searchable |
| Code memory | `data/code_memory.db` → past code snippets become retrievable |
| Personal facts | `data/personal_facts.json` + `user_memory.json` |

This means JARVIS will automatically know about everything you've ever told it, every email you've read through it, and every calendar event — without you manually ingesting anything.

---

## How JARVIS Gets Smarter — Before vs After

| Scenario | Before (No RAG) | After (With RAG) |
|----------|-----------------|-------------------|
| "What did I study yesterday?" | ❌ "I don't remember" | ✅ Retrieves from your notes/conversations |
| "Summarize my ML lecture" | ❌ Can't access files | ✅ Reads your PDF, summarizes key points |
| "What code did I write for sorting?" | ❌ Generic answer | ✅ Finds YOUR actual code from code_memory |
| "When is my exam?" | ⚠️ Only if you told it this session | ✅ Finds it from calendar + past conversations |
| "What did Mom's email say?" | ❌ No access | ✅ Retrieves from email_history |
| "How does my WhatsApp skill work?" | ❌ Generic Python answer | ✅ Reads whatsapp.py source code and explains |

---

## File Structure After Implementation

```
JARVIS/
├── brain/
│   ├── rag_engine.py          ← [NEW] Core RAG pipeline
│   ├── vector_memory.py       ← [UNCHANGED] Conversation memory
│   ├── gemini_handler.py      ← [MODIFIED] Injects RAG context
│   └── smart_router.py        ← [MODIFIED] New intent routing
├── skills/
│   └── knowledge_base.py      ← [NEW] Voice commands for RAG
├── data/
│   └── rag_db/                ← [NEW] ChromaDB persistent storage
└── requirements.txt           ← [MODIFIED] Add chromadb, PyPDF2
```

## Verification Plan

### Automated Tests
```powershell
# Test 1: Ingest a test document and query it
python -c "from brain.rag_engine import RAGEngine; r = RAGEngine(); r.ingest_file('README.md'); print(r.query('what is JARVIS'))"

# Test 2: Check ChromaDB persistence
python -c "from brain.rag_engine import RAGEngine; r = RAGEngine(); print(r.get_stats())"

# Test 3: Full pipeline — ingest, query, get Gemini-ready context
python -c "from brain.rag_engine import RAGEngine; r = RAGEngine(); r.ingest_file('README.md'); print(r.get_context_for_prompt('voice commands'))"
```

### Manual Verification
- Launch JARVIS and say "Jarvis, learn this file README.md"
- Then ask "Jarvis, what voice commands do you support?" — should answer from README
- Check that `data/rag_db/` folder is created with ChromaDB files
