"""
JARVIS — skills/code_runner.py
Code Runner — generate and execute code by voice.

Flow:
  "Write a Python script to list all files in Downloads"
       ↓ JARVIS generates code
       ↓ Shows the code
       ↓ Asks: "Should I run it?"
       ↓ Runs safely with timeout + sandbox
       ↓ Reports output

File Creation:
  "Create main.py with a hello world program"      → creates main.py on Desktop
  "Create hello.cpp with a basic C++ program"      → creates hello.cpp on Desktop
  "Write index.html with a simple webpage"         → creates index.html on Desktop
  "Create calculator.py on Desktop"                → creates there
  "Create app.js in my projects folder"            → creates there

Safety:
  - Sandboxed subprocess (isolated from JARVIS process)
  - 30-second timeout (no infinite loops)
  - Dangerous command detection (blocks rm, del, format, etc.)
  - Output size limit (no flooding)
  - User confirmation required before execution
"""

import os
import re
import sys
import subprocess
import threading
from datetime import datetime
from utils.logger import log

# Default save location
DESKTOP     = os.path.join(os.path.expanduser("~"), "Desktop")
DOCUMENTS   = os.path.join(os.path.expanduser("~"), "Documents")
DOWNLOADS   = os.path.join(os.path.expanduser("~"), "Downloads")
_CODE_DIR   = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "code_runs")

# Language → file extension mapping
LANG_TO_EXT = {
    "python": ".py",    "py": ".py",
    "javascript": ".js", "js": ".js",
    "html": ".html",    "webpage": ".html",   "web": ".html",
    "css": ".css",
    "cpp": ".cpp",      "c++": ".cpp",
    "c": ".c",
    "java": ".java",
    "typescript": ".ts", "ts": ".ts",
    "json": ".json",
    "yaml": ".yaml",    "yml": ".yml",
    "sql": ".sql",
    "bash": ".sh",      "shell": ".sh",
    "text": ".txt",     "txt": ".txt",
    "markdown": ".md",  "md": ".md",
}

# Language → how to run it
LANG_RUNNERS = {
    ".py":   [sys.executable],
    ".js":   ["node"],
    ".sh":   ["bash"],
}

# DANGEROUS commands that are NEVER allowed
BLOCKED_PATTERNS = [
    r"\brm\s+-rf\b",
    r"\bdel\s+/[fqs]",
    r"\bformat\s+[a-z]:",
    r"\bshutdown\b",
    r"\brestart\b",
    r"\bregdel\b",
    r"\brmdir\s+/s",
    r"os\.system\(['\"].*rm",
    r"subprocess.*rm\s+-rf",
    r"\bos\.remove\(.*\*",
    r"shutil\.rmtree\(",
    r"glob.*\*.*os\.remove",
]

# Code generation prompts by language
CODE_PROMPTS = {
    ".py": """Write a clean Python script to: {task}
Rules: short, working, use only stdlib, print results, handle errors.
Return ONLY code, no explanation.""",

    ".html": """Write a clean HTML page for: {task}
Rules: complete HTML5 document, inline CSS for styling, modern look.
Return ONLY the HTML code.""",

    ".js": """Write clean JavaScript code for: {task}
Rules: short, working, use console.log for output.
Return ONLY code.""",

    ".cpp": """Write a clean C++ program for: {task}
Rules: short, compilable, include necessary headers, use cout.
Return ONLY code.""",

    ".java": """Write a clean Java program for: {task}
Rules: single public class, include main method, use System.out.println.
Return ONLY code.""",

    ".css": """Write clean CSS for: {task}
Rules: modern, clean styles, include comments.
Return ONLY CSS code.""",

    ".sql": """Write a SQL query for: {task}
Rules: standard SQL, include comments explaining each part.
Return ONLY SQL code.""",

    "default": """Write code for: {task}
Rules: short, clean, working. Return ONLY the code.""",
}


