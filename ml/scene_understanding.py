"""
JARVIS — ml/scene_understanding.py
Local Scene Understanding using YOLO + CLIP.

What it does:
  - YOLO: Detects ALL objects in an image with bounding boxes + confidence
  - CLIP: Understands the SCENE ("a person working at a desk")
  - Combined: "I see a laptop, coffee mug, and notebook. Looks like a work setup, sir."

Works 100% offline using pre-trained models.
YOLO v8 nano = 6MB, runs at 30+ FPS on your RTX 4050.

Usage:
    python ml/scene_understanding.py           # test with webcam
    python ml/scene_understanding.py photo.jpg  # test with image file
"""

import os
import sys
import time
import json
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import log

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"


# ═══════════════════════════════════════════════════════════════
#  YOLO Object Detector
# ═══════════════════════════════════════════════════════════════
class YOLODetector:
    """
    YOLOv8 nano object detection — detects 80 object classes.
    Model auto-downloads on first use (6 MB).

    Classes include: person, bicycle, car, motorcycle, bus, truck,
    traffic light, fire hydrant, stop sign, bench, bird, cat, dog,
    horse, backpack, umbrella, handbag, suitcase, frisbee, bottle,
    wine glass, cup, fork, knife, spoon, bowl, banana, apple,
    sandwich, orange, broccoli, carrot, pizza, donut, cake, chair,
    couch, potted plant, bed, dining table, toilet, tv, laptop,
    mouse, remote, keyboard, cell phone, microwave, oven, toaster,
    sink, refrigerator, book, clock, vase, scissors, teddy bear,
    hair drier, toothbrush ...and more (80 total).
    """

    def __init__(self):
        self._model = None
        self._ready = False
        self._load()

    def _load(self):
        """Load YOLOv8 nano model."""
        try:
            from ultralytics import YOLO
            self._model = YOLO("yolov8n.pt")  # auto-downloads 6MB model
            self._ready = True
            log.info("YOLO v8 nano loaded — 80 object classes")
        except ImportError:
            log.info("YOLO not installed. Install with: pip install ultralytics")
        except Exception as e:
            log.warning(f"YOLO load error: {e}")

    def detect(self, image_path: str, confidence: float = 0.3) -> list:
        """
        Detect all objects in an image.

        Returns list of:
            {"class": "laptop", "confidence": 0.92, "bbox": [x1,y1,x2,y2]}
        """
        if not self._ready:
            return []

        try:
            results = self._model(image_path, verbose=False, conf=confidence)

            detections = []
            for r in results:
                for box in r.boxes:
                    cls_id = int(box.cls[0])
                    cls_name = r.names[cls_id]
                    conf = float(box.conf[0])
                    bbox = box.xyxy[0].tolist()
                    detections.append({
                        "class": cls_name,
                        "confidence": round(conf, 3),
                        "bbox": [round(b) for b in bbox],
                    })

            # Sort by confidence
            detections.sort(key=lambda x: -x["confidence"])
            return detections

        except Exception as e:
            log.error(f"YOLO detection error: {e}")
            return []

    def detect_and_annotate(self, image_path: str, output_path: str = None) -> tuple:
        """
        Detect objects AND save annotated image with bounding boxes.
        Returns (detections_list, annotated_image_path).
        """
        if not self._ready:
            return [], None

        try:
            results = self._model(image_path, verbose=False, conf=0.3)

            detections = []
            for r in results:
                for box in r.boxes:
                    cls_id = int(box.cls[0])
                    detections.append({
                        "class": r.names[cls_id],
                        "confidence": round(float(box.conf[0]), 3),
                    })

            # Save annotated image
            if not output_path:
                p = Path(image_path)
                output_path = str(p.parent / f"{p.stem}_detected{p.suffix}")

            annotated = results[0].plot()
            import cv2
            cv2.imwrite(output_path, annotated)

            return detections, output_path

        except Exception as e:
            log.error(f"YOLO annotate error: {e}")
            return [], None

    @property
    def is_ready(self) -> bool:
        return self._ready


