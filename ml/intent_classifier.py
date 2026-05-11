"""
JARVIS — ml/intent_classifier.py
Offline intent classification using fine-tuned DistilBERT.

This runs on CPU in <50ms (or GPU in <10ms) and classifies
user commands into 39 skill categories WITHOUT any API calls.

Usage:
    from ml.intent_classifier import OfflineIntentClassifier
    classifier = OfflineIntentClassifier()
    result = classifier.classify("open chrome")
    # → {"intent": "open_app", "confidence": 0.97}
"""

import json
import os
import sys
import time

# Ensure project root is in path (for direct execution)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import torch
from transformers import DistilBertTokenizer, DistilBertForSequenceClassification

from utils.logger import log

# Paths
ML_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(ML_DIR, "jarvis_intent_model")
LABEL_MAP_PATH = os.path.join(MODEL_DIR, "label_map.json")


class OfflineIntentClassifier:
    """
    Local DistilBERT model for offline intent classification.
    Loads once at startup, classifies in <50ms on CPU.
    """

    def __init__(self, use_gpu: bool = True):
        self._model = None
        self._tokenizer = None
        self._id2label = {}
        self._label2id = {}
        self._device = "cpu"
        self._ready = False
        self._load_time = 0

        self._load_model(use_gpu)

    def _load_model(self, use_gpu: bool):
        """Load the fine-tuned model from disk."""
        if not os.path.exists(MODEL_DIR):
            log.info("Offline intent model not found — run ml/train_intent_model.py first")
            return

        if not os.path.exists(LABEL_MAP_PATH):
            log.warning("Label map not found — model incomplete")
            return

        try:
            start = time.time()

            # Load label mapping
            with open(LABEL_MAP_PATH, "r") as f:
                maps = json.load(f)
                self._id2label = {int(k): v for k, v in maps["id2label"].items()}
                self._label2id = maps["label2id"]

            # Determine device
            if use_gpu and torch.cuda.is_available():
                self._device = "cuda"
            else:
                self._device = "cpu"

            # Load model + tokenizer
            self._tokenizer = DistilBertTokenizer.from_pretrained(MODEL_DIR)
            self._model = DistilBertForSequenceClassification.from_pretrained(MODEL_DIR)
            self._model.to(self._device)
            self._model.eval()

            self._load_time = (time.time() - start) * 1000
            self._ready = True

            log.info(
                f"Offline intent model loaded on {self._device.upper()} "
                f"({self._load_time:.0f}ms, {len(self._id2label)} intents)"
            )

        except Exception as e:
            log.warning(f"Failed to load offline intent model: {e}")
            self._ready = False

    @property
    def is_ready(self) -> bool:
        """Check if the model is loaded and ready."""
        return self._ready

    def classify(self, text: str, threshold: float = 0.4) -> dict:
        """
        Classify a text command into an intent.

        Args:
            text: User command (e.g. "open chrome")
            threshold: Minimum confidence to return a result

        Returns:
            {"intent": "open_app", "confidence": 0.97, "latency_ms": 12.3}
            or {"intent": "unknown", "confidence": 0.0} if below threshold
        """
        if not self._ready:
            return {"intent": "unknown", "confidence": 0.0, "latency_ms": 0}

        try:
            start = time.time()

            # Tokenize
            inputs = self._tokenizer(
                text.lower().strip(),
                return_tensors="pt",
                truncation=True,
                max_length=64,
                padding=True,
            ).to(self._device)

            # Inference
            with torch.no_grad():
                outputs = self._model(**inputs)
                probs = torch.softmax(outputs.logits, dim=-1)
                pred_id = torch.argmax(probs, dim=-1).item()
                confidence = probs[0][pred_id].item()

            latency = (time.time() - start) * 1000

            intent = self._id2label.get(pred_id, "unknown")

            if confidence < threshold:
                return {"intent": "unknown", "confidence": confidence, "latency_ms": latency}

            return {
                "intent": intent,
                "confidence": confidence,
                "latency_ms": latency,
            }

        except Exception as e:
            log.debug(f"Offline classifier error: {e}")
            return {"intent": "unknown", "confidence": 0.0, "latency_ms": 0}

    def classify_top_k(self, text: str, k: int = 3) -> list[dict]:
        """
        Get top-K intent predictions with confidence scores.
        Useful for debugging and understanding model behavior.
        """
        if not self._ready:
            return []

        try:
            inputs = self._tokenizer(
                text.lower().strip(),
                return_tensors="pt",
                truncation=True,
                max_length=64,
                padding=True,
            ).to(self._device)

            with torch.no_grad():
                outputs = self._model(**inputs)
                probs = torch.softmax(outputs.logits, dim=-1)

            top_k = torch.topk(probs[0], k=min(k, len(self._id2label)))
            results = []
            for score, idx in zip(top_k.values.tolist(), top_k.indices.tolist()):
                results.append({
                    "intent": self._id2label.get(idx, "unknown"),
                    "confidence": score,
                })
            return results

        except Exception as e:
            log.debug(f"Top-K classification error: {e}")
            return []

    def benchmark(self, test_commands: list[str] = None) -> dict:
        """
        Run a benchmark to test speed and accuracy.
        Returns average latency and results.
        """
        if not self._ready:
            return {"error": "Model not loaded"}

        if test_commands is None:
            test_commands = [
                "open chrome", "play music", "what time is it",
                "send message to mom", "take a screenshot",
                "volume up", "weather today", "tell me a joke",
                "set reminder for 5pm", "close notepad",
            ]

        results = []
        total_time = 0

        for cmd in test_commands:
            r = self.classify(cmd)
            total_time += r["latency_ms"]
            results.append({"command": cmd, **r})

        avg_latency = total_time / len(test_commands)

        return {
            "avg_latency_ms": avg_latency,
            "total_commands": len(test_commands),
            "device": self._device,
            "results": results,
        }


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("Loading offline intent classifier...")
    clf = OfflineIntentClassifier()

    if not clf.is_ready:
        print("Model not trained yet! Run these commands first:")
        print("  1. python ml/generate_training_data.py")
        print("  2. python ml/train_intent_model.py")
        sys.exit(1)

    # Interactive mode
    print(f"\nModel loaded! Type commands to test (or 'quit' to exit):\n")

    while True:
        try:
            cmd = input("You: ").strip()
            if cmd.lower() in ("quit", "exit", "q"):
                break
            if not cmd:
                continue

            result = clf.classify(cmd)
            top3 = clf.classify_top_k(cmd, k=3)

            print(f"  Intent: {result['intent']} ({result['confidence']:.1%})")
            print(f"  Latency: {result['latency_ms']:.1f}ms")
            top3_str = ', '.join(f"{r['intent']}({r['confidence']:.0%})" for r in top3)
            print(f"  Top 3: {top3_str}")
            print()
        except (KeyboardInterrupt, EOFError):
            break

    print("\nDone!")
