"""
JARVIS — skills/code_writer.py
VS Code Integration — opens VS Code and writes AI-generated code by voice.

Full workflow:
  1. User says "write a Python function to reverse a string"
  2. JARVIS asks "What should I name the file?"
  3. User says "reverse_string.py"
  4. JARVIS generates code via Gemini
  5. Opens VS Code with the file
  6. Types code line-by-line with animation
  7. Asks "Want me to run it?"

Handles:
  - Auto-detecting VS Code on Windows
  - Opening VS Code with a specific file
  - Typing code with animation (clipboard paste per line — safe for all chars)
  - Running the written file
  - Language auto-detection from task or filename
  - Gemini-powered code generation with rich prompts
"""

import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pyautogui
import pyperclip

from utils.logger import log

pyautogui.FAILSAFE = False  # Prevent corner-mouse crashes during typing

# ─── Defaults ────────────────────────────────────────────────
DESKTOP = Path.home() / "Desktop"
JARVIS_CODE_DIR = Path.home() / "Desktop" / "JARVIS_Code"

# Language → extension
LANG_EXT = {
    "python": ".py",
    "javascript": ".js",
    "typescript": ".ts",
    "java": ".java",
    "cpp": ".cpp",
    "c++": ".cpp",
    "c": ".c",
    "csharp": ".cs",
    "c#": ".cs",
    "go": ".go",
    "rust": ".rs",
    "ruby": ".rb",
    "php": ".php",
    "html": ".html",
    "css": ".css",
    "react": ".jsx",
    "vue": ".vue",
    "sql": ".sql",
    "bash": ".sh",
    "shell": ".sh",
    "kotlin": ".kt",
    "swift": ".swift",
    "r": ".r",
    "matlab": ".m",
    "markdown": ".md",
    "json": ".json",
    "yaml": ".yaml",
}

# Extension → language name (for display)
EXT_LANG = {v: k.title() for k, v in LANG_EXT.items()}
EXT_LANG[".py"] = "Python"
EXT_LANG[".js"] = "JavaScript"
EXT_LANG[".ts"] = "TypeScript"
EXT_LANG[".cpp"] = "C++"
EXT_LANG[".jsx"] = "React (JSX)"
EXT_LANG[".html"] = "HTML"
EXT_LANG[".sh"] = "Bash"

# How to run each extension
# NOTE: sys.executable may contain spaces (e.g. C:\Program Files\Python310\python.exe)
# subprocess.run() with a list handles this correctly — no quoting needed.
# For string-based CMD commands (VS Code terminal), use _quote_runner().
_PY = sys.executable  # e.g. C:\Program Files\Python310\python.exe
RUNNERS = {
    ".py": [_PY],
    ".js": ["node"],
    ".sh": ["bash"],
    ".ts": ["npx", "ts-node"],
    ".rb": ["ruby"],
    ".php": ["php"],
    ".go": ["go", "run"],
}


def _quote_runner(runner_parts: list) -> str:
    """Build a shell-safe command string. Quotes any part that contains spaces."""
    parts = []
    for part in runner_parts:
        if " " in str(part):
            parts.append(f'"{part}"')
        else:
            parts.append(str(part))
    return " ".join(parts)

# ─── Code generation prompts ──────────────────────────────────
_CODE_PROMPT = """You are an expert {language} programmer.

Task: {task}

Critical requirements:
- Write COMPLETE, fully working code — not a skeleton, not a stub
- Include ALL imports at the top
- If using any library (pygame, tkinter, requests, etc.) import it properly
- The code must run from top to bottom without modification
- Add clear comments explaining key sections
- Include error handling where appropriate
- For games: include the full game loop, event handling, rendering, and score
- For apps: include all UI, logic, and data handling
- For scripts: handle edge cases and print useful output
- Add a docstring at the top describing what the program does

Respond with ONLY the raw {language} code.
No markdown fences, no triple backticks, no explanation before or after.
Just pure code that can be saved directly to a .{ext} file and run immediately."""

_GAME_PROMPT = """You are an expert {language} game developer.

Task: Build a complete, fully playable {task}

Requirements:
- Write the ENTIRE game — every function, every class, every line
- Include ALL imports (pygame, sys, random, etc.)
- Full game loop with: event handling, update logic, rendering
- Proper pygame.init() and pygame.quit() calls
- Window with a sensible size (e.g. 600x600 or 800x600)
- Score display on screen
- Game over screen with restart option
- Smooth controls and clean gameplay
- Comments explaining each major section
- if __name__ == '__main__': block to start the game

Respond with ONLY the raw Python code.
No markdown fences, no triple backticks, no explanation.
Just pure complete Python code ready to run."""

_COMPLEX_PROMPT = """You are a senior {language} software engineer.

Task: {task}

ARCHITECTURE RULES — follow these exactly:
{architecture}

Coding standards:
- Write COMPLETE, production-quality code — every function fully implemented
- ALL imports at the top
- Proper error handling with try/except on every network/IO call
- Clear comments on every major block
- if __name__ == '__main__': entry point
- Code must run immediately without any edits

Respond with ONLY raw {language} code.
No markdown fences (```), no backticks, no explanation text.
Just pure executable code."""

