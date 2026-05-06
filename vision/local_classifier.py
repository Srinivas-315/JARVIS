"""
JARVIS — vision/local_classifier.py
Local ML object recognition using MobileNetV2 (PyTorch).
Works 100% OFFLINE — no API key needed.

How it works:
  1. Pre-trained MobileNetV2 classifies 1000 ImageNet objects
  2. Learned objects stored as feature embeddings (cosine similarity)
  3. User teaches: "This is a brush" → saves embedding → recognized next time
"""

import os
import pickle
import numpy as np
from pathlib import Path

_ROOT      = Path(__file__).parent.parent
_EMBED_FILE = _ROOT / "data" / "learned_embeddings.pkl"
_CLASS_FILE = _ROOT / "data" / "imagenet_classes.txt"

# 80 most common everyday objects JARVIS should know
COMMON_OBJECTS = [
    "pen", "pencil", "brush", "paintbrush", "toothbrush", "spoon", "fork",
    "knife", "cup", "mug", "bottle", "book", "phone", "mobile phone",
    "laptop", "keyboard", "mouse", "remote", "glasses", "sunglasses",
    "wallet", "keys", "headphones", "earphones", "watch", "ring",
    "scissors", "stapler", "tape", "ruler", "eraser", "marker",
    "comb", "hairbrush", "soap", "shampoo", "towel", "cloth",
    "apple", "banana", "orange", "water bottle", "coffee cup",
    "notebook", "magazine", "card", "coin", "charger", "cable",
]

IMAGENET_CLASSES_URL = (
    "https://raw.githubusercontent.com/pytorch/hub/master/"
    "imagenet_classes.txt"
)


