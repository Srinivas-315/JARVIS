"""
JARVIS â€” brain/local_llm.py
Local LLM handler via Ollama â€” fully offline AI brain.
No API key needed. Runs on your laptop.

Setup:
  1. Download Ollama: https://ollama.com/download
  2. Run: ollama pull phi3:mini
  3. JARVIS auto-detects and uses it!
"""

import json
import requests
from utils.logger import log
import config


# Ollama runs locally on this URL
OLLAMA_URL = "http://localhost:11434"

# Preferred models â€” jarvis-custom is our fine-tuned model (best!)
# jarvis-custom = YOUR trained JARVIS brain from Colab
# phi3:mini     = 2.3 GB RAM â€” fallback
# llama3.2:3b   = 2.0 GB RAM â€” fallback
PREFERRED_MODELS = ["jarvis-custom", "phi3:mini", "llama3.2:3b", "gemma2:2b", "mistral"]


# â”€â”€â”€ Model performance tracker â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Tracks good/garbage ratio per model â€” auto-switches to best one
_model_scores: dict[str, dict] = {}

def _record_model_result(model: str, good: bool):
    if model not in _model_scores:
        _model_scores[model] = {"good": 0, "garbage": 0}
    if good:
        _model_scores[model]["good"] += 1
    else:
        _model_scores[model]["garbage"] += 1

def _best_model(available_models: list[str]) -> str:
    """Return the model with the highest good/total ratio."""
    best, best_ratio = available_models[0], -1.0
    for m in available_models:
        stats = _model_scores.get(m, {"good": 1, "garbage": 0})
        total = stats["good"] + stats["garbage"]
        ratio = stats["good"] / max(total, 1)
        if ratio > best_ratio:
            best_ratio = ratio
            best = m
    return best

# â”€â”€â”€ Smart prompt templates â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
PROMPT_TEMPLATES = {
    "casual_chat": (
        "You are JARVIS, a helpful AI assistant. "
        "Reply casually and naturally in 1-2 short sentences."
    ),
    "technical": (
        "You are JARVIS. The user has a technical question. "
        "Give a clear, accurate, concise technical answer."
    ),
    "creative": (
        "You are JARVIS. Be imaginative and engaging. "
        "Reply in 2-3 sentences with personality."
    ),
    "emotional": (
        "You are JARVIS â€” empathetic and supportive. "
        "Acknowledge the user's feelings briefly, then offer help."
    ),
}

def _select_prompt_template(text: str) -> str:
    """Pick the best prompt template based on query type."""
    t = text.lower()
    if any(w in t for w in ["code", "python", "error", "debug", "function",
                              "sql", "script", "algorithm", "class"]):
        return PROMPT_TEMPLATES["technical"]
    if any(w in t for w in ["sad", "stress", "anxious", "worried", "tired",
                              "lonely", "depressed", "upset"]):
        return PROMPT_TEMPLATES["emotional"]
    if any(w in t for w in ["poem", "story", "joke", "creative", "write",
                              "imagine", "lyrics"]):
        return PROMPT_TEMPLATES["creative"]
    return PROMPT_TEMPLATES["casual_chat"]


