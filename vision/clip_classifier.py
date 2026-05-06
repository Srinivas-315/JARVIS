"""
JARVIS — vision/clip_classifier.py
CLIP-powered zero-shot object recognition.
Loads in background thread — JARVIS wakes instantly.

Model: ViT-B-32 (~338 MB, cached after first run)
"""

import warnings
import threading
import numpy as np
from pathlib import Path

warnings.filterwarnings("ignore", category=UserWarning)

_ROOT = Path(__file__).parent.parent

# ── Comprehensive object candidate list ──────────────────────────
# CLIP ranks the image against ALL of these and picks the best match
CANDIDATES = [
    # Writing / Office
    "pen", "pencil", "marker", "highlighter", "crayon", "chalk",
    "eraser", "ruler", "stapler", "scissors", "tape", "glue stick",
    "paper clip", "binder clip", "rubber band",
    "notebook", "book", "textbook", "magazine", "newspaper",
    "envelope", "sticky note", "calendar", "folder",
    # Art / Craft
    "paintbrush", "brush", "paint tube", "palette", "canvas",
    "sketchbook", "watercolor", "spray can",
    # Electronics (kept distinct — only ONE phone entry)
    "smartphone", "tablet", "laptop", "computer monitor",
    "keyboard", "computer mouse", "speaker", "headphones",
    "earphones", "charger", "power bank", "USB cable",
    "hard drive", "flash drive", "memory card", "camera",
    "remote control", "game controller", "calculator",
    "smartwatch", "router", "printer", "television",
    # Kitchen / Food items
    "cup", "mug", "glass", "bottle", "water bottle", "thermos",
    "plate", "bowl", "spoon", "fork", "knife", "chopsticks",
    "frying pan", "pot", "kettle", "toaster", "blender", "microwave",
    "apple", "banana", "orange", "mango", "grapes", "strawberry",
    "bread", "rice", "egg", "pizza", "burger", "sandwich",
    "coffee", "tea", "juice", "milk carton", "snack packet",
    # Personal Care
    "toothbrush", "toothpaste", "comb", "hairbrush", "razor",
    "shampoo bottle", "soap", "lotion", "perfume", "deodorant",
    "makeup", "lipstick", "foundation", "nail polish", "cotton swab",
    # Clothing / Accessories
    "shirt", "t-shirt", "jeans", "trousers", "shorts", "dress",
    "jacket", "coat", "sweater", "hoodie", "shoes", "sneakers",
    "sandals", "socks", "hat", "cap", "glasses", "sunglasses",
    "watch", "ring", "necklace", "bracelet", "belt", "bag",
    "backpack", "wallet", "purse", "umbrella",
    # Tools / Hardware
    "hammer", "screwdriver", "wrench", "pliers", "drill",
    "saw", "nail", "screw", "bolt", "wire", "tape measure",
    "level", "paintbrush roller", "flashlight", "battery",
    "lock", "key", "chain",
    # Furniture / Home
    "chair", "table", "desk", "sofa", "bed", "pillow", "blanket",
    "curtain", "lamp", "clock", "vase", "mirror", "picture frame",
    "trash can", "broom", "mop", "bucket", "basket",
    # Stationery
    "stamp", "ink pad", "hole punch", "sharpener", "correction fluid",
    "adhesive tape", "magnifying glass",
    # Medical
    "medicine bottle", "syringe", "bandage", "thermometer",
    "blood pressure monitor", "stethoscope", "mask", "gloves",
    # Sports / Fitness
    "ball", "football", "cricket bat", "tennis racket",
    "badminton racket", "dumbbell", "yoga mat", "water bottle",
    "skipping rope", "helmet",
    # Vehicles / Transport
    "car", "motorcycle", "bicycle", "bus", "truck", "auto rickshaw",
    "toy car", "bicycle helmet",
    # Animals
    "cat", "dog", "bird", "fish", "rabbit", "hamster",
    "parrot", "turtle", "snake", "spider",
    # Plants
    "plant", "flower", "cactus", "leaves", "seed", "soil",
    # Music
    "guitar", "piano keys", "microphone", "flute", "drum",
    "violin", "headphones",
    # Toys / Games
    "toy", "doll", "action figure", "lego brick", "puzzle",
    "playing cards", "chess piece", "dice", "rubik's cube",
    # Documents
    "id card", "credit card", "debit card", "passport",
    "driving license", "business card", "receipt", "bill",
    # Food containers
    "tin can", "jar", "packet", "box", "wrapper", "bag of chips",
    # Misc
    "coin", "currency note", "lighter", "matchstick", "candle",
    "safety pin", "needle", "thread", "button", "zipper",
    "straw", "tissue paper", "cotton ball", "sponge", "cloth",
]


