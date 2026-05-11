"""
JARVIS — ml/predictive_actions.py
Learns YOUR usage patterns and predicts what you'll do next.

Two modes:
  1. Rule-based (works from day 1): tracks time-of-day + sequence patterns
  2. LSTM neural network (after 200+ commands): learns temporal dependencies

Example predictions:
  - 9:00 AM weekday → "Open Chrome, sir?"
  - After opening VS Code → "Open terminal too?"
  - Friday evening → "Play some music, sir?"

Usage:
    # In JARVIS main loop — auto-logs every command
    predictor.log_command("open_app", "open chrome")

    # Get prediction
    suggestion = predictor.predict_next()
    # → {"action": "open_app", "confidence": 0.82, "reason": "You do this every morning"}
"""

import os
import sys
import json
import time
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import log

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "command_history.db"
LSTM_MODEL_PATH = Path(__file__).parent / "predictive_model.pt"

# All 39 intents from the intent classifier
ALL_INTENTS = [
    "app_mode", "brightness_control", "browser_control", "calendar_event",
    "chat", "clipboard_operation", "close_app", "file_operation",
    "list_reminders", "math_calculate", "media_control", "memory",
    "news", "notification_control", "open_app", "open_whatsapp_chat",
    "play_music", "read_email", "read_whatsapp", "screen_control",
    "screenshot", "send_email", "send_whatsapp", "set_reminder",
    "set_timer", "shopping", "shutdown_system", "solve_problem",
    "system_info", "time_date", "type_text", "vision_camera",
    "vision_screen", "voice_control", "volume_control", "weather",
    "web_search", "write_code", "youtube_search",
]

INTENT_TO_ID = {intent: i for i, intent in enumerate(ALL_INTENTS)}
ID_TO_INTENT = {i: intent for i, intent in enumerate(ALL_INTENTS)}


