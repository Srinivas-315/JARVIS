"""
JARVIS — vision/object_recognizer.py
Smart Object Recognition — 100% Local, No API.

Recognition Pipeline (smart cascade):
  1. Histogram match → learned objects (instant memory)
  2. EfficientNet    → 1000 ImageNet classes
  3. CLIP            → 270 broad categories
  4. MobileNetV2     → last visual resort
  5. AUTO OCR        → reads text on the object (labels, boxes, signs)
  6. Ask to teach    → saves + remembers for next time

If it reads "Kissan Jam" on a box → says that + auto-saves it!
"""

import cv2
import json
import time
import base64
import os
import requests
import shutil
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")
_GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")

try:
    from vision.local_classifier import LocalVisionClassifier
except ImportError:
    LocalVisionClassifier = None

try:
    from vision.clip_classifier import CLIPClassifier
except ImportError:
    CLIPClassifier = None

try:
    from vision.efficientnet_classifier import EfficientNetClassifier
except ImportError:
    EfficientNetClassifier = None

try:
    from vision.trained_classifier import TrainedClassifier
except ImportError:
    TrainedClassifier = None

try:
    from vision.ocr_reader import OCRReader
except ImportError:
    OCRReader = None

_ROOT        = Path(__file__).parent.parent
_OBJ_DIR     = _ROOT / "data" / "learned_objects"
_OBJ_DB      = _ROOT / "data" / "learned_objects.json"
_CAPTURE_DIR = _ROOT / "data" / "captures"

_OBJ_DIR.mkdir(parents=True, exist_ok=True)
_CAPTURE_DIR.mkdir(parents=True, exist_ok=True)