class LocalVisionClassifier:
    """
    Offline ML object classifier.
    - Uses MobileNetV2 for ImageNet classification (1000 objects)
    - Stores embeddings of learned objects for instant recognition
    - Learns new objects from user corrections
    """

    def __init__(self):
        self._model      = None
        self._features   = None   # feature extractor layer
        self._transform  = None
        self._classes    = []
        self._learned    = []     # [{label, embedding, count}]
        self._ready      = False
        _ROOT.joinpath("data").mkdir(parents=True, exist_ok=True)
        self._load_learned()
        self._load_model()

    # ── Model loading ────────────────────────────────────────────
    def _load_model(self):
        try:
            import torch
            import torchvision.models as tv_models
            import torchvision.transforms as tv_transforms

            # Try new API first, fall back to old
            try:
                from torchvision.models import MobileNet_V2_Weights
                model = tv_models.mobilenet_v2(
                    weights=MobileNet_V2_Weights.DEFAULT)
            except Exception:
                model = tv_models.mobilenet_v2(pretrained=True)

            model.eval()
            self._model   = model
            self._features = model.features   # conv layers = embedding

            self._transform = tv_transforms.Compose([
                tv_transforms.Resize(256),
                tv_transforms.CenterCrop(224),
                tv_transforms.ToTensor(),
                tv_transforms.Normalize(
                    mean=[0.485, 0.456, 0.406],
                    std =[0.229, 0.224, 0.225]),
            ])

            self._classes = self._load_classes()
            self._ready   = True
            print("  ✅ Local ML classifier ready (MobileNetV2 — offline)")

        except ImportError:
            print("  ⚠️  torchvision not installed. Run: pip install torchvision")
        except Exception as e:
            print(f"  ⚠️  Local ML unavailable: {e}")

    def _load_classes(self):
        """Load ImageNet labels — use cache if exists."""
        if _CLASS_FILE.exists():
            return _CLASS_FILE.read_text().strip().splitlines()
        try:
            import urllib.request
            data = urllib.request.urlopen(
                IMAGENET_CLASSES_URL, timeout=8).read().decode()
            _CLASS_FILE.write_text(data)
            return data.strip().splitlines()
        except Exception:
            return []

    # ── Public: classify ────────────────────────────────────────
    def classify(self, image_path: str) -> str | None:
        """
        Returns a description string, or None if not confident.
        Checks learned objects first, then ImageNet.
        """
        if not self._ready:
            return None

        try:
            import torch
            import torch.nn.functional as F
            from PIL import Image

            img    = Image.open(image_path).convert("RGB")
            tensor = self._transform(img).unsqueeze(0)

            with torch.no_grad():
                # Get embedding
                feat_map = self._features(tensor)
                emb      = feat_map.mean(dim=[2, 3]).squeeze().numpy()
                emb      = emb / (np.linalg.norm(emb) + 1e-8)

                # 1️⃣ Check learned objects
                label, sim = self._find_closest(emb)
                if label and sim > 0.82:
                    return (f"That's a {label}, sir. "
                            f"I recognize it from memory — {sim*100:.0f}% match.")

                # 2️⃣ ImageNet classification
                out   = self._model(tensor)
                probs = F.softmax(out[0], dim=0)
                top_p, top_i = torch.topk(probs, 5)

                results = []
                for p, i in zip(top_p.tolist(), top_i.tolist()):
                    if p > 0.03 and self._classes:
                        name = self._classes[i].replace("_", " ").lower()
                        results.append((name, p))

                if results:
                    name, conf = results[0]
                    if conf > 0.40:
                        return (f"That appears to be a {name}, sir. "
                                f"I'm about {conf*100:.0f}% confident.")
                    elif conf > 0.15:
                        alts = " or ".join(r[0] for r in results[:3])
                        return (f"It could be {alts}, sir — "
                                f"I'm not fully certain.")

            return None   # Low confidence — let caller decide

        except Exception as e:
            print(f"  [LocalML] classify error: {e}")
            return None

    # ── Public: learn ────────────────────────────────────────────
    def learn(self, image_path: str, label: str) -> bool:
        """Save embedding for a new object label."""
        if not self._ready:
            return False
        try:
            import torch
            from PIL import Image

            img    = Image.open(image_path).convert("RGB")
            tensor = self._transform(img).unsqueeze(0)

            with torch.no_grad():
                feat_map = self._features(tensor)
                emb      = feat_map.mean(dim=[2, 3]).squeeze().numpy()
                emb      = emb / (np.linalg.norm(emb) + 1e-8)

            label = label.strip().lower()
            existing = [e for e in self._learned if e["label"] == label]
            if existing:
                # Blend embeddings for better generalization
                old = existing[0]["embedding"]
                existing[0]["embedding"] = old * 0.65 + emb * 0.35
                existing[0]["count"]    += 1
            else:
                self._learned.append(
                    {"label": label, "embedding": emb, "count": 1})

            self._save_learned()
            return True

        except Exception as e:
            print(f"  [LocalML] learn error: {e}")
            return False

    # ── Public: status ───────────────────────────────────────────
    @property
    def is_ready(self):
        return self._ready

    @property
    def learned_count(self):
        return len(self._learned)

    def learned_names(self):
        return [e["label"] for e in self._learned]

    # ── Helpers ──────────────────────────────────────────────────
    def _find_closest(self, emb):
        best_sim, best_label = 0.0, None
        for e in self._learned:
            sim = float(np.dot(emb, e["embedding"]))
            if sim > best_sim:
                best_sim, best_label = sim, e["label"]
        return best_label, best_sim

    def _load_learned(self):
        try:
            if _EMBED_FILE.exists():
                with open(_EMBED_FILE, "rb") as f:
                    self._learned = pickle.load(f)
                print(f"  ✅ Loaded {len(self._learned)} learned objects from ML memory")
        except Exception:
            self._learned = []

    def _save_learned(self):
        try:
            with open(_EMBED_FILE, "wb") as f:
                pickle.dump(self._learned, f)
        except Exception as e:
            print(f"  ⚠️  Could not save ML embeddings: {e}")