class CodeRunner:
    """Generates, saves, and executes code by voice command."""

    def __init__(self):
        self._last_code     = ""
        self._last_task     = ""
        self._last_filepath = ""
        self._last_ext      = ".py"
        self._pending_confirmation = False
        self._execution_history = []
        os.makedirs(_CODE_DIR, exist_ok=True)
        log.info("CodeRunner ready ✅")

    # ═══════════════════════════════════════════════════════════
    # FILE CREATION
    # ═══════════════════════════════════════════════════════════

    def create_file(self, text: str, llm) -> str:
        """
        Parse voice command and create a named file with generated code.
        Examples:
          "Create main.py with a hello world program"
          "Create hello.cpp with a basic C++ program"
          "Write index.html with a simple webpage"
          "Create calculator.py in Documents"
        """
        filename, save_dir, task, ext = self._parse_file_command(text)

        log.info(f"Creating file: {filename} | Task: {task} | Dir: {save_dir}")
        self._last_task = task
        self._last_ext  = ext

        # Generate code in the right language
        prompt_template = CODE_PROMPTS.get(ext, CODE_PROMPTS["default"])
        prompt = prompt_template.format(task=task)

        self._speak_fn = None  # Will be set externally
        code = llm.ask(prompt)
        code = self._extract_code(code, ext)

        if not code or len(code) < 5:
            return f"Couldn't generate code for {filename}. Try being more specific."

        # Safety check (only for executable files)
        if ext in [".py", ".js", ".sh"]:
            blocked = self._safety_check(code)
            if blocked:
                return f"Generated code has dangerous operations. Not saving."

        # Build full path
        filepath = os.path.join(save_dir, filename)
        self._last_filepath = filepath
        self._last_code     = code

        # Save the file
        try:
            os.makedirs(save_dir, exist_ok=True)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(code)
            log.info(f"File saved: {filepath}")
        except Exception as e:
            return f"Couldn't save {filename}: {e}"

        # Display
        self._display_code(code, f"{filename} — {task}", filepath)

        # Ask if should run (only for runnable files)
        if ext in LANG_RUNNERS:
            self._pending_confirmation = True
            return (f"{filename} created on your {os.path.basename(save_dir)}. "
                    f"Say 'run it' to execute it.")
        else:
            return f"{filename} created on your {os.path.basename(save_dir)}."

    def _parse_file_command(self, text: str):
        """
        Parse: "create main.py with a hello world program"
        Returns: (filename, save_dir, task, extension)
        """
        t = text.lower().strip()

        # ── Find filename ────────────────────────────────────
        # Look for a word with a file extension
        filename_match = re.search(
            r'\b([\w\-]+\.(py|js|html|css|cpp|c|java|ts|json|yaml|yml|sql|sh|txt|md|csv))\b',
            t, re.IGNORECASE
        )

        if filename_match:
            filename = filename_match.group(1)
            ext = "." + filename_match.group(2).lower()
        else:
            # No extension found — guess from language words
            ext = self._guess_extension(t)
            filename = f"jarvis_{datetime.now().strftime('%H%M%S')}{ext}"

        # ── Find save location ────────────────────────────────
        save_dir = DESKTOP  # Default: Desktop
        if "document" in t:
            save_dir = DOCUMENTS
        elif "download" in t:
            save_dir = DOWNLOADS
        elif "desktop" in t:
            save_dir = DESKTOP
        elif "project" in t:
            save_dir = DESKTOP  # Could be extended

        # ── Extract task description ──────────────────────────
        # Remove command words to get the actual task
        stop_words = [
            "create", "make", "write", "generate", "build",
            "with", "that", "in documents", "in downloads",
            "on desktop", "in my", "for me", "please",
            filename.lower(),
        ]
        task = t
        for word in stop_words:
            # Use word boundary replacement to avoid stripping letters from words
            task = re.sub(r'\b' + re.escape(word) + r'\b', ' ', task)

        # Clean up multiple spaces
        task = re.sub(r'\s+', ' ', task).strip()

        # Add language context to task if missing
        lang_name = self._ext_to_lang(ext)
        if lang_name and lang_name.lower() not in task.lower():
            task = f"{task} (in {lang_name})"

        if not task or len(task) < 3:
            task = f"a simple {self._ext_to_lang(ext)} program"

        return filename, save_dir, task, ext

    def _guess_extension(self, text: str) -> str:
        """Guess file extension from language words in text."""
        for lang, ext in LANG_TO_EXT.items():
            if lang in text:
                return ext
        return ".py"  # Default to Python

    def _ext_to_lang(self, ext: str) -> str:
        """Convert extension to language name."""
        mapping = {
            ".py": "Python", ".js": "JavaScript", ".html": "HTML",
            ".css": "CSS", ".cpp": "C++", ".java": "Java",
            ".ts": "TypeScript", ".sql": "SQL", ".sh": "Bash",
        }
        return mapping.get(ext, "code")

    # ═══════════════════════════════════════════════════════════
    # GENERATE + RUN (original flow)
    # ═══════════════════════════════════════════════════════════

    def generate_and_ask(self, task: str, llm) -> str:
        """Generate Python code for a task and ask for confirmation."""
        self._last_task = task
        self._last_ext  = ".py"
        log.info(f"Generating code for: '{task}'")

        prompt = CODE_PROMPTS[".py"].format(task=task)
        code   = llm.ask(prompt)
        code   = self._extract_code(code, ".py")

        if not code or len(code) < 10:
            return "Couldn't generate code for that. Try being more specific."

        blocked = self._safety_check(code)
        if blocked:
            return "That code has dangerous operations. I won't run it."

        self._last_code = code
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._last_filepath = os.path.join(_CODE_DIR, f"jarvis_run_{timestamp}.py")
        self._pending_confirmation = True

        self._display_code(code, task)
        return "I wrote the code. Say 'run it' to execute, or 'show me the code' to see it."

    def confirm_and_run(self) -> str:
        """Run the pending code after confirmation."""
        if not self._last_code:
            return "No code to run. Ask me to write something first."
        if not self._pending_confirmation:
            return "Nothing pending. Ask me to write code first."
        self._pending_confirmation = False
        return self._execute(self._last_code, self._last_task, self._last_filepath, self._last_ext)

    def show_last_code(self) -> str:
        """Show the last generated code."""
        if not self._last_code:
            return "No code generated yet."
        self._display_code(self._last_code, self._last_task, self._last_filepath)
        return f"Here's the code. Saved at: {self._last_filepath}"

    def run_last_code(self) -> str:
        """Re-run the last code."""
        if not self._last_code:
            return "No code to run yet."
        return self._execute(self._last_code, self._last_task, self._last_filepath, self._last_ext)

    def cancel(self) -> str:
        self._pending_confirmation = False
        return "Cancelled."

    def get_history(self) -> str:
        if not self._execution_history:
            return "No code runs yet."
        last = self._execution_history[-3:]
        parts = []
        for h in last:
            status = "OK" if h["success"] else "failed"
            parts.append(f"{h['task'][:30]} — {status}")
        return " | ".join(parts)

    # ═══════════════════════════════════════════════════════════
    # EXECUTION ENGINE
    # ═══════════════════════════════════════════════════════════

    def _execute(self, code: str, task: str, filepath: str = None, ext: str = ".py") -> str:
        """Execute code safely in subprocess."""
        log.info(f"Executing: '{task}'")

        # Save to file if not already saved
        if not filepath:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath  = os.path.join(_CODE_DIR, f"jarvis_run_{timestamp}{ext}")

        try:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(code)
        except Exception as e:
            return f"Couldn't save file: {e}"

        # Get runner for this extension
        runner = LANG_RUNNERS.get(ext)
        if not runner:
            return f"File saved at {filepath}. I can't execute {ext} files directly."

        try:
            result = subprocess.run(
                runner + [filepath],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=os.path.dirname(filepath),
            )

            stdout = result.stdout.strip()
            stderr = result.stderr.strip()
            success = result.returncode == 0

            self._execution_history.append({
                "task": task, "file": filepath,
                "success": success, "output": stdout[:200],
                "time": datetime.now().isoformat()
            })

            if success:
                output = stdout[:300] + ("..." if len(stdout) > 300 else "")
                return f"Done. Output: {output}" if output else "Code ran with no output."
            else:
                return f"Error: {self._clean_error(stderr)}"

        except subprocess.TimeoutExpired:
            return "Code timed out after 30 seconds."
        except FileNotFoundError:
            return f"Runner not found for {ext}. Make sure the required tool is installed."
        except Exception as e:
            return f"Execution failed: {str(e)[:100]}"

    # ═══════════════════════════════════════════════════════════
    # HELPERS
    # ═══════════════════════════════════════════════════════════

    def _safety_check(self, code: str) -> str:
        code_lower = code.lower()
        for pattern in BLOCKED_PATTERNS:
            if re.search(pattern, code_lower):
                return pattern
        return ""

    def _extract_code(self, raw: str, ext: str = ".py") -> str:
        """Extract clean code from LLM response."""
        if not raw:
            return ""

        # Strip markdown fences
        raw = re.sub(r"```[\w]*\s*", "", raw)
        raw = re.sub(r"```\s*", "", raw)

        # For non-Python, return stripped directly
        if ext != ".py":
            return raw.strip()

        # For Python: find start of actual code
        lines = raw.strip().splitlines()
        code_lines = []
        in_code = False
        for line in lines:
            stripped = line.strip()
            if not in_code:
                if any(stripped.startswith(k) for k in
                       ["#", "import", "from", "def ", "class ", "print",
                        "for ", "if ", "with ", "try:", "while "]) or "=" in stripped:
                    in_code = True
            if in_code:
                code_lines.append(line)

        return "\n".join(code_lines).strip()

    def _clean_error(self, stderr: str) -> str:
        if not stderr:
            return "Unknown error"
        lines = stderr.strip().splitlines()
        for line in reversed(lines):
            if line.strip() and not line.strip().startswith("File "):
                return line.strip()[:150]
        return lines[-1][:150] if lines else "Unknown error"

    def _display_code(self, code: str, task: str, filepath: str = ""):
        print("\n" + "═" * 60)
        print(f"  📝 {task}")
        if filepath:
            print(f"  💾 Saved: {filepath}")
        print("═" * 60)
        print(code)
        print("═" * 60 + "\n")


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    runner = CodeRunner()

    # Test file name parsing
    tests = [
        "create main.py with a hello world program",
        "create hello.cpp with a basic C++ program",
        "write index.html with a simple webpage",
        "make calculator.py that adds two numbers",
        "create app.js with a simple server",
        "create notes.txt with some sample text",
    ]

    print("=== File parsing tests ===")
    for t in tests:
        filename, save_dir, task, ext = runner._parse_file_command(t)
        print(f"  '{t}'")
        print(f"    → file: {filename} | dir: {os.path.basename(save_dir)} | task: {task}")
        print()