# Architecture rules injected per task type
_ARCH_NETWORK = """
- Structure: ONE file with two clearly separated sections
  SECTION 1 — SERVER: all server code under `def run_server():`
  SECTION 2 — CLIENT: all client code under `def run_client():`
  SECTION 3 — MAIN: `if __name__ == '__main__':` checks sys.argv[1] == 'server' or 'client'
- Use threading.Thread for each client connection in the server
- Use a shared `clients = []` list protected by `threading.Lock()`
- Client reads from socket in a background thread; main thread handles input()
- Do NOT mix server and client loops — they must be completely separate functions
- Run instructions in the docstring: `python file.py server` and `python file.py client`"""

_ARCH_GUI = """
- Use tkinter for the GUI (no extra install needed)
- All widgets created in __init__ of a main App class
- Separate methods for each action (add, delete, save, load)
- Data persisted to a JSON file in the same directory
- Clean layout using .grid() or .pack() with proper padding"""

_ARCH_ML = """
- Use only numpy (no sklearn, no tensorflow) unless task specifies otherwise
- Clear separation: data loading → preprocessing → model → training → evaluation
- Print accuracy and loss at each epoch
- Save/load model weights to a .npy file
- Include a demo prediction at the end"""

_ARCH_DATA = """
- Read data from CSV or generate sample data if no file specified
- Use pandas for data manipulation, matplotlib for charts
- Each analysis in a separate function
- Save charts as PNG files
- Print a summary table to console"""

_EXPLAIN_PROMPT = """In exactly 2 sentences, explain what this code does:

{code}

Be concise and speak naturally as if explaining to the developer."""

# Keywords that signal a full application/game (use richer prompt)
_APP_KEYWORDS = {
    "game",
    "snake",
    "tetris",
    "chess",
    "checkers",
    "pong",
    "pacman",
    "breakout",
    "asteroids",
    "platformer",
    "shooter",
    "puzzle",
    "quiz",
    "app",
    "application",
    "dashboard",
    "gui",
    "interface",
    "window",
    "chat",
    "messenger",
    "todo",
    "tracker",
    "manager",
    "system",
    "simulation",
    "visualizer",
    "visualisation",
    "visualization",
    "website",
    "webpage",
    "server",
    "api",
    "scraper",
    "crawler",
    "bot",
    "downloader",
    "player",
    "editor",
    "recorder",
    "calculator",
}


