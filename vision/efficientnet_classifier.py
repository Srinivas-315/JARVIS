"""
JARVIS — vision/efficientnet_classifier.py
EfficientNet-B4 — 1000 ImageNet classes, ~75MB, loads fast.
Loads in background thread so JARVIS wakes up instantly.
"""

import json
import threading
from pathlib import Path

_CACHE_DIR  = Path.home() / ".cache" / "jarvis"
_LABEL_FILE = _CACHE_DIR / "imagenet1k_labels.json"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Working label URLs (tried in order until one works)
_LABEL_URLS = [
    "https://raw.githubusercontent.com/anishathalye/imagenet-simple-labels/master/imagenet-simple-labels.json",
    "https://raw.githubusercontent.com/pytorch/hub/master/imagenet_classes.txt",
]


def _fetch_labels() -> list:
    """Download 1000 ImageNet labels. Returns list of strings."""
    import urllib.request, json

    for url in _LABEL_URLS:
        try:
            data = urllib.request.urlopen(url, timeout=10).read().decode()
            if url.endswith(".json"):
                labels = json.loads(data)
            else:
                labels = [l.strip() for l in data.strip().split("\n")]
            if len(labels) >= 900:
                _LABEL_FILE.write_text(json.dumps(labels))
                return labels
        except Exception:
            continue
    return []


class EfficientNetClassifier:
    """
    Fast object classifier — EfficientNet-B4 pretrained on ImageNet-1K.
    Loads in background so JARVIS wakes instantly.
    """

    def __init__(self):
        self._model     = None
        self._transform = None
        self._labels    = []
        self._ready     = False
        self._lock      = threading.Lock()

        # Background load — doesn't block JARVIS startup
        t = threading.Thread(target=self._load_model, daemon=True)
        t.start()

    def _load_model(self):
        try:
            import timm
            import warnings
            warnings.filterwarnings("ignore")   # suppress timm noise

            print("  [Background] Loading EfficientNet-B4 (75MB)...")

            model = timm.create_model("efficientnet_b4", pretrained=True)
            model.eval()

            data_cfg  = timm.data.resolve_model_data_config(model)
            transform = timm.data.create_transform(**data_cfg, is_training=False)

            # Load labels (cache first, then download)
            if _LABEL_FILE.exists():
                labels = json.loads(_LABEL_FILE.read_text())
            else:
                print("  [Background] Downloading ImageNet labels...")
                labels = _fetch_labels()

            with self._lock:
                self._model     = model
                self._transform = transform
                self._labels    = labels
                self._ready     = True

            print(f"  EfficientNet-B4 ready -- {len(labels)} classes -- offline!")

        except ImportError:
            print("  [WARN] timm not installed. Run: pip install timm")
        except Exception as e:
            print(f"  [WARN] EfficientNet init failed: {e}")

    def classify(self, image_path: str) -> str | None:
        """Identify the object. Returns None if not ready or not confident."""
        with self._lock:
            if not self._ready:
                return None   # Still loading — fall through to CLIP

        try:
            import torch
            from PIL import Image

            img    = Image.open(image_path).convert("RGB")
            tensor = self._transform(img).unsqueeze(0)

            with torch.no_grad():
                logits = self._model(tensor)
                probs  = torch.softmax(logits, dim=-1).squeeze(0)
                top_p, top_i = probs.topk(5)

            results = [
                (self._labels[i], float(p))
                for p, i in zip(top_p.tolist(), top_i.tolist())
                if i < len(self._labels)
            ]

            if not results:
                return None

            name, conf = results[0]
            top3 = ", ".join(f"{n}({v*100:.1f}%)" for n, v in results[:3])
            print(f"  [EfficientNet] {top3}")

            if conf > 0.30:
                return f"That's a {name}, sir. I'm {conf*100:.0f}% confident."
            if conf > 0.08:
                alts = " or ".join(r[0] for r in results[:3])
                return f"It looks like {alts}, sir."

            return None

        except Exception as e:
            print(f"  [EfficientNet] error: {e}")
            return None

    @property
    def is_ready(self) -> bool:
        with self._lock:
            return self._ready
