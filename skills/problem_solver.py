"""
JARVIS — skills/problem_solver.py
Problem Solver — solves LeetCode, DSA, and any coding/logic/math problems.

Capabilities:
  1. Solve from screen   — reads LeetCode problem via screen vision, generates solution
  2. Solve by voice      — "solve two sum", "solve reverse linked list"
  3. Debug from screen   — reads error/code from screen, identifies bug, gives fix
  4. Explain approach    — re-explains the last solution's logic and complexity
  5. Optimize code       — reads code from screen, suggests optimizations

Usage:
  "Solve this"                   → screen-read LeetCode problem → generate + paste
  "Solve two sum problem"        → solve by name
  "Debug this" / "Fix this code" → read screen, find bug
  "Explain the approach"         → explain last solution
  "Optimize this code"           → read screen, suggest better solution
"""

import base64
import io
import re
import time
from datetime import datetime

import pyautogui
import pyperclip
import requests
from PIL import ImageGrab

import config
from utils.logger import log

pyautogui.FAILSAFE = False

# ─── Gemini API (direct call — bypasses local LLM fallback) ────
# Fallback chain: try each model in order when previous is overloaded (503/429)
# Includes retry of primary model after a delay (503 is usually temporary)
_GEMINI_MODELS = [
    "gemini-2.5-flash",       # Best quality (primary)
    "gemini-2.0-flash",       # Fast fallback
    "gemini-2.0-flash-lite",  # Lightweight fallback
]
_GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"


# ─── Prompts (tuned for competitive programming) ─────────────────

_SOLVE_FROM_SCREEN_PROMPT = """\
You are an expert competitive programmer who has solved 2000+ LeetCode problems.

This screenshot shows a coding problem from LeetCode (or similar platform).

STEP 1: Read and understand the problem from the screenshot.
STEP 2: Solve it optimally in {language}.

REQUIREMENTS — follow these EXACTLY:
1. APPROACH: State your approach in 1 sentence
2. COMPLEXITY: Time and space complexity
3. CODE: Write the COMPLETE solution
   - Use the equivalent function/class signature in {language} for the problem visible in the screenshot (for example, if the screenshot shows a Python signature and you are asked to solve in C++, translate the signature to proper C++ structure)
   - Handle ALL edge cases
   - If the problem uses ListNode/TreeNode, do NOT redefine it
4. DRY RUN: Quick trace through Example 1

FORMAT your response EXACTLY like this:
PROBLEM_TITLE: [Short name of the problem]
PROBLEM_TEXT: [1-2 sentences summarizing the core problem]
APPROACH: [1 sentence]
COMPLEXITY: Time O(...), Space O(...)

```{lang_lower}
[your complete solution code here]
```

DRY RUN: [trace through Example 1]"""

_SOLVE_BY_NAME_PROMPT = """\
You are an expert competitive programmer who has solved 2000+ LeetCode problems.

Solve this problem: {problem_name}

Language: {language}

Give the OPTIMAL solution (not brute force). Include:
1. APPROACH: 1-sentence description of the algorithm
2. COMPLEXITY: Time and space
3. CODE: Complete, working solution with the standard LeetCode function signature
4. EDGE CASES: List what edge cases you handle

FORMAT your response EXACTLY like this:
PROBLEM_TITLE: [Name of the problem]
PROBLEM_TEXT: [1-2 sentences summarizing the core problem]
APPROACH: [1 sentence]
COMPLEXITY: Time O(...), Space O(...)

```{lang_lower}
[complete solution code here]
```

EDGE CASES: [list them]"""

_DEBUG_PROMPT = """\
This is a screenshot showing code with an error or failing test case.

Analyze carefully:
1. What is the code trying to do?
2. What is the EXACT error or wrong output?
3. What is the ROOT CAUSE of the bug?
4. What is the FIX? (show the corrected code)

Be specific — point to the exact line and explain why it fails.
Give the FIXED code in a ```python code block``` ready to paste."""

_OPTIMIZE_PROMPT = """\
This is a screenshot showing code that works but may not be optimal.

Analyze:
1. What is the current approach and its time/space complexity?
2. What is a BETTER approach?
3. Why is it better? (concrete Big-O improvement)
4. Give the OPTIMIZED code in a ```python code block``` ready to paste.

If the code is already optimal, say so."""