# ═══════════════════════════════════════════════════════════════
#  Command Logger — stores every command with context
# ═══════════════════════════════════════════════════════════════
class CommandLogger:
    """Logs every JARVIS command to SQLite with temporal context."""

    def __init__(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(DB_PATH))
        self._create_table()

    def _create_table(self):
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS command_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                intent TEXT NOT NULL,
                raw_command TEXT,
                hour INTEGER,
                day_of_week INTEGER,
                is_weekend INTEGER,
                prev_intent TEXT
            )
        """)
        self._conn.commit()

    def log(self, intent: str, raw_command: str = "", prev_intent: str = ""):
        """Log a command with temporal features."""
        now = datetime.now()
        self._conn.execute(
            "INSERT INTO command_log (timestamp, intent, raw_command, hour, day_of_week, is_weekend, prev_intent) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                now.isoformat(),
                intent,
                raw_command,
                now.hour,
                now.weekday(),  # 0=Monday
                1 if now.weekday() >= 5 else 0,
                prev_intent,
            ),
        )
        self._conn.commit()

    def get_all(self) -> list:
        """Get all logged commands."""
        rows = self._conn.execute(
            "SELECT timestamp, intent, raw_command, hour, day_of_week, is_weekend, prev_intent "
            "FROM command_log ORDER BY id"
        ).fetchall()
        return [
            {
                "timestamp": r[0], "intent": r[1], "raw_command": r[2],
                "hour": r[3], "day_of_week": r[4], "is_weekend": r[5],
                "prev_intent": r[6],
            }
            for r in rows
        ]

    def count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM command_log").fetchone()[0]

    def get_recent(self, n: int = 50) -> list:
        """Get the N most recent commands."""
        rows = self._conn.execute(
            "SELECT timestamp, intent, raw_command, hour, day_of_week, is_weekend, prev_intent "
            "FROM command_log ORDER BY id DESC LIMIT ?", (n,)
        ).fetchall()
        return [
            {
                "timestamp": r[0], "intent": r[1], "raw_command": r[2],
                "hour": r[3], "day_of_week": r[4], "is_weekend": r[5],
                "prev_intent": r[6],
            }
            for r in reversed(rows)
        ]

    def close(self):
        self._conn.close()


# ═══════════════════════════════════════════════════════════════
#  Rule-based Predictor — works from day 1
# ═══════════════════════════════════════════════════════════════
class PatternPredictor:
    """
    Predicts next action using frequency analysis.
    No training needed — learns from logged commands immediately.
    """

    def __init__(self, logger: CommandLogger):
        self._logger = logger

    def predict(self, current_intent: str = "", top_k: int = 3) -> list:
        """
        Predict next likely actions based on patterns.

        Returns list of: {"action": str, "confidence": float, "reason": str}
        """
        commands = self._logger.get_all()
        if len(commands) < 5:
            return []

        predictions = []

        # Strategy 1: Time-of-day pattern
        now = datetime.now()
        hour = now.hour
        time_matches = [c for c in commands if c["hour"] == hour]
        if time_matches:
            time_counter = Counter(c["intent"] for c in time_matches)
            top_intent, count = time_counter.most_common(1)[0]
            total_at_hour = len(time_matches)
            conf = count / total_at_hour
            if conf > 0.2 and count >= 2:
                period = "morning" if hour < 12 else "afternoon" if hour < 17 else "evening"
                predictions.append({
                    "action": top_intent,
                    "confidence": round(conf, 2),
                    "reason": f"You usually do this in the {period} ({count}/{total_at_hour} times)",
                })

        # Strategy 2: Sequence pattern (what follows current intent)
        if current_intent:
            followers = [
                commands[i + 1]["intent"]
                for i in range(len(commands) - 1)
                if commands[i]["intent"] == current_intent
            ]
            if followers:
                seq_counter = Counter(followers)
                top_next, count = seq_counter.most_common(1)[0]
                conf = count / len(followers)
                if conf > 0.2 and count >= 2:
                    predictions.append({
                        "action": top_next,
                        "confidence": round(conf, 2),
                        "reason": f"You usually do '{top_next}' after '{current_intent}' ({count}x)",
                    })

        # Strategy 3: Day-of-week pattern
        dow = now.weekday()
        dow_matches = [c for c in commands if c["day_of_week"] == dow]
        if dow_matches:
            dow_counter = Counter(c["intent"] for c in dow_matches)
            for intent, count in dow_counter.most_common(2):
                conf = count / len(dow_matches)
                if conf > 0.25 and count >= 3:
                    day_name = ["Monday", "Tuesday", "Wednesday", "Thursday",
                                "Friday", "Saturday", "Sunday"][dow]
                    predictions.append({
                        "action": intent,
                        "confidence": round(conf, 2),
                        "reason": f"Common on {day_name}s ({count} times)",
                    })

        # Deduplicate and sort by confidence
        seen = set()
        unique = []
        for p in sorted(predictions, key=lambda x: -x["confidence"]):
            if p["action"] not in seen:
                seen.add(p["action"])
                unique.append(p)

        return unique[:top_k]


# ═══════════════════════════════════════════════════════════════
#  LSTM Predictor — neural network (needs 200+ commands)
# ═══════════════════════════════════════════════════════════════
class LSTMPredictor:
    """
    LSTM neural network that learns temporal command sequences.
    Activates after 200+ commands are logged.

    Input features (per timestep):
        - intent (one-hot, 39 dims)
        - hour (normalized, 1 dim)
        - day_of_week (one-hot, 7 dims)
        - is_weekend (1 dim)
        Total: 48 features

    Architecture:
        Input(48) → LSTM(64, 2 layers) → Dense(39) → Softmax
    """

    def __init__(self):
        self._model = None
        self._ready = False
        self._seq_length = 5  # look at last 5 commands
        self._input_dim = len(ALL_INTENTS) + 1 + 7 + 1  # 48
        self._hidden_dim = 64
        self._num_layers = 2
        self._output_dim = len(ALL_INTENTS)  # 39

        self._try_load()

    def _try_load(self):
        """Load pre-trained model if it exists."""
        try:
            import torch
            import torch.nn as nn

            if LSTM_MODEL_PATH.exists():
                self._model = self._build_model()
                self._model.load_state_dict(torch.load(str(LSTM_MODEL_PATH), map_location="cpu", weights_only=True))
                self._model.eval()
                self._ready = True
                log.info("LSTM predictor loaded!")
        except Exception as e:
            log.debug(f"LSTM not loaded: {e}")

    def _build_model(self):
        """Build the LSTM architecture."""
        import torch.nn as nn

        class ActionLSTM(nn.Module):
            def __init__(self, input_dim, hidden_dim, output_dim, num_layers):
                super().__init__()
                self.lstm = nn.LSTM(input_dim, hidden_dim, num_layers,
                                   batch_first=True, dropout=0.2)
                self.fc = nn.Linear(hidden_dim, output_dim)

            def forward(self, x):
                lstm_out, _ = self.lstm(x)
                last = lstm_out[:, -1, :]
                return self.fc(last)

        return ActionLSTM(self._input_dim, self._hidden_dim,
                         self._output_dim, self._num_layers)

    def _encode_command(self, cmd: dict) -> list:
        """Encode a single command into feature vector."""
        # Intent one-hot (39 dims)
        intent_vec = [0.0] * len(ALL_INTENTS)
        idx = INTENT_TO_ID.get(cmd.get("intent", ""), -1)
        if 0 <= idx < len(ALL_INTENTS):
            intent_vec[idx] = 1.0

        # Hour normalized (1 dim)
        hour_norm = [cmd.get("hour", 12) / 23.0]

        # Day of week one-hot (7 dims)
        dow_vec = [0.0] * 7
        dow = cmd.get("day_of_week", 0)
        if 0 <= dow < 7:
            dow_vec[dow] = 1.0

        # Weekend flag (1 dim)
        weekend = [float(cmd.get("is_weekend", 0))]

        return intent_vec + hour_norm + dow_vec + weekend

    def train_model(self, logger: CommandLogger, epochs: int = 50) -> dict:
        """Train the LSTM on logged command history."""
        import torch
        import torch.nn as nn
        from torch.utils.data import DataLoader, TensorDataset

        commands = logger.get_all()
        if len(commands) < self._seq_length + 10:
            return {"status": "not_enough_data", "count": len(commands), "needed": 200}

        # Build sequences: [cmd1, cmd2, ..., cmd5] → predict cmd6
        X_data, y_data = [], []
        for i in range(len(commands) - self._seq_length):
            seq = commands[i:i + self._seq_length]
            target = commands[i + self._seq_length]
            x_seq = [self._encode_command(c) for c in seq]
            y_idx = INTENT_TO_ID.get(target["intent"], 0)
            X_data.append(x_seq)
            y_data.append(y_idx)

        X = torch.FloatTensor(X_data)
        y = torch.LongTensor(y_data)

        # Split 80/20
        split = int(len(X) * 0.8)
        X_train, X_val = X[:split], X[split:]
        y_train, y_val = y[:split], y[split:]

        # Build model
        self._model = self._build_model()
        criterion = nn.CrossEntropyLoss()
        optimizer = torch.optim.Adam(self._model.parameters(), lr=0.001)

        dataset = TensorDataset(X_train, y_train)
        loader = DataLoader(dataset, batch_size=32, shuffle=True)

        # Train
        print(f"  Training LSTM on {len(X_train)} sequences...")
        best_acc = 0
        for epoch in range(epochs):
            self._model.train()
            total_loss = 0
            for batch_x, batch_y in loader:
                optimizer.zero_grad()
                output = self._model(batch_x)
                loss = criterion(output, batch_y)
                loss.backward()
                optimizer.step()
                total_loss += loss.item()

            # Validate
            if len(X_val) > 0:
                self._model.eval()
                with torch.no_grad():
                    val_out = self._model(X_val)
                    val_pred = val_out.argmax(dim=1)
                    acc = (val_pred == y_val).float().mean().item()
                    if acc > best_acc:
                        best_acc = acc

            if (epoch + 1) % 10 == 0:
                print(f"    Epoch {epoch+1}/{epochs} | Loss: {total_loss:.3f} | Val Acc: {acc:.1%}")

        # Save
        torch.save(self._model.state_dict(), str(LSTM_MODEL_PATH))
        self._model.eval()
        self._ready = True

        return {
            "status": "trained",
            "sequences": len(X_data),
            "best_accuracy": round(best_acc, 3),
            "model_path": str(LSTM_MODEL_PATH),
        }

    def predict(self, recent_commands: list, top_k: int = 3) -> list:
        """Predict next action from recent command sequence."""
        if not self._ready or not self._model:
            return []

        import torch

        if len(recent_commands) < self._seq_length:
            return []

        # Take last N commands
        seq = recent_commands[-self._seq_length:]
        x_seq = [self._encode_command(c) for c in seq]
        X = torch.FloatTensor([x_seq])

        self._model.eval()
        with torch.no_grad():
            output = self._model(X)
            probs = torch.softmax(output, dim=1)[0]
            top_vals, top_idxs = probs.topk(top_k)

        results = []
        for val, idx in zip(top_vals, top_idxs):
            results.append({
                "action": ID_TO_INTENT.get(idx.item(), "unknown"),
                "confidence": round(val.item(), 3),
                "reason": "LSTM pattern prediction",
            })

        return results

    @property
    def is_ready(self) -> bool:
        return self._ready


# ═══════════════════════════════════════════════════════════════
#  Main Predictor — combines both strategies
# ═══════════════════════════════════════════════════════════════
class PredictiveActions:
    """
    Main interface for JARVIS predictive actions.
    Combines rule-based + LSTM predictions.
    """

    def __init__(self):
        self._logger = CommandLogger()
        self._pattern = PatternPredictor(self._logger)
        self._lstm = LSTMPredictor()
        self._prev_intent = ""
        log.info(f"PredictiveActions: {self._logger.count()} commands logged, LSTM={'ready' if self._lstm.is_ready else 'needs training'}")

    def log_command(self, intent: str, raw_command: str = ""):
        """Call this after every JARVIS command is executed."""
        self._logger.log(intent, raw_command, self._prev_intent)
        self._prev_intent = intent

    def predict_next(self, top_k: int = 3) -> list:
        """Get predictions for what user will do next."""
        predictions = []

        # Rule-based predictions (always available)
        rule_preds = self._pattern.predict(self._prev_intent, top_k)
        predictions.extend(rule_preds)

        # LSTM predictions (if trained)
        if self._lstm.is_ready:
            recent = self._logger.get_recent(10)
            lstm_preds = self._lstm.predict(recent, top_k)
            predictions.extend(lstm_preds)

        # Merge, deduplicate, sort by confidence
        seen = set()
        merged = []
        for p in sorted(predictions, key=lambda x: -x["confidence"]):
            if p["action"] not in seen:
                seen.add(p["action"])
                merged.append(p)

        return merged[:top_k]

    def train_lstm(self, epochs: int = 50) -> dict:
        """Train the LSTM model on collected command history."""
        return self._lstm.train_model(self._logger, epochs)

    def get_stats(self) -> dict:
        """Get stats about the prediction system."""
        return {
            "commands_logged": self._logger.count(),
            "lstm_ready": self._lstm.is_ready,
            "lstm_needs": max(0, 200 - self._logger.count()),
        }

    @property
    def is_ready(self) -> bool:
        return self._logger.count() >= 5


# ═══════════════════════════════════════════════════════════════
#  Test & Demo
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("=" * 50)
    print("  JARVIS Predictive Actions — Test")
    print("=" * 50)

    predictor = PredictiveActions()
    stats = predictor.get_stats()
    print(f"\n  Commands logged: {stats['commands_logged']}")
    print(f"  LSTM ready: {stats['lstm_ready']}")

    if stats["commands_logged"] < 5:
        print("\n  Seeding with sample commands to demo the system...")
        # Simulate a typical day pattern
        sample_patterns = [
            ("open_app", "open chrome"),
            ("web_search", "search python tutorial"),
            ("open_app", "open vs code"),
            ("write_code", "write a python function"),
            ("play_music", "play lofi beats"),
            ("time_date", "what time is it"),
            ("chat", "how are you jarvis"),
            ("weather", "what's the weather"),
            ("open_app", "open chrome"),
            ("youtube_search", "search youtube coding"),
            ("screenshot", "take screenshot"),
            ("volume_control", "volume up"),
            ("open_app", "open chrome"),
            ("web_search", "search machine learning"),
            ("chat", "tell me a joke"),
            ("play_music", "play some music"),
            ("open_app", "open chrome"),
            ("send_whatsapp", "send whatsapp to mom"),
            ("time_date", "what date is today"),
            ("shutdown_system", "sleep mode"),
        ]
        for intent, cmd in sample_patterns:
            predictor.log_command(intent, cmd)
        print(f"  Seeded {len(sample_patterns)} sample commands")

    # Show predictions
    print("\n  --- Predictions ---")

    # Simulate: user just opened chrome
    predictor._prev_intent = "open_app"
    preds = predictor.predict_next()
    print(f"\n  After 'open_app':")
    for p in preds:
        bar = "#" * int(p["confidence"] * 20)
        print(f"    {p['action']:20s} {bar} {p['confidence']:.0%}  ({p['reason']})")

    # Simulate: user just searched
    predictor._prev_intent = "web_search"
    preds = predictor.predict_next()
    print(f"\n  After 'web_search':")
    for p in preds:
        bar = "#" * int(p["confidence"] * 20)
        print(f"    {p['action']:20s} {bar} {p['confidence']:.0%}  ({p['reason']})")

    # Train LSTM if enough data
    count = predictor.get_stats()["commands_logged"]
    if count >= 15:
        print(f"\n  --- Training LSTM on {count} commands ---")
        result = predictor.train_lstm(epochs=30)
        print(f"  Result: {result}")

        if result.get("status") == "trained":
            print("\n  --- LSTM Predictions ---")
            predictor._prev_intent = "open_app"
            preds = predictor.predict_next()
            for p in preds:
                bar = "#" * int(p["confidence"] * 20)
                print(f"    {p['action']:20s} {bar} {p['confidence']:.0%}  ({p['reason']})")
    else:
        print(f"\n  LSTM needs {200 - count} more commands for training.")
        print("  It auto-trains once you use JARVIS enough!")

    print("\n  DONE!")