# ═══════════════════════════════════════════════════════════════
#  CLIP Scene Classifier (uses existing vision module)
# ═══════════════════════════════════════════════════════════════
class SceneClassifier:
    """
    Uses CLIP to understand the overall SCENE of an image.
    Not just objects — but context like "office", "kitchen", "outdoor park".
    """

    SCENE_CATEGORIES = [
        # Indoor scenes
        "a home office with computer and desk",
        "a kitchen with cooking appliances",
        "a living room with sofa and TV",
        "a bedroom with bed and pillows",
        "a bathroom with mirror and sink",
        "a classroom or study area",
        "a restaurant or cafe",
        "a gym or fitness area",
        "a library with books",
        "a workshop or garage",
        # Outdoor scenes
        "an outdoor park with trees",
        "a city street with buildings",
        "a parking lot with cars",
        "a garden with plants and flowers",
        "a beach with sand and water",
        "a mountain or hiking trail",
        "a sports field or playground",
        # Activities
        "a person working on a computer",
        "a person eating food",
        "a person reading a book",
        "a person exercising or working out",
        "a person cooking in kitchen",
        "a video call or meeting",
        "a group of people talking",
        # Objects on desk
        "a desk with laptop and accessories",
        "food and drinks on a table",
        "electronics and gadgets",
        "stationery and office supplies",
        "a messy desk with papers",
    ]

    def __init__(self):
        self._clip = None
        self._ready = False
        self._load()

    def _load(self):
        """Try to use existing CLIP classifier from vision module."""
        try:
            import open_clip
            import torch

            self._model, _, self._preprocess = open_clip.create_model_and_transforms(
                "ViT-B-32", pretrained="openai"
            )
            self._model.eval()
            self._tokenizer = open_clip.get_tokenizer("ViT-B-32")

            # Pre-compute scene text features
            tokens = self._tokenizer(self.SCENE_CATEGORIES)
            with torch.no_grad():
                self._text_feats = self._model.encode_text(tokens)
                self._text_feats = self._text_feats / self._text_feats.norm(dim=-1, keepdim=True)

            self._ready = True
            log.info(f"Scene classifier ready — {len(self.SCENE_CATEGORIES)} scene types")
        except ImportError:
            log.info("open-clip not installed for scene classification")
        except Exception as e:
            log.warning(f"Scene classifier load error: {e}")

    def classify_scene(self, image_path: str, top_k: int = 3) -> list:
        """
        Classify the overall scene of an image.

        Returns list of:
            {"scene": "a home office with computer", "confidence": 0.75}
        """
        if not self._ready:
            return []

        try:
            import torch
            from PIL import Image

            img = Image.open(image_path).convert("RGB")
            tensor = self._preprocess(img).unsqueeze(0)

            with torch.no_grad():
                img_feat = self._model.encode_image(tensor)
                img_feat = img_feat / img_feat.norm(dim=-1, keepdim=True)
                logit_scale = self._model.logit_scale.exp()
                logits = (logit_scale * img_feat @ self._text_feats.T).squeeze(0)
                probs = logits.softmax(dim=-1)

            top_vals, top_idxs = probs.topk(top_k)
            results = []
            for val, idx in zip(top_vals.tolist(), top_idxs.tolist()):
                results.append({
                    "scene": self.SCENE_CATEGORIES[idx],
                    "confidence": round(val, 3),
                })
            return results

        except Exception as e:
            log.error(f"Scene classification error: {e}")
            return []

    @property
    def is_ready(self) -> bool:
        return self._ready


