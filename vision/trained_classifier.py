"""
JARVIS — vision/trained_classifier.py
Uses the classifier trained in Google Colab on Open Images V7.

Required files in JARVIS/models/:
  - jarvis_classifier.pkl   (~5 MB)  — the trained LogisticRegression
  - label_map.json          (~50 KB) — class index → name mapping

Pipeline:
  CLIP encodes image → trained classifier predicts class → return label
"""

import json
import pickle
import threading
from pathlib import Path

_ROOT       = Path(__file__).parent.parent
_MODELS_DIR = _ROOT / "models"
_CLF_FILE   = _MODELS_DIR / "jarvis_classifier.pkl"
_LABEL_FILE = _MODELS_DIR / "label_map.json"


class TrainedClassifier:
    """
    Offline classifier trained on 50,000 Open Images V7 images.
    Loads in background — JARVIS wakes instantly.
    """

    def __init__(self):
        self._clf    = None
        self._labels = {}
        self._model  = None        # CLIP model (shared)
        self._preprocess = None
        self._ready  = False
        self._lock   = threading.Lock()

        if not _CLF_FILE.exists() or not _LABEL_FILE.exists():
            print("  [WARN] Trained model not found in models/ folder.")
            print(f"     Expected: {_CLF_FILE}")
            print("     Download from Google Drive → put in JARVIS/models/")
            return

        t = threading.Thread(target=self._load, daemon=True)
        t.start()

    def _load(self):
        try:
            import open_clip
            import torch
            import warnings
            warnings.filterwarnings("ignore")

            print("  [Background] Loading your trained Colab model...")

            # Load classifier
            with open(_CLF_FILE, "rb") as f:
                clf = pickle.load(f)

            # Load label map
            with open(_LABEL_FILE, "r") as f:
                raw = json.load(f)
            # Keys may be strings — normalize to int
            labels = {int(k): v for k, v in raw.items()}

            # Load CLIP (same model used in training)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                clip_model, _, preprocess = open_clip.create_model_and_transforms(
                    "ViT-B-32", pretrained="openai"
                )
            clip_model.eval()

            with self._lock:
                self._clf      = clf
                self._labels   = labels
                self._model    = clip_model
                self._preprocess = preprocess
                self._ready    = True

            n = len(labels)
            print(f"  Trained model ready -- {n} classes from Open Images!")

        except Exception as e:
            print(f"  [WARN] Trained model load failed: {e}")

    def classify(self, image_path: str) -> str | None:
        """Run image through trained classifier. Returns JARVIS response or None."""
        with self._lock:
            if not self._ready:
                return None

        try:
            import torch
            from PIL import Image

            img    = Image.open(image_path).convert("RGB")
            tensor = self._preprocess(img).unsqueeze(0)

            with torch.no_grad():
                feats = self._model.encode_image(tensor)
                feats = feats / feats.norm(dim=-1, keepdim=True)
                feats_np = feats.cpu().numpy()

            # Predict with trained classifier
            probs    = self._clf.predict_proba(feats_np)[0]
            top_idxs = probs.argsort()[::-1][:5]

            results = [
                (self._labels.get(int(i), f"class_{i}"), float(probs[i]))
                for i in top_idxs
                if float(probs[i]) > 0.01
            ]

            if not results:
                return None

            name, conf = results[0]
            name = name.replace("_", " ").lower()

            top3 = ", ".join(f"{n.replace('_',' ')}({v*100:.1f}%)"
                             for n, v in results[:3])
            print(f"  [TrainedModel] {top3}")

            if conf > 0.35:
                return f"That's a {name}, sir. I'm {conf*100:.0f}% confident."
            if conf > 0.10:
                alts = " or ".join(
                    r[0].replace("_", " ") for r in results[:3]
                )
                return f"It looks like {alts}, sir."

            return None

        except Exception as e:
            print(f"  [TrainedModel] error: {e}")
            return None

    @property
    def is_ready(self) -> bool:
        with self._lock:
            return self._ready
