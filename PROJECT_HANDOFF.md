# JARVIS Project Handoff

## 1. Full Current Architecture
JARVIS is built as a locally-hosted, multimodal Personal AI Assistant leveraging Gemini 1.5 Flash for natural language understanding and reasoning. It operates via a central `main.py` daemon that orchestrates voice input, vision models, proactive systems, and a distributed execution engine.

**Core Components:**
- **SmartRouter (`brain/smart_router.py`)**: A 3-tier routing system (Instant -> Local ML -> Gemini) that parses user intents and dispatches them to execution blocks.
- **SkillExecutor (`brain/skill_executor.py`)**: Routes classified intents directly to module methods.
- **AgentManager (`skills/agent_engine.py`)**: A background daemon that performs asynchronous multi-step execution.
- **ProactiveAssistant (`skills/proactive_assistant.py`)**: A background daemon evaluating context for proactive alerts.

## 2. All Completed Modules
- **Voice System**: Text-To-Speech (Edge TTS / Pyttsx3) and Speech-To-Text (Whisper / SpeechRecognition).
- **Vision System**: Screen capturing and YOLOv8 object detection.
- **Memory Systems**: Unified long-term and short-term context stores.
- **Recurring Reminders**: SQLite-backed scheduling engine for periodic events.
- **WhatsApp Integrations**: Call monitoring, notification watching, sending/reading messages, draft approval queues.
- **Email Integrations**: Gmail reading, summarizing, searching, and composition.
- **Proactive Assistant Layer**: Context-aware daemon that evaluates state and announces alerts proactively.
- **Agent Task Execution Engine**: Goal-driven multi-step planner and executor with verification and safety gates.

## 3. Database Tables
All persistent data is stored in `jarvis_memory.db` with Thread-Safe SQLite locking (`memory/database.py`).
- `recurring_reminders`: `id, message, frequency, at_time, created_at`
- `whatsapp_drafts`: `id, contact, incoming_message, generated_reply, status, timestamp`
- `assistant_alerts`: `id, alert_type, message, created_at, delivered_at`
- `agent_tasks`: `id, goal, plan_json, current_step, status, created_at, updated_at`
- `conversations_full`: Standard conversational history.
- `skill_log`: Auditable execution log for all skills.

## 4. Memory Systems
JARVIS uses a Unified Context Pipeline (`memory/unified_context.py` and `brain/context_manager.py`) combining:
- **Personal Facts**: Hardcoded user facts and preferences (`PersonalMemory`).
- **Short-Term Context**: Cross-turn dialogue retention and pronoun resolution (`ConversationContext`).
- **Semantic Vector Storage**: Persistent vector database for RAG retrieval of historical facts.

## 5. Reminder Systems
Located in `skills/reminder.py`.
- **One-Time**: Scheduled via `schedule` module, lives in-memory until executed.
- **Recurring**: Persisted in SQLite `recurring_reminders` and re-loaded into the `schedule` engine on boot via `_load_recurring_reminders()`.

## 6. WhatsApp Systems
Located in `skills/whatsapp.py` and `scratch/whatsapp_call_monitor.py`.
- **Call Monitoring**: Uses Windows `pywinauto` UIA hooks to detect incoming calls safely without OCR latency, utilizing native keyboard shortcuts (`Ctrl+Alt+Shift+A/D`).
- **Draft & Approval System**: Incoming messages are intercepted, passed to Gemini for a drafted response based on Unified Context, and stored in `whatsapp_drafts` with a 'pending' status for user review.

## 7. Proactive Assistant
Located in `skills/proactive_assistant.py`.
- Daemon thread waking every 5 minutes.
- Feeds calendar, drafts, reminders, and recent events into a zero-shot Gemini prompt.
- Incorporates a 30-minute cooldown window per alert category (Calendar, Email, Reminders) to prevent spam.
- Stores historical alerts in `assistant_alerts` to ensure idempotency.

## 8. Agent Engine
Located in `skills/agent_engine.py`.
- **Planner**: Deconstructs natural language goals into a JSON array of actionable steps.
- **Executor**: Wraps `JARVIS.router` and `JARVIS.executor` to reuse the existing parsing architecture.
- **Verifier**: (Designed for) Visual screen verification of step completion.
- **Safety**: Inspects plan steps for keywords ("send", "pay", "delete") and pauses execution (`waiting_user`), requesting explicit user consent to proceed.

## 9. Runtime Commands
- **Agent Engine**: `start task <goal>`, `show active tasks`, `task status`, `resume task`, `cancel task`, `retry task`.
- **WhatsApp Drafts**: `show whatsapp drafts`, `read whatsapp draft <id>`, `send whatsapp draft <id>`, `reject whatsapp draft <id>`, `clear whatsapp drafts`.
- **Reminders**: `set reminder`, `set recurring reminder`, `list reminders`, `edit reminder`, `delete reminder`.

## 10. Known Limitations
- The `AgentVerifier` currently bypasses full screen-OCR validation for step success unless manually hooked due to latency constraints in the current Windows environment.
- WhatsApp Call Monitoring depends strictly on the English UI labels ("Incoming video call", "Incoming voice call") in the WhatsApp desktop app.
- Email integration uses `pywinauto` rather than IMAP/SMTP due to security and local client requirements. It requires the Mail app to be visible.

## 11. Remaining Roadmap
1. **Full Visual Validation Hookup**: Wire `AgentVerifier` directly to `what_is_on_screen()` for genuine autonomous validation of Agent steps.
2. **Dynamic UI Adaptation**: Fallbacks for WhatsApp and Email interactions if the window hierarchy changes or updates.
3. **Advanced Calendar Syncing**: Moving beyond local parsing to a dedicated backend schema for full meeting negotiations.
4. **Local ML Optimization**: Upgrading the local DistilBERT router to a quantized ONNX model for sub-1ms intent parsing.