# ═══════════════════════════════════════════════════════════════
#  Unified Scene Understanding
# ═══════════════════════════════════════════════════════════════
class SceneUnderstanding:
    """
    Combines YOLO + CLIP for complete scene understanding.

    YOLO answers: WHAT objects are here?
    CLIP answers: WHAT is happening here?
    Combined: Natural language description of the scene.
    """

    def __init__(self):
        self._yolo = YOLODetector()
        self._scene = SceneClassifier()
        log.info(f"SceneUnderstanding: YOLO={'ready' if self._yolo.is_ready else 'needs install'}, CLIP={'ready' if self._scene.is_ready else 'needs install'}")

    def analyze(self, image_path: str) -> dict:
        """
        Full scene analysis.

        Returns:
            {
                "objects": [{"class": "laptop", "confidence": 0.92}, ...],
                "scene": "a home office with computer",
                "description": "I see a laptop, cup, and keyboard. Looks like a work setup, sir.",
                "object_count": 3,
            }
        """
        result = {
            "objects": [],
            "scene": "unknown",
            "description": "",
            "object_count": 0,
        }

        # YOLO: detect objects
        objects = self._yolo.detect(image_path) if self._yolo.is_ready else []
        result["objects"] = objects
        result["object_count"] = len(objects)

        # CLIP: classify scene
        scenes = self._scene.classify_scene(image_path) if self._scene.is_ready else []
        if scenes:
            result["scene"] = scenes[0]["scene"]

        # Build natural description
        result["description"] = self._build_description(objects, scenes)

        return result

    def analyze_and_annotate(self, image_path: str) -> dict:
        """Analyze scene AND save annotated image."""
        result = self.analyze(image_path)

        if self._yolo.is_ready:
            _, annotated_path = self._yolo.detect_and_annotate(image_path)
            result["annotated_image"] = annotated_path

        return result

    def _build_description(self, objects: list, scenes: list) -> str:
        """Build a natural JARVIS-style description."""
        parts = []

        if objects:
            # Group and count objects
            from collections import Counter
            obj_counts = Counter(o["class"] for o in objects)
            obj_parts = []
            for name, count in obj_counts.most_common(5):
                if count > 1:
                    obj_parts.append(f"{count} {name}s")
                else:
                    obj_parts.append(f"a {name}")

            if len(obj_parts) == 1:
                parts.append(f"I can see {obj_parts[0]}")
            elif len(obj_parts) == 2:
                parts.append(f"I can see {obj_parts[0]} and {obj_parts[1]}")
            else:
                last = obj_parts[-1]
                rest = ", ".join(obj_parts[:-1])
                parts.append(f"I can see {rest}, and {last}")

        if scenes and scenes[0]["confidence"] > 0.1:
            scene_desc = scenes[0]["scene"]
            parts.append(f"This looks like {scene_desc}")

        if not parts:
            return "I couldn't analyze the scene clearly, sir."

        return ". ".join(parts) + ", sir."

    def describe_camera(self) -> str:
        """Capture from webcam and describe what JARVIS sees."""
        try:
            import cv2

            cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                return "Camera unavailable, sir."

            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

            # Capture a few frames, keep the best
            best_frame, best_sharp = None, 0
            for _ in range(15):
                ret, frame = cap.read()
                if not ret:
                    continue
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                sharp = cv2.Laplacian(gray, cv2.CV_64F).var()
                if sharp > best_sharp:
                    best_sharp = sharp
                    best_frame = frame.copy()

            cap.release()

            if best_frame is None:
                return "Couldn't capture from camera, sir."

            # Save temp image
            temp_path = str(DATA_DIR / "scene_capture.jpg")
            cv2.imwrite(temp_path, best_frame, [cv2.IMWRITE_JPEG_QUALITY, 85])

            # Analyze
            result = self.analyze(temp_path)
            return result["description"]

        except Exception as e:
            return f"Scene analysis error: {e}"

    @property
    def is_ready(self) -> bool:
        return self._yolo.is_ready or self._scene.is_ready


# ═══════════════════════════════════════════════════════════════
#  Test
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("=" * 50)
    print("  JARVIS Scene Understanding — Test")
    print("=" * 50)

    scene = SceneUnderstanding()

    print(f"\n  YOLO: {'READY' if scene._yolo.is_ready else 'NOT INSTALLED — run: pip install ultralytics'}")
    print(f"  CLIP: {'READY' if scene._scene.is_ready else 'NOT INSTALLED — run: pip install open-clip-torch'}")

    # Check if image path was provided as argument
    if len(sys.argv) > 1:
        image_path = sys.argv[1]
        if os.path.exists(image_path):
            print(f"\n  Analyzing: {image_path}")
            result = scene.analyze_and_annotate(image_path)
            print(f"\n  Objects found: {result['object_count']}")
            for obj in result["objects"][:10]:
                print(f"    - {obj['class']} ({obj['confidence']:.0%})")
            print(f"\n  Scene: {result['scene']}")
            print(f"\n  Description: {result['description']}")
            if result.get("annotated_image"):
                print(f"\n  Annotated image: {result['annotated_image']}")
        else:
            print(f"\n  File not found: {image_path}")
    else:
        # Use webcam
        if scene._yolo.is_ready or scene._scene.is_ready:
            print("\n  Capturing from webcam...")
            description = scene.describe_camera()
            print(f"\n  JARVIS says: {description}")
        else:
            print("\n  Install dependencies first:")
            print("    pip install ultralytics    # for YOLO (6MB model)")
            print("    pip install open-clip-torch # for CLIP scene understanding")

    print("\n  DONE!")