class LocalLLM:
    """Fully offline LLM using Ollama. No internet needed!"""

    def __init__(self):
        self._model = None
        self._available = False
        self._history = []
        self._garbage_strikes = 0   # auto-disable after 3 consecutive bad responses

        # Conversation memory
        from brain.memory import ConversationMemory
        self.memory = ConversationMemory()

        self._detect_model()

    def _detect_model(self):
        """Check if Ollama is running and find best available model."""
        try:
            resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=2)
            if resp.status_code == 200:
                models = resp.json().get("models", [])
                model_names = [m["name"] for m in models]
                log.info(f"Ollama available! Models: {model_names}")

                # Pick the first preferred model that's installed
                for preferred in PREFERRED_MODELS:
                    for installed in model_names:
                        if preferred in installed:
                            self._model = installed
                            self._available = True
                            log.info(f"Local LLM selected: {self._model} âœ…")
                            return

                # Use first available model
                if model_names:
                    self._model = model_names[0]
                    self._available = True
                    log.info(f"Local LLM using: {self._model} âœ…")
                else:
                    log.warning("Ollama running but no models installed.")
                    log.warning("Run: ollama pull phi3:mini")
        except requests.ConnectionError:
            log.info("Ollama not running â€” local LLM offline.")
        except Exception as e:
            log.warning(f"Local LLM init error: {e}")

    def _is_garbage(self, reply: str) -> bool:
        """Detect if the model output is nonsense/garbage. Catches ALL types seen in logs."""
        import re

        if not reply or len(reply.strip()) < 2:
            return True

        # â”€â”€ Known garbage openers (seen in production logs) â”€â”€â”€â”€â”€
        garbage_openers = [
            "Fascinating â€”", "Fascinatingâ€”",
            "I find this rather intriguing",
            "To be precise, Hello", "To be precise, At your",
            "To be precise, Good to hear", "To be precise, I'm processing",
        ]
        if any(reply.startswith(g) for g in garbage_openers):
            return True

        # â”€â”€ Speaker labels (model leaked its training format) â”€â”€â”€â”€
        if re.search(r'\bSpeaker\s*:', reply, re.IGNORECASE):
            return True
        if re.search(r'JarvisSrini|SriniJarvis|Jarvis Srini says', reply):
            return True

        # â”€â”€ 3+ em-dashes = rambling/hallucinating â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        em_dash_count = reply.count('\u2014') + reply.count('\u2013')
        if em_dash_count >= 3:
            return True

        # â”€â”€ 4+ consecutive ALL-CAPS words (model went haywire) â”€â”€
        if re.search(r'\b[A-Z]{3,}\b(?:\s+\b[A-Z]{3,}\b){3,}', reply):
            return True

        # â”€â”€ Hard string signals â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        garbage_signals = [
            r'\{\{', r'\}\}', r'\[\[', r'\]\]',
            r'hiperonimia', r'FilePath', r'Special:', r'audio\|',
            r'webm', r'vorbis', r'ffmpeg', r'libavformat',
            r'<\|', r'\|>', r'<start>', r'ENDSTART',
            r'end_marker', r'Craft a regex', r'--Instruction',
            r'\[INST\]', r'<<SYS>>',
            r'Srini says:', r'Recent conversation:',
            r'I am Phi', r'engineered by Microsoft',
            r'I am an AI language model', r'as an AI assistant',
            r'TheNameOfAI', r'AIsolated', r'bear really needs seven legs',
            r'WolframAlpha', r'JARVISAbout', r'MarcZuckerberg',
            r'\w{40,}',
            # New patterns from production logs
            r'NadaHere', r'NothingHere', r'JustTell me a joke or else',
            r'hqhiphighgain', r'decoderffmpeg',
            r'NOASSEMBLY', r'NOSCRIPT', r'NAMED ANIMAL',
        ]
        for pattern in garbage_signals:
            if re.search(pattern, reply, re.IGNORECASE):
                return True

        # â”€â”€ Non-latin script check â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        non_latin_count = sum(1 for c in reply if ord(c) > 0x04FF)
        if non_latin_count > 10:
            return True

        # â”€â”€ URL clusters â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        if len(re.findall(r'https?://', reply)) >= 2:
            return True

        # â”€â”€ Special char runs â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        special_runs = re.findall(r'[^\w\s,.!?\'"-]{4,}', reply)
        if len(special_runs) >= 2:
            return True

        # â”€â”€ Alpha ratio â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        alpha = sum(c.isalpha() or c.isspace() for c in reply)
        if len(reply) > 30 and alpha / len(reply) < 0.55:
            return True

        # â”€â”€ Very long, no sentence breaks â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        if len(reply) > 300 and reply.count('.') < 2:
            return True

        # â”€â”€ Repetitive phrase detection â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        # e.g. "Hello sir Hello sir Hello sir"
        words = reply.lower().split()
        if len(words) > 10:
            bigrams = [f"{words[i]} {words[i+1]}" for i in range(len(words)-1)]
            most_common_count = max(bigrams.count(b) for b in set(bigrams)) if bigrams else 0
            if most_common_count >= 3:
                return True

        return False
        alpha = sum(c.isalpha() or c.isspace() for c in reply)
        if len(reply) > 30 and alpha / len(reply) < 0.55:
            return True

        # â”€â”€ Very long response with no sentence breaks â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        if len(reply) > 300 and reply.count('.') < 2:
            return True

        return False


    def _fallback_response(self, text: str) -> str:
        """Smart JARVIS fallback â€” handles common queries without any LLM."""
        import re, random
        t = text.lower().strip()

        # â”€â”€ Math calculation â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        # "1+1", "5 times 3", "10 minus 4", "one plus one"
        word_nums = {'zero':0,'one':1,'two':2,'three':3,'four':4,'five':5,
                     'six':6,'seven':7,'eight':8,'nine':9,'ten':10}
        for wn, wv in word_nums.items():
            t = t.replace(wn, str(wv))
        t = t.replace('plus','+').replace('minus','-').replace('times','*') \
             .replace('multiplied by','*').replace('divided by','/') \
             .replace('x','*').replace('equals','').replace('equal to','')
        math_m = re.search(r'(\d+)\s*([+\-*/])\s*(\d+)', t)
        if math_m:
            try:
                a, op, b = int(math_m.group(1)), math_m.group(2), int(math_m.group(3))
                res = {'+': a+b, '-': a-b, '*': a*b, '/': a/b if b else 'undefined'}[op]
                return f"That's {res}, sir."
            except Exception:
                pass

        # â”€â”€ Counting â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        # "count 1 to 10", "1 to 10 numbers", "count from 3 to 7"
        count_m = re.search(r'(?:count\s+)?(?:from\s+)?(\d+)\s+to\s+(\d+)', text.lower())
        if count_m:
            start, end = int(count_m.group(1)), int(count_m.group(2))
            if 0 <= start <= 1000 and 0 <= end <= 1000 and abs(end-start) <= 100:
                nums = list(range(start, end+1)) if end >= start else list(range(start, end-1, -1))
                return ', '.join(str(n) for n in nums) + '.'

        # Re-read original text for remaining checks
        tl = text.lower()

        # â”€â”€ How are you (including "how r u", "how r you") â”€â”€â”€â”€â”€â”€
        if re.search(r'how\s+(r|are)\s+(u|you)', tl) or 'how r u' in tl:
            return random.choice([
                "Operating at peak efficiency, sir. More importantly â€” how are YOU doing?",
                "All systems green! What can I help you with?",
                "Running great, sir. Ready to assist!",
            ])

        # â”€â”€ Jokes / make me laugh â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        if any(w in tl for w in ['joke', 'laugh', 'funny', 'make me laugh', 'something funny', 'humour']):
            jokes = [
                "Why don't scientists trust atoms? Because they make up everything!",
                "Why do programmers prefer dark mode? Because light attracts bugs!",
                "I told my computer I needed a break. Now it won't stop sending me Kit-Kat ads.",
                "Why did the AI cross the road? It was optimizing the shortest path to the other side.",
                "I asked my local LLM a joke. It gave me a 500-word essay on humour theory instead.",
                "What do you call a computer that sings? A Dell!",
            ]
            return random.choice(jokes)

        # â”€â”€ Favourite colour/color â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        if any(w in tl for w in ['favourite colour', 'favorite color', 'fav colour', 'favourite color', 'fav color']):
            return "I don't have your favourite colour stored yet, sir. Tell me and I'll remember it!"

        # â”€â”€ Greeting â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        if re.search(r'^(hello|hey|hi|hiya|howdy|good (morning|evening|night|afternoon))', tl):
            return random.choice([
                "Hello, sir! All systems online. What can I do for you?",
                "Hey! Ready and waiting. What's on your mind?",
                "Good to hear from you, sir. What shall we do today?",
            ])

        # â”€â”€ Status / feelings â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        if any(w in tl for w in ['stress', 'anxious', 'worried', 'sad', 'tired', 'lonely', 'upset']):
            return "I hear you, sir. Want to talk through what's on your mind?"

        # â”€â”€ Compliments â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        if any(w in tl for w in ['good job', 'well done', 'great', 'awesome', 'thank', 'thanks']):
            return random.choice([
                "Always happy to help, sir!",
                "That's what I'm here for!",
                "Glad I could assist, sir.",
            ])

        # â”€â”€ Capability question â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        if any(w in tl for w in ['what can you do', 'your capabilities', 'help me', 'what do you do']):
            return ("I can open apps, control your system, send WhatsApp/email, check weather, "
                    "take screenshots, set timers, search the web, and identify objects with the camera. "
                    "What would you like to do?")

        # â”€â”€ Generic smart fallback â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        return random.choice([
            "My offline brain is limited right now, sir. Try reconnecting Gemini for complex questions.",
            "I caught that, but I need my full AI brain for this one. Gemini API quota may be reset soon.",
            "For simple tasks I'm ready â€” but that question needs Gemini. What else can I help with?",
        ])

    def _clean_response(self, reply: str) -> str:
        """Strip known garbage artifacts from model output."""
        import re
        patterns = [
            r'--Instruction:.*',
            r'Srini says:.*',
            r'\[INST\].*',
            r'<<SYS>>.*',
            r'<\|.*?\|>',
            r'Much More Diff.*',
            r'Constraints Answered.*',
            r'Food for thought, sir\..*',
            r'<start>.*',
            r'ENDSTART.*',
        ]
        for p in patterns:
            reply = re.sub(p, '', reply, flags=re.IGNORECASE | re.DOTALL)
        reply = re.sub(r'\n{3,}', '\n\n', reply).strip()
        # Trim if too long
        if len(reply) > 500:
            sentences = reply.split('. ')
            trimmed = ''
            for s in sentences:
                if len(trimmed) + len(s) < 450:
                    trimmed += s + '. '
                else:
                    break
            reply = trimmed.strip()
        return reply

    def _post_process(self, text: str) -> str:
        """
        Post-process model output:
        - Remove repeated sentences
        - Fix punctuation
        - Trim excessive length
        """
        import re
        # Remove repeated sentences
        sentences = re.split(r'(?<=[.!?])\s+', text)
        seen, unique = set(), []
        for s in sentences:
            norm = s.strip().lower()
            if norm not in seen:
                seen.add(norm)
                unique.append(s.strip())
        text = " ".join(unique)
        # Fix double spaces
        text = re.sub(r'  +', ' ', text).strip()
        # Ensure ends with punctuation
        if text and text[-1] not in '.!?':
            text += '.'
        return text

    def _compress_context(self, messages: list) -> list:
        """
        Context window compression for Ollama's limited context.
        Keep last 3 in full, summarize 4-10, drop older.
        """
        if len(messages) <= 6:
            return messages
        # Keep last 6 messages (3 exchanges) in full
        recent = messages[-6:]
        old = messages[:-6]
        if not old:
            return recent
        # Summarize the old ones into one compressed system message
        summary = "[Earlier conversation: " + " | ".join(
            f"{m['role']}: {m['content'][:50]}" for m in old
        ) + "]"
        compressed = [{"role": "system", "content": summary}]
        return compressed + recent

    def ask(self, text: str) -> str:
        """Send a chat message to the local LLM with full memory context."""
        if not self._available:
            return ""

        try:
            # Select best-performing model
            if self._model:
                best = _best_model([self._model])
            system = _select_prompt_template(text)

            # Build facts context
            facts = self.memory.get_facts_prompt()
            if facts:
                system = system + f"\n\n{facts}"

            messages = [{"role": "system", "content": system}]

            # Compress context to fit Ollama's window
            context = self.memory.get_context_messages()
            compressed = self._compress_context(context)
            messages.extend(compressed)

            messages.append({"role": "user", "content": text})
            self.memory.add_user_message(text)

            # Call Ollama API
            resp = requests.post(
                f"{OLLAMA_URL}/api/chat",
                json={
                    "model": self._model,
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "num_predict": 150,    # tight, focused responses
                        "temperature": 0.72,
                        "repeat_penalty": 1.4, # stronger anti-repeat
                        "top_p": 0.9,
                    }
                },
                timeout=30
            )

            if resp.status_code == 200:
                result = resp.json()
                reply = result.get("message", {}).get("content", "").strip()

                if reply:
                    reply = self._clean_response(reply)
                    reply = self._post_process(reply)   # NEW: dedup + fix punctuation
                    if not reply or self._is_garbage(reply):
                        self._garbage_strikes += 1
                        _record_model_result(self._model or "", False)  # track bad
                        log.warning(f"Model garbage strike {self._garbage_strikes}/3")
                        if self._garbage_strikes >= 3:
                            log.warning("3 garbage strikes â€” disabling local LLM for this session")
                            self._available = False
                            return ""
                        reply = self._fallback_response(text)
                    else:
                        self._garbage_strikes = 0   # BUG FIX: reset on ALL good paths
                        _record_model_result(self._model or "", True)   # track good
                    self.memory.add_jarvis_message(reply)
                    log.info(f"Local LLM responded ({len(reply)} chars)")
                    return reply

            log.warning(f"Local LLM error: {resp.status_code}")
            return ""

        except requests.Timeout:
            log.warning("Local LLM timeout (30s)")
            return ""
        except Exception as e:
            log.error(f"Local LLM error: {e}")
            return ""

    def reset(self):
        """Clear conversation history."""
        self._history.clear()
        self.memory.clear_session()
        log.info("Local LLM history cleared.")



# â”€â”€â”€ Quick test â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
if __name__ == "__main__":
    llm = LocalLLM()
    if llm.is_available:
        print(f"Model: {llm.model_name}")
        print("Testing...")
        reply = llm.ask("Hello! What can you do?")
        print(f"Reply: {reply}")
    else:
        print("Ollama not available.")
        print("Install: https://ollama.com/download")
        print("Then run: ollama pull phi3:mini")