class CLIPClassifier:
    """
    Zero-shot object recognition using CLIP.
    Loads in background — doesn't block JARVIS startup.
    """

    def __init__(self):
        self._model      = None
        self._preprocess = None
        self._tokenizer  = None
        self._ready      = False
        self._text_feats = None
        self._lock       = threading.Lock()
        # Load in background — JARVIS starts immediately
        t = threading.Thread(target=self._load_model, daemon=True)
        t.start()

    # ── Load model ───────────────────────────────────────────────
    def _load_model(self):
        try:
            import open_clip
            import torch

            print("  [Background] Loading CLIP ViT-B-32...")
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                model, _, preprocess = open_clip.create_model_and_transforms(
                    "ViT-B-32", pretrained="openai"
                )
            model.eval()

            tokenizer = open_clip.get_tokenizer("ViT-B-32")

            with self._lock:
                self._model      = model
                self._preprocess = preprocess
                self._tokenizer  = tokenizer

            # Pre-compute text embeddings (outside lock — takes a moment)
            self._precompute_text_features()

            with self._lock:
                self._ready = True
            print(f"  CLIP ready -- {len(CANDIDATES)} object categories")

        except ImportError:
            print("  [WARN] open-clip-torch not installed. Run: pip install open-clip-torch")
        except Exception as e:
            print(f"  [WARN] CLIP failed to load: {e}")

    # Prompt templates — ensemble of 7 prompts improves accuracy a lot
    PROMPT_TEMPLATES = [
        "a photo of a {}",
        "a photo of the {}",
        "a {} in someone's hand",
        "a close up photo of a {}",
        "a {} on a table",
        "this is a {}",
        "an image of a {}",
    ]

    def _precompute_text_features(self):
        """Pre-compute averaged CLIP text embeddings using prompt ensembling."""
        import torch

        all_feats = []
        for template in self.PROMPT_TEMPLATES:
            texts  = [template.format(c) for c in CANDIDATES]
            tokens = self._tokenizer(texts)
            with torch.no_grad():
                feats = self._model.encode_text(tokens)
                feats = feats / feats.norm(dim=-1, keepdim=True)
            all_feats.append(feats)

        # Average across all prompt templates
        stacked = torch.stack(all_feats, dim=0)  # [n_templates, n_classes, dim]
        averaged = stacked.mean(dim=0)
        self._text_feats = averaged / averaged.norm(dim=-1, keepdim=True)
        self._cand_names = CANDIDATES[:]

    # ── Public: classify ─────────────────────────────────────────
    def classify(self, image_path: str, top_k: int = 5) -> str | None:
        """Identify the object. Returns natural language or None if unsure."""
        if not self._ready:
            return None

        try:
            import torch
            from PIL import Image

            img    = Image.open(image_path).convert("RGB")
            tensor = self._preprocess(img).unsqueeze(0)

            with torch.no_grad():
                img_feat = self._model.encode_image(tensor)
                img_feat = img_feat / img_feat.norm(dim=-1, keepdim=True)
                # Use logit_scale for proper CLIP scoring
                logit_scale = self._model.logit_scale.exp()
                logits = (logit_scale * img_feat @ self._text_feats.T).squeeze(0)
                probs  = logits.softmax(dim=-1)

            top_vals, top_idxs = probs.topk(top_k)
            results = [
                (self._cand_names[i], float(v))
                for v, i in zip(top_vals.tolist(), top_idxs.tolist())
            ]

            if not results:
                return None

            top_name, top_conf = results[0]
            # Debug — shows real scores in terminal
            print("  [CLIP] Top 3: " +
                  ", ".join(f"{n}({v*100:.1f}%)" for n, v in results[:3]))

            # Confident
            if top_conf > 0.25:
                return (f"That's a {top_name}, sir. "
                        f"I'm {top_conf*100:.0f}% confident.")

            # Somewhat confident — give options
            if top_conf > 0.06:
                alts = " or ".join(r[0] for r in results[:3])
                return (f"It could be {alts}, sir — "
                        f"I'm about {top_conf*100:.0f}% sure on the first.")

            return None   # Too uncertain

        except Exception as e:
            print(f"  [CLIP] classify error: {e}")
            return None

    @property
    def is_ready(self) -> bool:
        with self._lock:
            return self._ready