class VSCodeWriter:
    """
    Opens VS Code and writes AI-generated code by voice command.
    Requires: VS Code installed, pyautogui, pyperclip, gemini_handler.
    """

    def __init__(self, gemini_handler=None):
        """
        Args:
            gemini_handler: GeminiHandler instance for code + explanation generation.
        """
        self.gemini = gemini_handler
        self._vscode_exe = self._find_vscode()
        self._last_filepath = ""
        self._last_code = ""
        self._last_language = "Python"
        self._pending_run = False
        JARVIS_CODE_DIR.mkdir(parents=True, exist_ok=True)
        log.info(f"VSCodeWriter ready ✅ (VS Code: {self._vscode_exe})")

    # ═══════════════════════════════════════════════════════════
    # VS CODE FINDER
    # ═══════════════════════════════════════════════════════════

    def _find_vscode(self) -> str:
        """
        Locate the VS Code executable on Windows.
        Returns the path string or 'code' if found in PATH.
        """
        # Check if 'code' is in PATH (simplest case)
        try:
            result = subprocess.run(
                ["code", "--version"],
                capture_output=True,
                timeout=4,
                shell=True,  # Required on Windows for PATH commands
            )
            if result.returncode == 0:
                log.info("VS Code found in PATH ✅")
                return "code"
        except Exception:
            pass

        # Check known Windows install locations
        username = os.environ.get("USERNAME", "")
        candidates = [
            Path(
                f"C:/Users/{username}/AppData/Local/Programs/Microsoft VS Code/Code.exe"
            ),
            Path("C:/Program Files/Microsoft VS Code/Code.exe"),
            Path("C:/Program Files (x86)/Microsoft VS Code/Code.exe"),
            Path(f"C:/Users/{username}/scoop/apps/vscode/current/Code.exe"),
        ]

        for path in candidates:
            if path.exists():
                log.info(f"VS Code found: {path} ✅")
                return str(path)

        log.warning("VS Code not found — will try 'code' and hope for the best.")
        return "code"

    def is_vscode_available(self) -> bool:
        """Return True if VS Code can be launched."""
        return self._vscode_exe != "" and (
            self._vscode_exe == "code" or Path(self._vscode_exe).exists()
        )

    # ═══════════════════════════════════════════════════════════
    # LANGUAGE & FILENAME HELPERS
    # ═══════════════════════════════════════════════════════════

    def detect_language(self, text: str, filename: str = "") -> str:
        """
        Auto-detect programming language from task description or filename.
        Returns language name string e.g. "Python", "JavaScript".
        """
        # From filename extension
        if filename:
            ext = Path(filename).suffix.lower()
            if ext in EXT_LANG:
                return EXT_LANG[ext]

        text_lower = text.lower()

        # Ordered by specificity (longer/more specific first)
        ordered = sorted(LANG_EXT.keys(), key=len, reverse=True)
        for lang in ordered:
            # For short language names (c, r, go), require word boundaries
            # to prevent matching inside English words like "create", "for", "ago"
            if len(lang) <= 2:
                if re.search(rf"\b{re.escape(lang)}\b", text_lower):
                    return lang.title().replace("Cpp", "C++").replace("Csharp", "C#")
            else:
                if lang in text_lower:
                    return lang.title().replace("Cpp", "C++").replace("Csharp", "C#")

        # Framework/library → language mappings (before heuristic defaults)
        framework_map = {
            "pygame": "Python", "tkinter": "Python", "flask": "Python",
            "django": "Python", "fastapi": "Python", "numpy": "Python",
            "pandas": "Python", "opencv": "Python", "tensorflow": "Python",
            "pytorch": "Python", "requests": "Python", "beautifulsoup": "Python",
            "selenium": "Python", "scrapy": "Python", "matplotlib": "Python",
            "express": "JavaScript", "nodejs": "JavaScript", "node.js": "JavaScript",
            "angular": "TypeScript", "vue": "Javascript",
        }
        for fw, lang in framework_map.items():
            if fw in text_lower:
                return lang

        # Heuristic defaults
        if any(
            w in text_lower for w in ["function", "def ", "script", "flask", "django"]
        ):
            return "Python"
        if any(w in text_lower for w in ["component", "jsx", "hook", "props"]):
            return "React"
        if any(w in text_lower for w in ["webpage", "website", "page", "form"]):
            return "HTML"

        return "Python"  # Safe default

    def suggest_filename(self, task: str, language: str) -> str:
        """
        Suggest a snake_case filename from the task description.
        E.g. "reverse a string" → "reverse_string.py"
        """
        # Strip noise words
        noise = {
            "write",
            "create",
            "make",
            "build",
            "a",
            "an",
            "the",
            "function",
            "that",
            "to",
            "for",
            "in",
            "with",
            "using",
            "program",
            "script",
            "code",
            "class",
            "method",
        }
        words = [
            w
            for w in re.sub(r"[^\w\s]", "", task.lower()).split()
            if w not in noise and len(w) > 2
        ][:4]  # Max 4 words

        base = "_".join(words) if words else "jarvis_code"
        ext = LANG_EXT.get(
            language.lower().replace("+", "p").replace("#", "sharp"), ".py"
        )
        return f"{base}{ext}"

    def _ext_from_language(self, language: str) -> str:
        """Get file extension for a language name."""
        key = language.lower().replace("+", "p").replace("#", "sharp").replace(" ", "")
        return LANG_EXT.get(key, ".py")

    # ═══════════════════════════════════════════════════════════
    # CODE GENERATION
    # ═══════════════════════════════════════════════════════════

    def _is_app_or_game(self, task: str) -> bool:
        """Return True if the task describes a full application or game."""
        task_lower = task.lower()
        return any(kw in task_lower for kw in _APP_KEYWORDS)

    def generate_code(self, task: str, language: str) -> tuple:
        """
        Generate code using Gemini AI.

        Automatically selects the right prompt for the task type:
          - Network/socket/chat  → _COMPLEX_PROMPT + _ARCH_NETWORK
          - GUI/tkinter app      → _COMPLEX_PROMPT + _ARCH_GUI
          - ML/neural network    → _COMPLEX_PROMPT + _ARCH_ML
          - Data/chart/analysis  → _COMPLEX_PROMPT + _ARCH_DATA
          - Game/pygame          → _GAME_PROMPT
          - Everything else      → _CODE_PROMPT

        Returns:
            (code: str, explanation: str)
        """
        if not self.gemini:
            log.warning("No Gemini handler — using template fallback")
            return self._template_code(task, language), ""

        ext = self._ext_from_language(language).lstrip(".")
        task_lower = task.lower()

        # ── Detect task type ─────────────────────────────────────
        is_game = any(w in task_lower for w in [
            "game", "snake", "tetris", "chess", "pong", "pacman",
            "breakout", "asteroids", "platformer", "shooter", "puzzle",
        ])
        is_network = any(w in task_lower for w in [
            "socket", "chat", "server", "client", "networking",
            "real-time", "realtime", "broadcast", "messenger", "tcp", "udp",
        ])
        is_gui = any(w in task_lower for w in [
            "gui", "tkinter", "window", "form", "desktop app",
            "interface", "dashboard", "todo app", "expense tracker",
            "library management", "student", "manager",
        ])
        is_ml = any(w in task_lower for w in [
            "neural network", "machine learning", "train", "predict",
            "classifier", "regression", "deep learning", "mnist", "numpy nn",
        ])
        is_data = any(w in task_lower for w in [
            "csv", "pandas", "chart", "matplotlib", "plot", "analysis",
            "statistics", "data", "visualize", "bar chart", "graph",
        ])

        # ── Select prompt ─────────────────────────────────────────
        if is_game and language.lower() == "python":
            prompt = _GAME_PROMPT.format(language=language, task=task)
            prompt_type = "game"
        elif is_network:
            prompt = _COMPLEX_PROMPT.format(
                language=language, task=task, architecture=_ARCH_NETWORK
            )
            prompt_type = "network"
        elif is_gui:
            prompt = _COMPLEX_PROMPT.format(
                language=language, task=task, architecture=_ARCH_GUI
            )
            prompt_type = "gui"
        elif is_ml:
            prompt = _COMPLEX_PROMPT.format(
                language=language, task=task, architecture=_ARCH_ML
            )
            prompt_type = "ml"
        elif is_data:
            prompt = _COMPLEX_PROMPT.format(
                language=language, task=task, architecture=_ARCH_DATA
            )
            prompt_type = "data"
        else:
            prompt = _CODE_PROMPT.format(language=language, task=task, ext=ext)
            prompt_type = "standard"

        log.info(f"Generating {language} code [{prompt_type}]: {task}")

        try:
            raw = self.gemini.ask(prompt)
            code = self._clean_code(raw)

            if not code or len(code) < 10:
                log.warning("Generated code too short — using template")
                return self._template_code(task, language), ""

            # ── Validate: retry if obviously broken ──────────────
            issues = self._detect_code_issues(code, prompt_type)
            if issues:
                log.warning(f"Code issues detected: {issues} — retrying with correction")
                fix_prompt = (
                    f"The following {language} code has issues: {issues}\n\n"
                    f"REWRITE it completely, fixing those issues.\n"
                    f"Original task: {task}\n\n"
                    f"{prompt}\n\n"
                    f"Broken code to fix:\n{code[:2000]}"
                )
                raw2 = self.gemini.ask(fix_prompt)
                code2 = self._clean_code(raw2)
                if code2 and len(code2) > len(code):
                    log.info("Retry produced better code — using retry result")
                    code = code2

            # ── Minimum length check for games ───────────────────
            if is_game and len(code.splitlines()) < 40:
                log.warning(f"Game code too short ({len(code.splitlines())} lines) — retrying")
                raw2 = self.gemini.ask(prompt)
                code2 = self._clean_code(raw2)
                if code2 and len(code2.splitlines()) > len(code.splitlines()):
                    code = code2

            explanation = self._generate_explanation(code)
            return code, explanation

        except Exception as e:
            log.error(f"Code generation error: {e}")
            return self._template_code(task, language), ""

    def _detect_code_issues(self, code: str, prompt_type: str) -> str:
        """
        Quick sanity check on generated code.
        Returns a string describing issues found, or empty string if clean.
        """
        issues = []

        if prompt_type == "network":
            # Must have both server and client functions
            if "def run_server" not in code and "def server" not in code:
                issues.append("missing run_server() function")
            if "def run_client" not in code and "def client" not in code:
                issues.append("missing run_client() function")
            # Must use threading for clients
            if "threading" not in code:
                issues.append("missing threading for concurrent clients")
            # Should use sys.argv to pick mode
            if "sys.argv" not in code:
                issues.append("missing sys.argv mode selection (server/client)")

        elif prompt_type == "game":
            if "pygame.init" not in code:
                issues.append("missing pygame.init()")
            if "while" not in code:
                issues.append("missing game loop")
            if "pygame.display" not in code:
                issues.append("missing display update")

        elif prompt_type == "gui":
            if "tkinter" not in code and "tk" not in code.lower():
                issues.append("missing tkinter import")

        elif prompt_type == "ml":
            if "import numpy" not in code and "import torch" not in code:
                issues.append("missing numpy/torch import")

        return "; ".join(issues)


    def _generate_explanation(self, code: str) -> str:
        """Ask Gemini for a 2-sentence spoken explanation of the code."""
        if not self.gemini:
            return ""
        try:
            prompt = _EXPLAIN_PROMPT.format(code=code[:1500])
            raw = (
                self.gemini.ask_quick(prompt)
                if hasattr(self.gemini, "ask_quick")
                else self.gemini.ask(prompt)
            )
            return raw.strip()
        except Exception:
            return ""

    def _clean_code(self, raw: str) -> str:
        """
        Strip markdown fences and leading/trailing noise from LLM output.
        Handles edge cases like triple backticks mid-response,
        'Here is the code:' preambles, and trailing explanations.
        """
        if not raw:
            return ""

        # Remove ``` fences (with or without language tag)
        raw = re.sub(r"^```[\w+#]*\s*", "", raw.strip(), flags=re.MULTILINE)
        raw = re.sub(r"^```\s*$", "", raw, flags=re.MULTILINE)

        lines = raw.strip().splitlines()

        # Drop leading noise lines (preamble before actual code)
        # e.g. "Here is the complete Snake game:", "Sure! Here's the code:"
        noise_prefixes = (
            "here",
            "sure",
            "certainly",
            "of course",
            "below",
            "the following",
            "this",
            "i've",
            "i have",
            "as requested",
            "```",
        )
        while lines and (
            not lines[0].strip()
            or lines[0].strip().lower().startswith(noise_prefixes)
            and not lines[0].strip().startswith(("import", "from", "#", "class", "def"))
        ):
            lines.pop(0)

        # Drop trailing blank lines and trailing explanation paragraphs
        # (LLMs sometimes add "This code does X..." after the code block)
        while lines and not lines[-1].strip():
            lines.pop()

        # If the last few lines look like an explanation paragraph (no code),
        # trim them off — they start with English sentences, not code
        while lines and (
            lines[-1].strip()
            and not lines[-1]
            .strip()
            .startswith(
                (
                    "#",
                    "}",
                    ")",
                    "]",
                    '"""',
                    "'''",
                    "pass",
                    "return",
                    "print",
                    "pygame",
                    "if ",
                    "else",
                    "elif ",
                    "for ",
                    "while ",
                    "class ",
                    "def ",
                    "import ",
                    "from ",
                    "    ",
                )
            )
            and len(lines[-1].strip().split()) > 4  # Long English sentence
            and not any(c in lines[-1] for c in ["=", "(", ":", "[", "{"])
        ):
            lines.pop()

        return "\n".join(lines)

    def _template_code(self, task: str, language: str) -> str:
        """Return a minimal template when AI is unavailable."""
        task_lower = task.lower()
        # Special template for Snake game so it's always runnable even without AI
        if "snake" in task_lower and language.lower() == "python":
            return '''\
"""
Snake Game — built by JARVIS
Controls: Arrow keys to move | Q to quit | R to restart
"""
import pygame
import random
import sys

# ── Constants ─────────────────────────────────────────────────
WIDTH, HEIGHT = 600, 600
CELL = 20
COLS, ROWS = WIDTH // CELL, HEIGHT // CELL
FPS = 10

BLACK  = (0,   0,   0)
GREEN  = (0,   200, 0)
DGREEN = (0,   140, 0)
RED    = (220, 0,   0)
WHITE  = (255, 255, 255)
GRAY   = (40,  40,  40)

UP, DOWN, LEFT, RIGHT = (0, -1), (0, 1), (-1, 0), (1, 0)


def draw_cell(surface, col, row, color, border=DGREEN):
    rect = pygame.Rect(col * CELL, row * CELL, CELL, CELL)
    pygame.draw.rect(surface, color, rect)
    pygame.draw.rect(surface, border, rect, 1)


def random_food(snake):
    while True:
        pos = (random.randint(0, COLS - 1), random.randint(0, ROWS - 1))
        if pos not in snake:
            return pos


def run_game():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Snake — JARVIS")
    clock  = pygame.time.Clock()
    font   = pygame.font.SysFont("consolas", 22, bold=True)
    big    = pygame.font.SysFont("consolas", 40, bold=True)

    snake     = [(COLS // 2, ROWS // 2)]
    direction = RIGHT
    food      = random_food(snake)
    score     = 0
    running   = True
    game_over = False

    while running:
        clock.tick(FPS)

        # ── Events ────────────────────────────────────────────
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_q:
                    running = False
                elif event.key == pygame.K_r and game_over:
                    run_game()          # Restart
                    return
                elif not game_over:
                    if event.key == pygame.K_UP    and direction != DOWN:
                        direction = UP
                    elif event.key == pygame.K_DOWN  and direction != UP:
                        direction = DOWN
                    elif event.key == pygame.K_LEFT  and direction != RIGHT:
                        direction = LEFT
                    elif event.key == pygame.K_RIGHT and direction != LEFT:
                        direction = RIGHT

        if not game_over:
            # ── Move ──────────────────────────────────────────
            head = (snake[0][0] + direction[0], snake[0][1] + direction[1])

            # Wall collision
            if not (0 <= head[0] < COLS and 0 <= head[1] < ROWS):
                game_over = True
                continue

            # Self collision
            if head in snake:
                game_over = True
                continue

            snake.insert(0, head)

            if head == food:
                score += 10
                food = random_food(snake)
            else:
                snake.pop()

        # ── Draw ──────────────────────────────────────────────
        screen.fill(BLACK)

        # Grid
        for c in range(COLS):
            for r in range(ROWS):
                pygame.draw.rect(screen, GRAY,
                                 pygame.Rect(c * CELL, r * CELL, CELL, CELL), 1)

        # Food
        draw_cell(screen, food[0], food[1], RED, (180, 0, 0))

        # Snake
        for i, (c, r) in enumerate(snake):
            color = GREEN if i > 0 else (0, 255, 80)
            draw_cell(screen, c, r, color)

        # Score
        score_surf = font.render(f"Score: {score}", True, WHITE)
        screen.blit(score_surf, (8, 8))

        # Game over overlay
        if game_over:
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 160))
            screen.blit(overlay, (0, 0))
            over = big.render("GAME OVER", True, RED)
            sub  = font.render(f"Score: {score}   |   R = Restart   Q = Quit", True, WHITE)
            screen.blit(over, over.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 30)))
            screen.blit(sub,  sub.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 20)))

        pygame.display.flip()

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    run_game()
'''
        templates = {
            "Python": f'"""\n{task}\n"""\n\n\ndef main():\n    # TODO: {task}\n    pass\n\n\nif __name__ == "__main__":\n    main()\n',
            "JavaScript": f"// {task}\n\nfunction main() {{\n    // TODO: {task}\n}}\n\nmain();\n",
            "HTML": f'<!DOCTYPE html>\n<html lang="en">\n<head>\n    <meta charset="UTF-8">\n    <title>{task}</title>\n</head>\n<body>\n    <!-- TODO: {task} -->\n    <h1>Hello World</h1>\n</body>\n</html>\n',
            "C++": f'// {task}\n#include <iostream>\nusing namespace std;\n\nint main() {{\n    // TODO: {task}\n    cout << "Hello World" << endl;\n    return 0;\n}}\n',
            "Java": f'// {task}\npublic class Main {{\n    public static void main(String[] args) {{\n        // TODO: {task}\n        System.out.println("Hello World");\n    }}\n}}\n',
        }
        return templates.get(language, f"# {task}\n# TODO: implement\n")

    # ═══════════════════════════════════════════════════════════
    # FILE CREATION
    # ═══════════════════════════════════════════════════════════

    def save_code(
        self, code: str, filename: str, directory: Path | None = None
    ) -> Path:
        """
        Write generated code to disk.

        Args:
            code:      Code string to write
            filename:  Filename including extension (e.g. "hello.py")
            directory: Where to save — defaults to JARVIS_CODE_DIR

        Returns:
            Full Path of the saved file.
        """
        # ── Guard: validate code before writing ─────────────
        if not code or not isinstance(code, str):
            log.error(f"save_code: invalid code (type={type(code).__name__}, len={len(code) if code else 0})")
            raise ValueError("Generated code is empty or invalid — cannot save.")

        save_dir = directory or JARVIS_CODE_DIR
        save_dir = Path(save_dir)
        save_dir.mkdir(parents=True, exist_ok=True)

        # Sanitise filename
        filename = re.sub(r'[<>:"/\\|?*]', "_", filename)
        if not Path(filename).suffix:
            filename += ".py"

        filepath = save_dir / filename

        try:
            filepath.write_text(code, encoding="utf-8")
            log.info(f"Code saved: {filepath}")
            return filepath
        except Exception as e:
            log.error(f"save_code error: {e}")
            raise

    # ═══════════════════════════════════════════════════════════
    # VS CODE OPENER
    # ═══════════════════════════════════════════════════════════

    def open_in_vscode(self, filepath: Path) -> bool:
        """
        Open a file in VS Code.
        Returns True if VS Code launched successfully.
        """
        filepath = Path(filepath)

        # Create file if it doesn't exist yet
        if not filepath.exists():
            filepath.parent.mkdir(parents=True, exist_ok=True)
            filepath.write_text("", encoding="utf-8")

        try:
            log.info(f"Opening VS Code with: {filepath}")
            subprocess.Popen(
                [self._vscode_exe, str(filepath)],
                shell=(self._vscode_exe == "code"),  # Shell required for PATH command
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            # Wait for VS Code window to appear
            return self._wait_for_vscode(timeout=12)

        except Exception as e:
            log.error(f"VS Code open error: {e}")
            return False

    def _wait_for_vscode(self, timeout: int = 12) -> bool:
        """Poll every 0.5s until VS Code window appears (max timeout seconds)."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._is_vscode_focused():
                return True
            titles = self._get_all_window_titles()
            if any("visual studio code" in t.lower() for t in titles):
                time.sleep(1.5)  # Let it fully render
                self._focus_vscode()
                return True
            time.sleep(0.5)
        log.warning("VS Code window did not appear in time")
        return False

    def _is_vscode_focused(self) -> bool:
        """Return True if VS Code is the currently active window."""
        try:
            import pygetwindow as gw

            active = gw.getActiveWindow()
            if active:
                return "visual studio code" in (active.title or "").lower()
        except Exception:
            pass
        return False

    def _get_all_window_titles(self) -> list:
        """Return list of all visible window titles."""
        try:
            import pygetwindow as gw

            return gw.getAllTitles()
        except Exception:
            return []

    def _focus_vscode(self) -> bool:
        """Bring VS Code window to the front."""
        try:
            import pygetwindow as gw

            for title in gw.getAllTitles():
                if "visual studio code" in title.lower():
                    wins = gw.getWindowsWithTitle(title)
                    if wins:
                        win = wins[0]
                        if win.isMinimized:
                            win.restore()
                        win.activate()
                        time.sleep(0.6)
                        return True
        except Exception as e:
            log.warning(f"Focus VS Code error: {e}")
        return False

    # ═══════════════════════════════════════════════════════════
    # ANIMATED CODE TYPING
    # ═══════════════════════════════════════════════════════════

    _stop_typing = False  # Set True to abort mid-animation

    def stop_writing(self):
        """Call this from the 'stop' command to abort code typing."""
        self._stop_typing = True
        log.info("Code typing interrupted by user.")

    def _clipboard_copy(self, text: str, retries: int = 5) -> bool:
        """Copy text to clipboard with retry for WinError 5 (Access Denied)."""
        for attempt in range(retries):
            try:
                pyperclip.copy(text)
                return True
            except Exception as e:
                if attempt < retries - 1:
                    time.sleep(0.1 * (attempt + 1))  # progressive delay
                else:
                    log.error(f"Clipboard copy failed after {retries} attempts: {e}")
                    return False
        return False

    def type_code_animated(
        self,
        code: str,
        delay_per_line: float = 0.06,
        clear_first: bool = True,
    ) -> bool:
        """
        Type code into the focused VS Code editor.

        Strategy: BULK PASTE the entire code at once using clipboard.
        This avoids ALL VS Code auto-indent issues that corrupt code
        when pasting line-by-line. The code is already saved to disk,
        so the file is correct regardless — this is purely visual.

        Args:
            code:           The code string to type
            delay_per_line: (unused — kept for API compat)
            clear_first:    Whether to select-all + delete before typing

        Returns:
            True if typing completed without error.
        """
        if not code:
            return False

        self._stop_typing = False  # Reset stop flag

        # Make sure VS Code editor area is focused
        self._focus_vscode()
        time.sleep(0.5)

        # Click in the centre of the screen to focus the editor pane
        screen_w, screen_h = pyautogui.size()
        pyautogui.click(screen_w // 2, screen_h // 2)
        time.sleep(0.3)

        # Check for stop
        if self._stop_typing:
            return False

        # Clear existing content
        if clear_first:
            pyautogui.hotkey("ctrl", "a")
            time.sleep(0.1)
            pyautogui.press("delete")
            time.sleep(0.15)

        try:
            # ── BULK PASTE: Copy entire code → single Ctrl+V ─────
            # This is 100% reliable because VS Code handles
            # multi-line paste correctly with proper indentation.
            if not self._clipboard_copy(code):
                log.error("Cannot access clipboard — code is saved on disk.")
                return False

            # Check for stop before pasting
            if self._stop_typing:
                return False

            time.sleep(0.05)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.3)

            # Save the file
            pyautogui.hotkey("ctrl", "s")
            time.sleep(0.2)

            # Jump to top so user sees the beginning
            pyautogui.hotkey("ctrl", "Home")
            time.sleep(0.1)

            line_count = len(code.splitlines())
            log.info(f"Code pasted: {line_count} lines OK")
            return True

        except Exception as e:
            log.error(f"type_code_animated error: {e}")
            # Try to save whatever was typed so far
            try:
                pyautogui.hotkey("ctrl", "s")
            except Exception:
                pass
            return False

    # ═══════════════════════════════════════════════════════════
    # MAIN WORKFLOW
    # ═══════════════════════════════════════════════════════════

    def write_to_vscode(
        self,
        task: str,
        filename: str,
        language: str | None = None,
        save_dir: Path | None = None,
        speak_fn=None,
    ) -> str:
        """
        Full end-to-end workflow:
          1. Detect language
          2. Generate code via Gemini
          3. Save to disk
          4. Open VS Code
          5. Type code with animation
          6. Return status + explanation

        Args:
            task:     Natural language description ("reverse a string")
            filename: Filename with extension ("reverse_string.py")
            language: Language override; auto-detected if None
            save_dir: Where to save; defaults to JARVIS_Code on Desktop
            speak_fn: Optional callable(str) to speak status updates

        Returns:
            Final spoken response string.
        """

        def _say(msg: str):
            log.info(msg)
            if speak_fn:
                speak_fn(msg)

        # ── Step 1: Language detection ────────────────────────
        if not language:
            language = self.detect_language(task, filename)

        # For pygame/game tasks, always force Python
        task_lower = task.lower()
        if any(w in task_lower for w in ["pygame", "snake game", "tetris", "pong"]):
            language = "Python"

        _is_game = any(
            w in task_lower
            for w in [
                "game",
                "snake",
                "tetris",
                "chess",
                "pong",
                "pacman",
                "breakout",
                "asteroids",
                "platformer",
                "shooter",
            ]
        )

        if _is_game:
            _say(
                f"Building a complete {task} now, sir. This might take a moment — writing the full game."
            )
        else:
            _say(f"Generating {language} code for {filename}, sir.")

        # ── Step 2: Code generation ───────────────────────────
        code, explanation = self.generate_code(task, language)

        if not code or len(code) < 5:
            return "Code generation failed, sir. Try rephrasing the task."

        # ── Step 3: Save to disk ──────────────────────────────
        try:
            filepath = self.save_code(code, filename, save_dir or JARVIS_CODE_DIR)
        except Exception as e:
            return f"Couldn't save the file, sir: {str(e)[:80]}"

        self._last_filepath = str(filepath)
        self._last_code = code
        self._last_language = language
        self._pending_run = self._can_run(filepath)

        # ── Step 4: Open VS Code ──────────────────────────────
        _say("Opening VS Code now.")
        vscode_ok = self.open_in_vscode(filepath)

        if not vscode_ok:
            # VS Code didn't open — code is still saved
            return (
                f"VS Code didn't open, sir, but the code is saved at {filepath}. "
                f"You can open it manually. {explanation}"
            )

        # ── Step 5: Type code ─────────────────────────────────
        _say("Writing the code now, sir.")
        typed = self.type_code_animated(code, delay_per_line=0.06)

        if not typed:
            return (
                f"The file is ready at {filepath}, sir, "
                f"but I had trouble typing into VS Code. Try clicking inside the editor."
            )

        # ── Step 6: Response ──────────────────────────────────
        line_count = len(code.splitlines())

        if _is_game:
            response = (
                f"Done, sir! The {task} is ready — {line_count} lines of {language} "
                f"open in VS Code. "
            )
            if explanation:
                response += explanation + " "
            response += "Say 'run it' to play!"
        else:
            response = (
                f"Done, sir! {filename} is open in VS Code — "
                f"{line_count} lines of {language}. "
            )
            if explanation:
                response += explanation
            if self._pending_run:
                response += " Would you like me to run it?"

        return response

    # ═══════════════════════════════════════════════════════════
    # RUN CODE
    # ═══════════════════════════════════════════════════════════

    def _can_run(self, filepath: Path) -> bool:
        """Return True if the file can be executed directly."""
        return Path(filepath).suffix.lower() in RUNNERS

    def run_last_file(self) -> str:
        """
        Execute the last file written.
        Runs in a subprocess with 30s timeout.
        Returns spoken result string.
        """
        if not self._last_filepath:
            return "No file to run yet, sir."

        filepath = Path(self._last_filepath)
        if not filepath.exists():
            return f"File not found: {filepath.name}, sir."

        ext = filepath.suffix.lower()
        runner = RUNNERS.get(ext)
        if not runner:
            return (
                f"I can't run {ext} files directly, sir. "
                f"Open the terminal and run it manually."
            )

        log.info(f"Running: {filepath}")
        try:
            result = subprocess.run(
                runner + [str(filepath)],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(filepath.parent),
            )

            stdout = (result.stdout or "").strip()
            stderr = (result.stderr or "").strip()
            success = result.returncode == 0
            self._pending_run = False

            if success:
                if stdout:
                    # Trim for speaking
                    spoken_out = stdout[:250] + ("…" if len(stdout) > 250 else "")
                    return f"Code ran successfully, sir. Output: {spoken_out}"
                return "Code ran with no output, sir. Looks clean!"
            else:
                err = self._clean_error(stderr)
                return f"The code has an error, sir: {err}"

        except subprocess.TimeoutExpired:
            return (
                "Code timed out after 30 seconds, sir. It might have an infinite loop."
            )
        except FileNotFoundError:
            runner_name = runner[0]
            return f"'{runner_name}' is not installed, sir. Install it and try again."
        except Exception as e:
            return f"Couldn't run the file, sir: {str(e)[:100]}"

    def _clean_error(self, stderr: str) -> str:
        """Extract the most useful error line from stderr."""
        if not stderr:
            return "unknown error"
        parts = [ln.strip() for ln in stderr.splitlines() if ln.strip()]
        # Return last meaningful line (usually the actual error)
        for part in reversed(parts):
            if not part.startswith("File ") and not part.startswith("Traceback"):
                return part[:150]
        return parts[-1][:150] if parts else "unknown error"

    def run_in_vscode_terminal(self) -> bool:
        """
        Run the last file using VS Code's integrated terminal (Ctrl+`).
        Opens the terminal, types the run command, presses Enter.
        """
        if not self._last_filepath:
            return False

        filepath = Path(self._last_filepath)
        ext = filepath.suffix.lower()
        runner_cmd = RUNNERS.get(ext, [])
        if not runner_cmd:
            return False

        # Build command string — quote runner parts that contain spaces
        cmd = _quote_runner(runner_cmd) + f' "{filepath.name}"'

        try:
            self._focus_vscode()
            time.sleep(0.3)

            # Open VS Code integrated terminal
            pyautogui.hotkey("ctrl", "`")
            time.sleep(1.2)

            # Navigate to file's directory
            dir_cmd = f'cd "{filepath.parent}"'
            pyperclip.copy(dir_cmd)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.1)
            pyautogui.press("enter")
            time.sleep(0.4)

            # Type run command
            pyperclip.copy(cmd)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.1)
            pyautogui.press("enter")
            return True

        except Exception as e:
            log.error(f"VS Code terminal run error: {e}")
            return False

    # ═══════════════════════════════════════════════════════════
    # COMMAND PARSER (used by main.py)
    # ═══════════════════════════════════════════════════════════

    def parse_write_command(self, text: str) -> dict:
        """
        Parse a voice command into structured code-writing parameters.

        Returns dict with keys:
            action   : "write" | "run" | "explain" | "open"
            task     : cleaned task description
            language : detected language
            filename : suggested filename
        """
        text_lower = text.lower().strip()

        # Detect action
        action = "write"
        if any(
            w in text_lower for w in ["run it", "run the code", "execute", "run that"]
        ):
            action = "run"
        elif any(
            w in text_lower for w in ["explain", "what does it do", "describe the code"]
        ):
            action = "explain"
        elif any(
            w in text_lower
            for w in ["open in vscode", "open the file", "show in vscode"]
        ):
            action = "open"

        # Extract task — remove command prefixes
        task = text
        strip_prefixes = [
            "jarvis write",
            "write me",
            "write a",
            "write an",
            "write the",
            "create a",
            "create an",
            "create the",
            "make a",
            "make an",
            "build a",
            "build an",
            "generate a",
            "code a",
            "code an",
            "write",
            "create",
            "make",
            "build",
            "generate",
            "code",
            "in vscode",
            "in vs code",
            "open in vscode",
            "for me",
            "please",
            "can you",
            "could you",
        ]
        for prefix in sorted(strip_prefixes, key=len, reverse=True):
            pattern = re.compile(re.escape(prefix), re.IGNORECASE)
            task = pattern.sub("", task, count=1).strip()

        task = re.sub(r"\s+", " ", task).strip()
        if not task:
            task = text  # Fallback to original

        # Detect language
        language = self.detect_language(text, "")

        # Suggest filename
        filename = self.suggest_filename(task, language)

        return {
            "action": action,
            "task": task,
            "language": language,
            "filename": filename,
        }

    # ═══════════════════════════════════════════════════════════
    # QUICK HELPERS
    # ═══════════════════════════════════════════════════════════

    def get_last_filepath(self) -> str:
        return self._last_filepath

    def get_last_code(self) -> str:
        return self._last_code

    def has_pending_run(self) -> bool:
        return self._pending_run

    def clear_pending_run(self):
        self._pending_run = False

    def explain_last_code(self) -> str:
        """Explain the last written code via Gemini."""
        if not self._last_code:
            return "No code written yet, sir."
        explanation = self._generate_explanation(self._last_code)
        return explanation or "I couldn't generate an explanation, sir."

    def open_last_in_vscode(self) -> str:
        """Re-open the last saved file in VS Code."""
        if not self._last_filepath:
            return "No file to open, sir."
        filepath = Path(self._last_filepath)
        if not filepath.exists():
            return f"File no longer exists: {filepath.name}, sir."
        ok = self.open_in_vscode(filepath)
        if ok:
            return f"Opened {filepath.name} in VS Code, sir."
        return "Couldn't open VS Code, sir."


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    writer = VSCodeWriter(gemini_handler=None)

    # Test language detection
    cases = [
        ("write a Python function to reverse a string", ""),
        ("create a React login component", ""),
        ("build a Java calculator", "calculator.java"),
        ("make a webpage for portfolio", ""),
        ("write a bash script to backup files", ""),
    ]
    print("=== Language Detection Tests ===")
    for task, fname in cases:
        lang = writer.detect_language(task, fname)
        suggested = writer.suggest_filename(task, lang)
        print(f"  Task: {task[:45]}")
        print(f"  → Lang: {lang}  | File: {suggested}\n")

    # Test command parser
    print("=== Command Parser Tests ===")
    cmds = [
        "write a Python function to sort a list",
        "create a JavaScript fetch API wrapper",
        "run it",
        "explain the code",
    ]
    for cmd in cmds:
        parsed = writer.parse_write_command(cmd)
        print(f"  Input : {cmd}")
        print(f"  Parsed: {parsed}\n")