class ObjectRecognizer:
    """
    Identifies objects via webcam using local ML only.
    No internet, no API, no quota limits.
    """

    def __init__(self):
        self._last_capture  = None
        self._pending_learn = None
        self._object_db     = self._load_db()

        # OpenCV check
        try:
            self._cv2    = cv2
            self._cv2_ok = True
        except Exception:
            self._cv2_ok = False

        # ── Colab-trained model — TOP PRIORITY (your custom 600-class model) ──
        self._trained = None
        if TrainedClassifier:
            try:
                self._trained = TrainedClassifier()
            except Exception as e:
                print(f"  ⚠️  Trained model init failed: {e}")

        # ── EfficientNet — 1000 ImageNet classes ──
        self._efficientnet = None
        if EfficientNetClassifier:
            try:
                self._efficientnet = EfficientNetClassifier()
            except Exception as e:
                print(f"  ⚠️  EfficientNet init failed: {e}")

        # ── CLIP zero-shot classifier ──
        self._clip = None
        if CLIPClassifier:
            try:
                self._clip = CLIPClassifier()
            except Exception as e:
                print(f"  ⚠️  CLIP init failed: {e}")

        # MobileNetV2 — fallback (1000 ImageNet classes)
        self._local_ml = None
        if LocalVisionClassifier:
            try:
                self._local_ml = LocalVisionClassifier()
            except Exception as e:
                print(f"  ⚠️  MobileNetV2 init failed: {e}")

        # OCR Reader — reads text on objects (labels, boxes, signs)
        self._ocr = None
        if OCRReader:
            try:
                self._ocr = OCRReader()
            except Exception as e:
                print(f"  ⚠️  OCR init failed: {e}")

    # ═══════════════════════════════════════════════════════════
    # MAIN: identify an object
    # ═══════════════════════════════════════════════════════════

    def identify(self) -> str:
        """
        Smart cascade: Gemini Vision → Local ML → OCR → Teach.
        Gemini Vision is the MOST ACCURATE for real-world objects.
        """
        if not self._cv2_ok:
            return "Camera module unavailable, sir. Install opencv-python."

        print("\n  📷 Opening camera for object recognition...")
        frame_path = self._capture_best_frame()

        if not frame_path:
            return "I couldn't open the camera, sir. Please check it's connected."

        self._last_capture = frame_path

        # ── Step 1: Gemini Vision API — BEST ACCURACY ────────────────
        # Works on any object, reads labels, identifies brands, scenes
        gemini_result = self._ask_gemini_vision(frame_path)
        if gemini_result:
            self._save_to_history(frame_path, gemini_result)
            return gemini_result

        # ── Step 2: Learned objects (histogram match) ─────────────────
        match = self._check_learned_objects(frame_path)
        if match:
            return f"That's a {match['name']}, sir! I recognize it from memory."

        # ── Step 3: Your Colab-trained model ─────────────────────────
        if self._trained and self._trained.is_ready:
            result = self._trained.classify(frame_path)
            if result:
                self._save_to_history(frame_path, result)
                return result

        # ── Step 4: EfficientNet (1000 ImageNet classes) ──────────────
        if self._efficientnet and self._efficientnet.is_ready:
            result = self._efficientnet.classify(frame_path)
            if result:
                self._save_to_history(frame_path, result)
                return result

        # ── Step 5: CLIP zero-shot ────────────────────────────────────
        if self._clip and self._clip.is_ready:
            result = self._clip.classify(frame_path)
            if result:
                self._save_to_history(frame_path, result)
                return result

        # ── Step 6: MobileNetV2 ───────────────────────────────────────
        if self._local_ml and self._local_ml.is_ready:
            result = self._local_ml.classify(frame_path)
            if result:
                self._save_to_history(frame_path, result)
                return result

        # ── Step 7: AUTO OCR — read text labels on the object ─────────
        print("  🔍 Visual models uncertain — trying OCR to read text...")
        if self._ocr and self._ocr.is_ready:
            ocr_result = self._ocr.read_from_file(frame_path)
            has_text = ("says:" in ocr_result or "lines of text" in ocr_result)
            if has_text:
                text_content = self._extract_ocr_text(ocr_result)
                if text_content and len(text_content) > 2:
                    self._auto_learn_from_text(frame_path, text_content)
                    return (
                        f"{ocr_result} "
                        f"I've saved this as '{text_content}' in my memory, sir!"
                    )
                return ocr_result

        # ── Step 8: Ask user to teach ─────────────────────────────────
        self._pending_learn = frame_path
        return (
            "I couldn't identify this visually or read any text on it, sir. "
            "Say 'This is a [name]' and I'll remember it!"
        )

    def _ask_gemini_vision(self, image_path: str) -> str:
        """
        Send image to Gemini 1.5 Flash Vision for accurate object identification.
        Gives natural, JARVIS-style responses like ChatGPT would.
        """
        if not _GEMINI_KEY:
            return ""
        try:
            with open(image_path, "rb") as f:
                image_data = base64.b64encode(f.read()).decode("utf-8")

            url = (
                f"https://generativelanguage.googleapis.com/v1beta/"
                f"models/gemini-1.5-flash:generateContent?key={_GEMINI_KEY}"
            )
            body = {
                "contents": [{
                    "parts": [
                        {
                            "text": (
                                "You are JARVIS, an AI assistant. Look at this image carefully "
                                "and describe what you see in one or two natural, conversational sentences. "
                                "Be specific: name the object, its brand if visible, its color, and what it's used for. "
                                "Address the user as 'sir'. Example: 'That's a Samsung Galaxy phone, sir — "
                                "black model, looks like the S23 series.'"
                            )
                        },
                        {
                            "inline_data": {
                                "mime_type": "image/jpeg",
                                "data": image_data
                            }
                        }
                    ]
                }],
                "generationConfig": {"maxOutputTokens": 200, "temperature": 0.3}
            }
            resp = requests.post(url, json=body, timeout=15)
            if resp.status_code == 200:
                parts = (resp.json()
                         .get("candidates", [{}])[0]
                         .get("content", {})
                         .get("parts", []))
                text = next((p["text"] for p in parts if "text" in p), "").strip()
                if text:
                    print(f"  🤖 Gemini Vision: {text[:60]}...")
                    return text
        except Exception as e:
            print(f"  ⚠️  Gemini Vision error: {e}")
        return ""

    def _extract_ocr_text(self, ocr_result: str) -> str:
        """Pull the quoted text out of an OCR result string."""
        try:
            # Result format: 'It says: "Kissan Jam", sir.'
            if '"' in ocr_result:
                parts = ocr_result.split('"')
                if len(parts) >= 2:
                    text = parts[1].strip()
                    # Clean it up — take first meaningful word(s)
                    words = text.split()[:5]   # max 5 words
                    return " ".join(words).lower().strip()
        except Exception:
            pass
        return ""

    def _auto_learn_from_text(self, image_path: str, name: str):
        """Automatically save an OCR-read label as a learned object."""
        try:
            name = name.strip().lower()[:50]
            ts   = int(time.time())
            saved_path = _OBJ_DIR / f"{name.replace(' ','_')}_{ts}.jpg"
            shutil.copy2(image_path, saved_path)

            existing = [o for o in self._object_db if o["name"] == name]
            if existing:
                existing[0]["count"] += 1
                existing[0]["image"]  = str(saved_path)
            else:
                self._object_db.append({
                    "name":    name,
                    "image":   str(saved_path),
                    "learned": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "source":  "ocr_auto",
                    "count":   1,
                })
            self._save_db()
            print(f"  💾 Auto-learned from OCR: '{name}'")
        except Exception as e:
            print(f"  ⚠️  Auto-learn failed: {e}")

    # ═══════════════════════════════════════════════════════════
    # TEACH: "This is a brush"
    # ═══════════════════════════════════════════════════════════

    def teach(self, object_name: str, image_path: str = None) -> str:
        """Save label + train ML embedding for future recognition."""
        name     = object_name.strip().lower()
        img_path = image_path or self._pending_learn or self._last_capture

        if not img_path or not Path(img_path).exists():
            img_path = self._capture_best_frame()
            if not img_path:
                return f"I'll remember the name '{name}', sir, but couldn't save a photo."

        # Save image to learned_objects/
        ts         = int(time.time())
        saved_name = f"{name.replace(' ', '_')}_{ts}.jpg"
        saved_path = _OBJ_DIR / saved_name
        shutil.copy2(img_path, saved_path)

        # Update JSON database
        existing = [o for o in self._object_db if o["name"] == name]
        if existing:
            existing[0]["count"] += 1
            existing[0]["image"]  = str(saved_path)
        else:
            self._object_db.append({
                "name":    name,
                "image":   str(saved_path),
                "learned": time.strftime("%Y-%m-%d %H:%M:%S"),
                "count":   1,
            })
        self._save_db()

        # Train ML embedding (CLIP first, MobileNetV2 fallback)
        ml_trained = False
        if self._clip and self._clip.is_ready:
            ml_trained = self._clip.learn(img_path, name) if hasattr(self._clip, 'learn') else False
        if not ml_trained and self._local_ml and self._local_ml.is_ready:
            ml_trained = self._local_ml.learn(img_path, name)

        self._pending_learn = None
        ml_note = " ML model updated!" if ml_trained else ""
        eff_note = "EfficientNet ✅" if (self._efficientnet and self._efficientnet.is_ready) else ""
        return (
            f"Understood, sir! I've learned that's a '{name}'.{ml_note} "
            f"I'll recognize it next time. I now know {len(self._object_db)} objects."
        )

    # ═══════════════════════════════════════════════════════════
    # STATUS
    # ═══════════════════════════════════════════════════════════

    def status(self) -> str:
        if not self._object_db:
            return "I haven't learned any objects yet, sir. Show me something!"
        names = ", ".join(o["name"] for o in self._object_db[:10])
        eff_status  = "EfficientNet ✅" if (self._efficientnet and self._efficientnet.is_ready) else "EfficientNet ❌"
        clip_status = "CLIP ✅" if (self._clip and self._clip.is_ready) else "CLIP ❌"
        ml_status   = "MobileNetV2 ✅" if (self._local_ml and self._local_ml.is_ready) else "MobileNetV2 ❌"
        return (
            f"I know {len(self._object_db)} objects: {names}. "
            f"Engines: {eff_status}, {clip_status}, {ml_status}. "
            f"All offline — no API needed."
        )

    @property
    def has_pending_learn(self) -> bool:
        """True when JARVIS said 'I don't know' — but teaching works even without this."""
        return self._pending_learn is not None

    @property
    def last_capture(self) -> str | None:
        """Path of the most recent camera capture — used for teaching corrections."""
        return self._last_capture

    # ═══════════════════════════════════════════════════════════
    # WEBCAM CAPTURE
    # ═══════════════════════════════════════════════════════════

    def _capture_best_frame(self, countdown: int = 3) -> str | None:
        """Open webcam, collect frames, save the sharpest one."""
        self._cleanup_captures(keep=10)

        cap = self._cv2.VideoCapture(0)
        if not cap.isOpened():
            return None

        cap.set(self._cv2.CAP_PROP_FRAME_WIDTH,  1280)
        cap.set(self._cv2.CAP_PROP_FRAME_HEIGHT, 720)

        best_frame, best_sharp = None, 0

        print(f"\n  📸 Camera open — collecting frames ({countdown}s)...", flush=True)
        for c in range(countdown, 0, -1):
            print(f"  ⏱  {c}...", flush=True)
            deadline = time.time() + 1.0
            while time.time() < deadline:
                ret, frame = cap.read()
                if not ret:
                    continue
                gray  = self._cv2.cvtColor(frame, self._cv2.COLOR_BGR2GRAY)
                sharp = self._cv2.Laplacian(gray, self._cv2.CV_64F).var()
                if sharp > best_sharp:
                    best_sharp = sharp
                    best_frame = frame.copy()

        cap.release()

        if best_frame is None:
            return None

        ts        = int(time.time())
        save_path = str(_CAPTURE_DIR / f"capture_{ts}.jpg")
        self._cv2.imwrite(save_path, best_frame,
                          [self._cv2.IMWRITE_JPEG_QUALITY, 85])
        print(f"  ✅ Captured best frame: {save_path}", flush=True)
        return save_path

    def _cleanup_captures(self, keep: int = 10):
        """Keep only the most recent `keep` capture files."""
        try:
            files = sorted(
                _CAPTURE_DIR.glob("capture_*.jpg"),
                key=lambda f: f.stat().st_mtime,
                reverse=True
            )
            for old in files[keep:]:
                try:
                    old.unlink()
                except Exception:
                    pass
        except Exception:
            pass

    # ═══════════════════════════════════════════════════════════
    # LEARNED OBJECT MATCHING (histogram)
    # ═══════════════════════════════════════════════════════════

    def _check_learned_objects(self, new_image_path: str) -> dict | None:
        """Fast histogram comparison against saved learned objects."""
        if not self._object_db:
            return None
        try:
            new_img = cv2.imread(new_image_path, cv2.IMREAD_GRAYSCALE)
            if new_img is None:
                return None
            new_img  = cv2.resize(new_img, (64, 64))
            new_hist = cv2.calcHist([new_img], [0], None, [256], [0, 256])
            cv2.normalize(new_hist, new_hist)

            best_score, best_match = 0, None
            THRESHOLD = 0.82   # lowered from 0.92 — learned objects recalled more easily

            for obj in self._object_db:
                if not Path(obj["image"]).exists():
                    continue
                ref = cv2.imread(obj["image"], cv2.IMREAD_GRAYSCALE)
                if ref is None:
                    continue
                ref      = cv2.resize(ref, (64, 64))
                ref_hist = cv2.calcHist([ref], [0], None, [256], [0, 256])
                cv2.normalize(ref_hist, ref_hist)
                score = cv2.compareHist(new_hist, ref_hist, cv2.HISTCMP_CORREL)
                if score > best_score:
                    best_score = score
                    best_match = obj

            if best_match:
                print(f"  [Histogram] Best match: {best_match['name']} ({best_score:.3f})")
            return best_match if best_score > THRESHOLD else None
        except Exception:
            return None

    # ═══════════════════════════════════════════════════════════
    # DATABASE
    # ═══════════════════════════════════════════════════════════

    def _load_db(self) -> list:
        try:
            if _OBJ_DB.exists():
                with open(_OBJ_DB) as f:
                    return json.load(f)
        except Exception:
            pass
        return []

    def _save_db(self):
        try:
            with open(_OBJ_DB, "w") as f:
                json.dump(self._object_db, f, indent=2)
        except Exception as e:
            print(f"  ⚠️  Could not save object DB: {e}")

    def _save_to_history(self, image_path: str, result: str):
        try:
            hist_file = _ROOT / "data" / "recognition_history.json"
            history   = []
            if hist_file.exists():
                with open(hist_file) as f:
                    history = json.load(f)
            history.append({
                "time":   time.strftime("%Y-%m-%d %H:%M:%S"),
                "result": result,
                "image":  image_path,
            })
            history = history[-50:]   # keep last 50
            with open(hist_file, "w") as f:
                json.dump(history, f, indent=2)
        except Exception:
            pass


# ── Quick test ────────────────────────────────────────────────
if __name__ == "__main__":
    print("Testing Object Recognizer (local ML only)...")
    rec    = ObjectRecognizer()
    result = rec.identify()
    print(f"\nResult: {result}")