_EXPLAIN_PROMPT = """\
Explain this solution like you're teaching a student:

{solution}

Cover:
1. What algorithm/technique is used and WHY it works
2. Time and space complexity
3. Walk through the key logic step by step
4. Edge cases handled

Keep it concise — 4-6 sentences max. Speak naturally."""

_EXPLAIN_SCREEN_PROMPT = """\
This is a screenshot showing a coding problem.

DO NOT describe the screen visually or say things like "It looks like someone is solving...".
Instead, provide a clear and structured explanation of the problem itself:
1. What the problem asks (1-2 sentences)
2. Input/Output format
3. Key Idea
4. Constraints to be aware of
5. Example Walkthrough
6. Common Approach

Speak naturally but concisely."""

class ProblemSolver:
    """
    Solves LeetCode and coding problems via screen vision + Gemini Vision API.

    KEY DESIGN: Uses DIRECT Gemini Vision API calls (screenshot + prompt in one shot)
    instead of going through GeminiHandler.ask() which may fall back to
    the local LLM and produce garbage output.
    """

    def __init__(self, gemini_handler=None, vision_handler=None):
        self.gemini = gemini_handler
        self.vision = vision_handler
        self._api_key = config.GEMINI_API_KEY
        # Last solved state (session memory)
        self._last_problem_title = ""
        self._last_problem_text = ""
        self._last_solution = ""
        self._last_code = ""
        self._last_approach = ""
        self._last_complexity = ""
        self._last_timestamp = None
        self._default_language = "Python"
        self._solve_history = []

        # ── Code Memory — remembers every problem solved ──────
        try:
            from skills.code_memory import CodeMemory
            self.memory = CodeMemory()
        except Exception as e:
            log.warning(f"CodeMemory unavailable: {e}")
            self.memory = None

        log.info("ProblemSolver ready ✅ — say 'solve this' on any coding problem!")

    # ═══════════════════════════════════════════════════════════
    # DIRECT GEMINI VISION CALL (bypasses local LLM fallback)
    # ═══════════════════════════════════════════════════════════

    def _screenshot_to_base64(self) -> str:
        """Capture screen and convert to base64 — high res for code readability."""
        screenshot = ImageGrab.grab()
        # Keep high resolution for code readability (don't shrink below 1920px)
        if screenshot.size[0] > 1920:
            ratio = 1920 / screenshot.size[0]
            screenshot = screenshot.resize(
                (1920, int(screenshot.size[1] * ratio))
            )
        buf = io.BytesIO()
        screenshot.save(buf, format="PNG", quality=95)
        return base64.b64encode(buf.getvalue()).decode()

    def _call_gemini_vision(self, prompt: str, image_b64: str) -> str:
        """
        Send screenshot + prompt DIRECTLY to Gemini Vision API.
        Tries multiple models in fallback order (2.5-flash → 2.0-flash → 1.5-flash).
        This bypasses GeminiHandler.ask() and its local LLM fallback.
        """
        if not self._api_key:
            log.error("No Gemini API key — cannot solve problems")
            return ""

        body = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {
                            "inline_data": {
                                "mime_type": "image/png",
                                "data": image_b64,
                            }
                        },
                    ]
                }
            ]
        }

        for model in _GEMINI_MODELS:
            url = _GEMINI_API_BASE.format(model=model, key=self._api_key)
            try:
                log.info(f"🌐 Trying {model}...")
                resp = requests.post(url, json=body, timeout=60)

                if resp.status_code == 200:
                    data = resp.json()
                    parts = (
                        data.get("candidates", [{}])[0]
                        .get("content", {})
                        .get("parts", [])
                    )
                    for p in reversed(parts):
                        if "text" in p and not p.get("thought", False):
                            log.info(f"✅ Got response from {model}")
                            return p["text"].strip()
                    log.error(f"{model}: response had no text parts")
                    continue

                elif resp.status_code in (429, 503):
                    log.warning(f"{model}: overloaded ({resp.status_code}), trying next...")
                    time.sleep(1)  # Brief pause before trying next model
                    continue
                else:
                    log.error(f"{model}: error {resp.status_code} — {resp.text[:150]}")
                    continue

            except Exception as e:
                log.error(f"{model}: request failed — {e}")
                continue

        # All models failed on first pass — retry primary after delay (503 is temporary)
        log.warning("All models busy — waiting 5 seconds and retrying primary...")
        time.sleep(5)
        url = _GEMINI_API_BASE.format(model=_GEMINI_MODELS[0], key=self._api_key)
        try:
            resp = requests.post(url, json=body, timeout=60)
            if resp.status_code == 200:
                data = resp.json()
                parts = (
                    data.get("candidates", [{}])[0]
                    .get("content", {})
                    .get("parts", [])
                )
                for p in reversed(parts):
                    if "text" in p and not p.get("thought", False):
                        log.info(f"✅ Got response from {_GEMINI_MODELS[0]} (retry)")
                        return p["text"].strip()
        except Exception:
            pass

        log.error("All Gemini models failed after retry")
        return ""


    def _call_gemini_text(self, prompt: str) -> str:
        """
        Send text-only prompt DIRECTLY to Gemini API (no image).
        Tries multiple models in fallback order.
        Bypasses GeminiHandler to avoid local LLM fallback.
        """
        if not self._api_key:
            if self.gemini:
                return self.gemini.ask(prompt)
            return ""

        body = {
            "contents": [{"parts": [{"text": prompt}]}]
        }

        for model in _GEMINI_MODELS:
            url = _GEMINI_API_BASE.format(model=model, key=self._api_key)
            try:
                log.info(f"🌐 Trying {model} (text)...")
                resp = requests.post(url, json=body, timeout=60)

                if resp.status_code == 200:
                    data = resp.json()
                    parts = (
                        data.get("candidates", [{}])[0]
                        .get("content", {})
                        .get("parts", [])
                    )
                    for p in reversed(parts):
                        if "text" in p and not p.get("thought", False):
                            log.info(f"✅ Got response from {model}")
                            return p["text"].strip()
                    continue

                elif resp.status_code in (429, 503):
                    log.warning(f"{model}: overloaded ({resp.status_code}), trying next...")
                    time.sleep(1)
                    continue
                else:
                    log.error(f"{model}: error {resp.status_code}")
                    continue

            except Exception as e:
                log.error(f"{model}: request failed — {e}")
                continue

        # Retry primary model after delay
        log.warning("All models busy (text) — waiting 5 seconds and retrying...")
        time.sleep(5)
        url = _GEMINI_API_BASE.format(model=_GEMINI_MODELS[0], key=self._api_key)
        try:
            resp = requests.post(url, json=body, timeout=60)
            if resp.status_code == 200:
                data = resp.json()
                parts = (
                    data.get("candidates", [{}])[0]
                    .get("content", {})
                    .get("parts", [])
                )
                for p in reversed(parts):
                    if "text" in p and not p.get("thought", False):
                        log.info(f"✅ Got response from {_GEMINI_MODELS[0]} (retry)")
                        return p["text"].strip()
        except Exception:
            pass

        log.error("All Gemini models failed for text after retry")
        if self.gemini:
            return self.gemini.ask(prompt)
        return ""

    # ═══════════════════════════════════════════════════════════
    # 1. SOLVE FROM SCREEN (LeetCode / any platform)
    # ═══════════════════════════════════════════════════════════

    def solve_from_screen(self, language: str = None) -> str:
        """
        Read a coding problem from the screen and solve it — SINGLE API call.

        Takes screenshot → sends to Gemini Vision with solve prompt → extracts code.
        One-shot approach avoids the local LLM fallback that produces garbage.
        """
        if not self._api_key:
            return "I need Gemini API to solve problems, but the key isn't set."

        lang = language or self._default_language
        log.info(f"📖 Capturing screen + solving in one shot...")

        # ── Single shot: screenshot + solve prompt → Gemini Vision ──
        try:
            image_b64 = self._screenshot_to_base64()
            log.info("📷 Screenshot captured, sending to Gemini Vision...")

            prompt = _SOLVE_FROM_SCREEN_PROMPT.format(
                language=lang,
                lang_lower=lang.lower(),
            )

            raw = self._call_gemini_vision(prompt, image_b64)

            if not raw or len(raw) < 30:
                return ("Gemini couldn't analyze the screen. "
                        "Make sure the problem is fully visible and try again.")

            self._last_problem = f"[from screen at {datetime.now().strftime('%H:%M')}]"
            return self._process_solution(raw, "LeetCode screen", lang)

        except Exception as e:
            log.error(f"Solve from screen error: {e}")
            return f"Hit an error: {str(e)[:80]}. Try again."

    # ═══════════════════════════════════════════════════════════
    # 2. SOLVE BY NAME (voice command)
    # ═══════════════════════════════════════════════════════════

    def solve_by_name(self, problem_name: str, language: str = None) -> str:
        """
        Solve a well-known problem by name.
        E.g., "two sum", "reverse linked list", "merge intervals"
        
        CHECK MEMORY FIRST — if JARVIS already solved this, skip the API call!
        """
        lang = language or self._default_language
        log.info(f"🧠 Solving '{problem_name}' in {lang}...")

        # ── Step 1: Check memory — already solved? ────────────
        if self.memory:
            cached = self.memory.find_exact(problem_name, lang)
            if cached:
                log.info(f"💡 Found in memory! Skipping API call.")
                self._last_code = cached["solution_code"]
                self._last_approach = cached["approach"]
                self._last_complexity = cached["complexity"]
                self._last_solution = cached["solution_code"]
                pyperclip.copy(cached["solution_code"])
                return (
                    f"I already know this one! "
                    f"Approach: {cached['approach']}. "
                    f"Complexity: {cached['complexity']}. "
                    f"Solution copied to clipboard. Say 'paste it' to put it in."
                )

            # Check for similar problems
            similar = self.memory.find_similar_text(problem_name, top_k=2)
            if similar and similar[0][0] > 0.4:  # >40% similarity
                best = similar[0][1]
                log.info(f"💡 Found similar problem: {best['problem_name']}")
                # Still call Gemini but mention the similar problem

        # ── Step 2: Call Gemini ────────────────────────────────
        prompt = _SOLVE_BY_NAME_PROMPT.format(
            problem_name=problem_name,
            language=lang,
            lang_lower=lang.lower(),
        )

        try:
            raw = self._call_gemini_text(prompt)
            if not raw:
                return "Couldn't get a response from Gemini. Try again."
            return self._process_solution(raw, problem_name, lang)
        except Exception as e:
            log.error(f"Solve error: {e}")
            return f"Hit an error solving that: {str(e)[:80]}"

    # ═══════════════════════════════════════════════════════════
    # 3. DEBUG FROM SCREEN
    # ═══════════════════════════════════════════════════════════

    def debug_from_screen(self) -> str:
        """Read code + error from screen and identify the bug."""
        if not self._api_key:
            return "I need Gemini API to debug code."

        log.info("🐛 Reading code/error from screen for debugging...")

        try:
            image_b64 = self._screenshot_to_base64()
            analysis = self._call_gemini_vision(_DEBUG_PROMPT, image_b64)

            if not analysis or len(analysis) < 20:
                return "I couldn't read the code from your screen clearly."

            code = self._extract_code_block(analysis)
            if code:
                pyperclip.copy(code)
                log.info("🐛 Fixed code copied to clipboard")
                return (f"{analysis}\n\n"
                        "I've copied the fixed code to your clipboard. "
                        "Press Ctrl+V to paste it.")
            return analysis

        except Exception as e:
            log.error(f"Debug error: {e}")
            return "Couldn't analyze the code. Try again."

    # ═══════════════════════════════════════════════════════════
    # 4. OPTIMIZE FROM SCREEN
    # ═══════════════════════════════════════════════════════════

    def optimize_from_screen(self) -> str:
        """Read code from screen and suggest optimizations."""
        if not self._api_key:
            return "I need Gemini API to optimize code."

        log.info("⚡ Reading code from screen for optimization...")

        try:
            image_b64 = self._screenshot_to_base64()
            analysis = self._call_gemini_vision(_OPTIMIZE_PROMPT, image_b64)

            if not analysis or len(analysis) < 20:
                return "I couldn't read the code from your screen."

            code = self._extract_code_block(analysis)
            
            if code:
                pyperclip.copy(code)
                log.info("⚡ Optimized code copied to clipboard")
                return (f"{analysis}\n\n"
                        "I've copied the optimized code to your clipboard. "
                        "Press Ctrl+V to paste it.")
            return analysis

        except Exception as e:
            log.error(f"Optimize error: {e}")
            return "Couldn't analyze the code. Try again."

    # ═══════════════════════════════════════════════════════════
    # 5. EXPLAIN FROM SCREEN
    # ═══════════════════════════════════════════════════════════

    def explain_from_screen(self) -> str:
        """Read code/problem from screen and explain it."""
        if not self._api_key:
            return "I need Gemini API to explain code from the screen."

        log.info("📖 Reading code from screen for explanation...")

        try:
            image_b64 = self._screenshot_to_base64()
            analysis = self._call_gemini_vision(_EXPLAIN_SCREEN_PROMPT, image_b64)

            if not analysis or len(analysis) < 20:
                return "I couldn't read the code or problem from your screen."

            return analysis

        except Exception as e:
            log.error(f"Explain error: {e}")
            return "Couldn't analyze the screen. Try again."

    # ═══════════════════════════════════════════════════════════
    # 5. EXPLAIN LAST SOLUTION
    # ═══════════════════════════════════════════════════════════

    def explain_last(self) -> str:
        """Explain the approach of the last solved problem."""
        if not self._last_solution:
            return "I haven't solved any problem yet. Say 'solve this' first."

        return self._cached_explanation()

    def _cached_explanation(self) -> str:
        if self._last_approach:
            return (f"Approach: {self._last_approach}. "
                    f"Complexity: {self._last_complexity}.")
        return "Couldn't generate explanation right now."

    # ═══════════════════════════════════════════════════════════
    # 6. PASTE INTO EDITOR
    # ═══════════════════════════════════════════════════════════

    def paste_solution(self) -> str:
        """Paste the last solution into the active editor (LeetCode/VS Code)."""
        if not self._last_code:
            return "No solution to paste. Solve a problem first."

        try:
            pyperclip.copy(self._last_code)
            time.sleep(0.3)

            # Select all existing code first (Ctrl+A), then paste over it
            pyautogui.hotkey("ctrl", "a")
            time.sleep(0.2)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.3)

            log.info("📋 Solution pasted into editor")
            return "Solution pasted! You can submit it now."

        except Exception as e:
            log.error(f"Paste error: {e}")
            return ("Couldn't paste automatically. "
                    "The code is in your clipboard — press Ctrl+V manually.")

    # ═══════════════════════════════════════════════════════════
    # 7. GET COMPLEXITY OF LAST SOLUTION
    # ═══════════════════════════════════════════════════════════

    def get_complexity(self) -> str:
        """Return the time/space complexity of the last solution."""
        if not self._last_solution:
            return "No solution analyzed yet. Solve a problem first."
        if self._last_complexity:
            return f"The complexity is: {self._last_complexity}"
        return "I couldn't determine the complexity of the last solution."

    def show_last_solution(self) -> str:
        """Return the last solution code from memory."""
        if not self._last_code:
            return "I don't have a recent solution to show."
        return f"Here is the last solution code:\n\n```\n{self._last_code}\n```"

    def explain_last_problem(self) -> str:
        """Explain the last problem from memory."""
        if not self._last_solution:
            return "I haven't solved any problem yet. Say 'solve this' first."
        
        parts = []
        if self._last_problem_title:
            parts.append(f"Problem: {self._last_problem_title}")
        if self._last_problem_text:
            parts.append(f"Summary: {self._last_problem_text}")
            
        if parts:
            return "\n\n".join(parts)
            
        return "I remember solving a problem, but I don't have a summary of its text."

    # ═══════════════════════════════════════════════════════════
    # INTERNALS
    # ═══════════════════════════════════════════════════════════

    def _process_solution(self, raw: str, problem_id: str, language: str) -> str:
        """Parse the AI response, extract code, copy to clipboard."""
        self._last_solution = raw
        self._last_timestamp = datetime.now()

        # ── Extract problem title and text ─────────────────────
        title_match = re.search(r"PROBLEM_TITLE:\s*(.+?)(?:\n|PROBLEM_TEXT)", raw, re.IGNORECASE)
        self._last_problem_title = title_match.group(1).strip() if title_match else problem_id

        text_match = re.search(r"PROBLEM_TEXT:\s*(.+?)(?:\n|APPROACH)", raw, re.IGNORECASE | re.DOTALL)
        self._last_problem_text = text_match.group(1).strip() if text_match else ""

        # ── Extract approach ──────────────────────────────────
        approach_match = re.search(
            r"APPROACH:\s*(.+?)(?:\n|COMPLEXITY)", raw, re.IGNORECASE | re.DOTALL
        )
        self._last_approach = (
            approach_match.group(1).strip() if approach_match else ""
        )

        # ── Extract complexity ────────────────────────────────
        complexity_match = re.search(
            r"COMPLEXITY:\s*(.+?)(?:\n\n|```)", raw, re.IGNORECASE | re.DOTALL
        )
        self._last_complexity = (
            complexity_match.group(1).strip() if complexity_match else ""
        )

        # ── Extract code block ────────────────────────────────
        code = self._extract_code_block(raw)
        if not code:
            # Fallback: try to find anything that looks like code
            lines = raw.splitlines()
            code_lines = []
            in_code = False
            for line in lines:
                stripped = line.strip()
                if stripped.startswith(("def ", "class ", "import ", "from ", "#include", "using ", "public ", "package ")):
                    in_code = True
                if in_code:
                    code_lines.append(line)
            code = "\n".join(code_lines) if code_lines else ""

        self._last_code = code

        # ── Copy to clipboard ─────────────────────────────────
        if code:
            pyperclip.copy(code)
            log.info(f"✅ Solution ready ({len(code.splitlines())} lines) — copied to clipboard")

            # ── Save to history ───────────────────────────────
            self._solve_history.append({
                "problem": problem_id,
                "language": language,
                "approach": self._last_approach,
                "complexity": self._last_complexity,
                "lines": len(code.splitlines()),
                "time": datetime.now().strftime("%H:%M"),
            })

            # ── Save to Code Memory (LEARNING!) ───────────────
            if self.memory:
                try:
                    self.memory.save_solution(
                        problem_name=problem_id,
                        problem_text=self._last_problem or problem_id,
                        solution_code=code,
                        approach=self._last_approach,
                        complexity=self._last_complexity,
                        language=language,
                        source_model="gemini",
                    )
                except Exception as e:
                    log.warning(f"Couldn't save to memory: {e}")

        # ── Build spoken response ─────────────────────────────
        parts = []
        if self._last_approach:
            parts.append(f"Approach: {self._last_approach}")
        if self._last_complexity:
            parts.append(f"Complexity: {self._last_complexity}")
        if code:
            parts.append(
                f"Solution is {len(code.splitlines())} lines. "
                f"Copied to clipboard. Say 'paste it' to put it in the editor, "
                f"or 'explain' for a detailed walkthrough."
            )
        else:
            parts.append("I generated an analysis but couldn't extract clean code.")
            parts.append(raw[:300])

        return " ".join(parts)

    def _extract_code_block(self, text: str) -> str:
        """Extract code from markdown fenced code blocks."""
        # Match ```python ... ``` or ```java ... ``` etc.
        pattern = r"```(?:\w+)?\s*\n(.*?)```"
        matches = re.findall(pattern, text, re.DOTALL)
        if matches:
            code = max(matches, key=len).strip()
            # Clean up duplicated boilerplate if Gemini repeats it in a single block
            code = re.sub(r'(class \w+:\n\s*def \w+\([^)]+\)[^:]*:\n(?:\s*pass\n)?)(?=class \w+:)', '', code)
            return code

        # Try without language tag
        pattern2 = r"```\s*\n(.*?)```"
        matches2 = re.findall(pattern2, text, re.DOTALL)
        if matches2:
            code = max(matches2, key=len).strip()
            code = re.sub(r'(class \w+:\n\s*def \w+\([^)]+\)[^:]*:\n(?:\s*pass\n)?)(?=class \w+:)', '', code)
            return code

        return ""

    def get_history(self) -> str:
        """Return a summary of recently solved problems."""
        if not self._solve_history:
            return "No problems solved yet this session."
        recent = self._solve_history[-5:]
        parts = []
        for h in recent:
            parts.append(
                f"  {h['problem'][:40]} — {h['complexity']} "
                f"({h['lines']} lines, {h['time']})"
            )
        return "Recently solved:\n" + "\n".join(parts)


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    ps = ProblemSolver()
    print("ProblemSolver initialized OK")
    print(ps.get_history())

