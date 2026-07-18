"""
JARVIS — brain/vision_handler.py
Vision — sees screen AND webcam in real-time.

Camera:  OpenCV grabs one frame → analyzed in RAM → NEVER saved to disk
Screen:  PIL ImageGrab for screen analysis
Online:  Gemini Vision API (best quality)
Offline: Ollama vision model (llava, moondream)

Voice commands:
  "What do you see"         → camera capture + describe
  "What am I holding"       → identify object in hand
  "Who am I"                → identify person (face)
  "Look at the camera"      → describe what's in front of camera
  "What's on my screen"     → screenshot analysis
"""

import base64
import io
import os
import threading
import contextlib
from pathlib import Path

import requests
from PIL import Image, ImageGrab

import config
from utils.logger import log
from utils.safe_api import safe_json_extract

GEMINI_VISION_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.5-flash:generateContent?key={key}"
)
OLLAMA_URL = "http://localhost:11434"
LOCAL_VISION_MODELS = ["moondream", "llava:7b", "llava", "bakllava"]

# Global lock — only ONE camera capture allowed at a time
_CAMERA_LOCK = threading.Lock()


class VisionHandler:
    """
    Handles screen + webcam analysis.
    Camera frames are NEVER written to disk — pure in-memory pipeline.
    """

    def __init__(self):
        self._gemini_available = bool(config.GEMINI_API_KEY)
        self._local_vision_model = None
        self._camera_index = -1  # -1 = auto-detect on first use
        self._camera_backend = -1  # cached backend (cv2.CAP_ANY etc.)
        self._detect_local_vision()

        if self._gemini_available:
            log.info("Vision: Gemini API ready ✅")
        if self._local_vision_model:
            log.info(f"Vision: Local model '{self._local_vision_model}' ready ✅")
        if not self._gemini_available and not self._local_vision_model:
            log.info("Vision: OCR-only mode (no vision AI available)")

    def _detect_local_vision(self):
        """Check if any local vision model is installed in Ollama."""
        try:
            resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=2)
            if resp.status_code == 200:
                models = [m["name"] for m in resp.json().get("models", [])]
                for preferred in LOCAL_VISION_MODELS:
                    for installed in models:
                        if preferred in installed:
                            self._local_vision_model = installed
                            return
        except Exception:
            pass

    # ── Known virtual / fake camera name fragments (case-insensitive) ────────
    _VIRTUAL_CAM_NAMES = [
        "smart connect",  # NVIDIA Smart Connect Camera  ← confirmed on this laptop
        "nvidia broadcast",  # NVIDIA Broadcast virtual cam
        "nvidia virtual",  # generic NVIDIA virtual
        "obs virtual",  # OBS Studio virtual camera
        "obs-camera",
        "droidcam",  # phone-as-webcam (virtual on PC side)
        "iriun",  # another phone-as-webcam
        "epoccam",
        "xsplit",
        "manycam",
        "splitcam",
        "virtual camera",
        "screen capture",
        "logi capture",  # Logitech screen capture
        "snap camera",  # Snap AR virtual cam
    ]

    def _get_real_camera_indices(self) -> list:
        """
        Query Windows for camera friendly names and return the OpenCV indices
        of REAL physical cameras (skipping known NVIDIA / virtual cameras).

        Uses PowerShell Get-PnpDevice — fast, no extra dependencies.
        Falls back to [0,1,2,3] if the query fails.

        The DirectShow enumeration order that OpenCV uses matches the order
        returned by Get-PnpDevice -Class Camera on Windows 10/11.
        """
        import subprocess

        try:
            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    "Get-PnpDevice -Class Camera -Status OK "
                    "| Sort-Object InstanceId "
                    "| Select-Object -ExpandProperty FriendlyName",
                ],
                capture_output=True,
                text=True,
                timeout=6,
            )
            names = [n.strip() for n in result.stdout.strip().splitlines() if n.strip()]
            if not names:
                raise ValueError("empty camera list")

            log.info(f"Windows cameras: {names}")

            real_indices = []
            virtual_indices = []
            for i, name in enumerate(names):
                name_lower = name.lower()
                is_virtual = any(v in name_lower for v in self._VIRTUAL_CAM_NAMES)
                if is_virtual:
                    log.info(f"  [VIRTUAL] idx={i}: {name}")
                    virtual_indices.append(i)
                else:
                    log.info(f"  [REAL]    idx={i}: {name}")
                    real_indices.append(i)

            if real_indices:
                return real_indices
            # All cameras are virtual — try all anyway as last resort
            log.warning("All cameras appear virtual — trying all indices")
            return list(range(len(names)))

        except Exception as e:
            log.warning(f"Camera enumeration failed ({e}) — will try idx 0-3")
            return list(range(4))

    def _is_screen_capture(self, frame, cv2) -> bool:
        """
        Return True if the camera frame looks like a screen capture
        (i.e. it is the NVIDIA Smart Connect Camera or similar virtual cam
        that captures the desktop instead of the physical sensor).

        Method: grab a fresh screenshot and compare it to the camera frame
        at low resolution using Pearson correlation.  A real webcam image
        will look nothing like the desktop (correlation < 0.40).
        A virtual screen-capture camera will be nearly identical (corr > 0.65).
        """
        try:
            import numpy as np
            from PIL import ImageGrab

            # Grab a tiny (64×36) version of the current screen
            screenshot = ImageGrab.grab()
            scr = np.array(screenshot.convert("RGB"), dtype=np.float32)
            scr_small = cv2.resize(scr, (64, 36)).flatten()

            # Resize camera frame to the same tiny size
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB).astype(np.float32)
            cam_small = cv2.resize(frame_rgb, (64, 36)).flatten()

            if cam_small.std() < 1.0 or scr_small.std() < 1.0:
                return False  # can't correlate flat images

            corr = float(np.corrcoef(cam_small, scr_small)[0, 1])
            log.info(f"Screen-correlation check: {corr:.3f}")

            # > 0.65 → camera is basically showing the screen → virtual
            return corr > 0.65

        except Exception as e:
            log.debug(f"Screen-correlation check error: {e}")
            return False  # if we can't check, assume it might be real

    def _open_real_webcam(self, cv2):
        """
        Find and open the REAL physical webcam, automatically skipping
        NVIDIA Smart Connect Camera and other virtual screen-capture cameras.

        Two-layer detection:
          Layer 1 — Name filter: query Windows camera names via PowerShell,
                    skip any index whose name matches a known virtual camera
                    (NVIDIA Smart Connect, OBS, DroidCam, etc.)
          Layer 2 — Screen correlation: capture a screenshot and compare it
                    pixel-by-pixel with the camera frame.  If they look the
                    same (corr > 0.65) the camera is capturing the screen.

        Backend order: CAP_ANY first (works with both MSMF and DSHOW drivers),
        then DSHOW as a last resort if nothing was found.
        """
        import time

        import numpy as np

        # Get the OpenCV indices that correspond to real physical cameras
        real_indices = self._get_real_camera_indices()
        # Also prepare a full fallback list (all indices, real first)
        all_indices = real_indices + [i for i in range(6) if i not in real_indices]

        backends = [
            (cv2.CAP_ANY, "CAP_ANY"),
            (cv2.CAP_MSMF, "MSMF"),
            (cv2.CAP_DSHOW, "DSHOW"),
        ]

        def _try(idx: int, backend: int, backend_name: str):
            """Open one (idx, backend) pair; validate and return cap or None."""
            cap = None
            try:
                cap = cv2.VideoCapture(idx, backend)
                if not cap.isOpened():
                    if cap:
                        cap.release()
                    return None

                # Let the sensor settle and drain stale buffered frames
                time.sleep(0.4)
                for _ in range(3):
                    cap.grab()

                ret, frame = cap.read()
                if not ret or frame is None:
                    cap.release()
                    return None

                # ── Layer 2 validation: reject screen-capture virtual cams ──
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                std = float(np.std(gray))

                # Completely blank / solid-colour frame → definitely not a webcam
                if std < 6.0:
                    log.info(
                        f"Skipping idx={idx} {backend_name}: "
                        f"blank/solid frame (std={std:.1f})"
                    )
                    cap.release()
                    return None

                # Screen-correlation check — catches NVIDIA Smart Connect
                if self._is_screen_capture(frame, cv2):
                    log.info(
                        f"Skipping idx={idx} {backend_name}: "
                        f"screen-capture virtual camera detected"
                    )
                    cap.release()
                    return None

                w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                log.info(
                    f"Real webcam confirmed: idx={idx} {backend_name} "
                    f"{w}x{h} std={std:.1f}"
                )
                self._camera_index = idx
                self._camera_backend = backend  # cache the backend too
                return cap  # caller must release

            except Exception as e:
                log.debug(f"Camera idx={idx} {backend_name} error: {e}")
                if cap:
                    try:
                        cap.release()
                    except Exception:
                        pass
                return None

        # ── Phase 1: preferred (real) indices with every backend ──────────────
        log.info(f"Camera search Phase 1 — real indices {real_indices}")
        for backend, bname in backends:
            for idx in real_indices:
                cap = _try(idx, backend, bname)
                if cap:
                    return cap

        # ── Phase 2: all indices (in case name filter was wrong) ──────────────
        log.info(
            "Camera search Phase 2 — all indices (name filter may have been wrong)"
        )
        for backend, bname in backends:
            for idx in all_indices:
                if idx in real_indices:
                    continue  # already tried
                cap = _try(idx, backend, bname)
                if cap:
                    return cap

        log.warning(
            "No real webcam found. "
            "Possible causes:\n"
            "  • Camera in use by Teams / Zoom / OBS — close them first\n"
            "  • Windows privacy blocks Python — Settings → Privacy → Camera → "
            "enable 'Let desktop apps access your camera'\n"
            "  • Only NVIDIA Smart Connect Camera present — disable it in "
            "Device Manager → Cameras → Smart Connect Camera → Disable"
        )
        return None

    @contextlib.contextmanager
    def acquire_camera(self):
        """
        Thread-safe context manager to stream from the real physical webcam.
        Acquires _CAMERA_LOCK, opens the camera (skipping virtual cams),
        yields the cv2.VideoCapture object, and ensures it's safely released.
        """
        # ── Acquire lock — wait up to 20 s for any prior capture to finish ──
        if not _CAMERA_LOCK.acquire(timeout=20):
            log.warning(
                "Camera lock timeout (20 s) — prior capture may have hung. "
                "Forcing lock reset."
            )
            try:
                _CAMERA_LOCK.release()
            except RuntimeError:
                pass
            yield None
            return

        import cv2
        import time

        cap = None
        try:
            # ── Use cached index on subsequent calls (skips slow discovery) ──
            if self._camera_index >= 0 and self._camera_backend >= 0:
                log.info(f"Using cached camera idx={self._camera_index}")
                cap = cv2.VideoCapture(self._camera_index, self._camera_backend)
                if cap.isOpened():
                    time.sleep(0.3)
                    for _ in range(3):
                        cap.grab()
                    ret, frame = cap.read()
                    if ret and frame is not None:
                        log.info("Cached camera OK")
                    else:
                        cap.release()
                        cap = None
                
                # Cached camera no longer works — fall through to discovery
                if not cap:
                    log.warning("Cached camera failed — re-discovering")
                    self._camera_index = -1
                    self._camera_backend = -1

            # ── Find the real physical webcam (MSMF first, DSHOW last) ────
            if cap is None:
                log.info("Opening webcam...")
                cap = self._open_real_webcam(cv2)
                if cap is None:
                    log.warning(
                        "No real webcam found. "
                        "Check: camera not blocked by Teams/Zoom, privacy settings OK, "
                        "not only an NVIDIA virtual camera present."
                    )
            
            yield cap
        except ImportError:
            log.warning("OpenCV not installed — run: pip install opencv-python")
            yield None
        except Exception as e:
            log.error(f"Camera capture error: {e}")
            yield None
        finally:
            if cap:
                try:
                    cap.release()
                except Exception:
                    pass
            try:
                _CAMERA_LOCK.release()
            except RuntimeError:
                pass

    def capture_cv2_frame(self) -> tuple:
        """
        Grab the best frame from the real physical webcam.
        Returns: (frame: np.ndarray, meta: dict) or (None, None).
        meta contains camera_index, backend, resolution.
        """
        import time
        import cv2
        import numpy as np

        with self.acquire_camera() as cap:
            if cap is None:
                return None, None

            # ── Auto-exposure settle + buffer drain ───────────────────────
            log.info("Camera open — letting auto-exposure settle (1 s)...")
            time.sleep(1.0)
            for _ in range(5):
                cap.grab()  # discard stale buffered frames

            # ── Collect frames — pick the SHARPEST one ────────────────────
            best_frame = None
            best_sharp = -1.0
            n_collected = 0

            for _ in range(8):
                ret, frame = cap.read()
                if not ret or frame is None:
                    time.sleep(0.05)
                    continue
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                sharp = float(cv2.Laplacian(gray, cv2.CV_64F).var())
                if sharp > best_sharp:
                    best_sharp = sharp
                    best_frame = frame.copy()
                n_collected += 1
                time.sleep(0.06)

            log.info(
                f"Camera released — collected {n_collected} frames, "
                f"best sharpness={best_sharp:.1f}"
            )

            if best_frame is None:
                log.warning("No valid frames captured from webcam")
                return None, None

            meta = {
                "camera_index": self._camera_index,
                "backend": self._camera_backend,
                "resolution": (
                    int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                    int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                )
            }
            return best_frame, meta

    def _capture_camera_frame(self) -> Image.Image:
        """
        Grab the best frame from the real physical webcam as a PIL Image.
        """
        import cv2

        frame, meta = self.capture_cv2_frame()
        if frame is None:
            return None

        # ── BGR → RGB → PIL (entirely in RAM) ────────────────────────
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(frame_rgb)
        log.info(f"Frame ready: {pil_img.size[0]}x{pil_img.size[1]} px")
        return pil_img

    def look_at_camera(self, prompt: str = None) -> str:
        """Capture one camera frame and describe what JARVIS sees."""
        if prompt is None:
            prompt = (
                "This is a live webcam image. "
                "Tell me: (1) Is there a person visible? (2) What are the main objects visible? "
                "Answer in 1-2 short sentences like you're talking to the person. "
                "Example: 'I can see you sitting at a desk with a laptop and a coffee mug.'"
            )
        img = self._capture_camera_frame()
        if img is None:
            return (
                "I can't access the camera, sir. "
                "Make sure the webcam is connected and not in use by another app."
            )
        return self._analyze_image(img, prompt)

    def identify_objects(self) -> str:
        """What objects does the camera see?"""
        img = self._capture_camera_frame()
        if img is None:
            return "Camera unavailable, sir."
        return self._analyze_image(
            img,
            "This is a live webcam image. "
            "Identify and name all clearly visible OBJECTS in the scene. "
            "Start with the most prominent object. "
            "Format: list the object names only, separated by commas. "
            "Example: 'laptop, coffee mug, notebook, pen' "
            "Do NOT describe colours or backgrounds — just name the objects.",
        )

    def identify_person(self) -> str:
        """Who is in front of the camera?"""
        img = self._capture_camera_frame()
        if img is None:
            return "Camera unavailable, sir."
        return self._analyze_image(
            img,
            "This is a live webcam image. "
            "Is there a person visible? "
            "If yes: describe them in 1 sentence (gender, approximate age, what they're wearing, expression). "
            "If no person: say 'No person visible in frame.' "
            "Keep it natural and conversational.",
        )

    def what_am_i_holding(self) -> str:
        """Identify what the person is holding in front of the camera."""
        img = self._capture_camera_frame()
        if img is None:
            return "Camera unavailable, sir."
        return self._analyze_image(
            img,
            "This is a live webcam image of a person. "
            "Look carefully at what the person is holding in their hands or showing to the camera. "
            "Name the specific object as precisely as possible. "
            "Examples: 'a book titled X', 'a smartphone', 'a water bottle', 'a pen', 'a TV remote'. "
            "If their hands are empty or not visible, say 'Nothing visible in hands.' "
            "Answer in one short sentence only.",
        )

    def read_text_from_camera(self) -> str:
        """Read any text visible in the camera frame (book, paper, board)."""
        img = self._capture_camera_frame()
        if img is None:
            return "Camera unavailable, sir."
        return self._analyze_image(
            img,
            "This is a live webcam image. "
            "Look for any TEXT visible in the image — on paper, a book, a whiteboard, a screen, a label, or anywhere. "
            "If you find text: transcribe it exactly as written. "
            "If no readable text is visible: say 'No readable text found in frame.' "
            "Do not describe the image — only output the text you can read.",
        )

    def describe_scene(self) -> str:
        """Give a detailed scene description of what the camera sees."""
        img = self._capture_camera_frame()
        if img is None:
            return "Camera unavailable, sir."
        return self._analyze_image(
            img,
            "Describe this scene in detail. What is in the environment? "
            "What is happening? Answer in 2-3 sentences.",
        )

    # ===================================================================
    # SCREEN — screenshot analysis
    # ===================================================================

    def analyze_screen(self, prompt: str = None) -> str:
        """Take a screenshot and describe what's on screen."""
        if prompt is None:
            prompt = (
                "Describe what's on this screen in 1-2 short sentences. "
                "Be casual and direct, like telling a friend."
            )
        try:
            log.info("Capturing screen for vision analysis...")
            screenshot = ImageGrab.grab()
            return self._analyze_image(screenshot, prompt)
        except Exception as e:
            log.error(f"Screen analysis error: {e}")
            return "Couldn't capture the screen."

    def what_is_on_screen(self) -> str:
        return self.analyze_screen(
            "What app or website is open? Describe in 1 sentence casually."
        )

    def read_text_from_screen(self) -> str:
        try:
            import pytesseract

            screenshot = ImageGrab.grab()
            text = pytesseract.image_to_string(screenshot).strip()
            if text:
                lines = [l.strip() for l in text.splitlines() if l.strip()]
                return "Screen text: " + " | ".join(lines[:10])
        except ImportError:
            pass
        except Exception:
            pass
        return self.analyze_screen(
            "List only the important text visible on this screen. Keep it short."
        )

    def summarize_screen(self) -> str:
        return self.analyze_screen(
            "What is the user doing right now? Answer in 1 casual sentence."
        )

    def find_on_screen(self, target: str) -> str:
        return self.analyze_screen(
            f"Is there anything related to '{target}' visible on this screen? "
            f"Answer yes or no, and describe where."
        )

    def check_error_on_screen(self) -> str:
        return self.analyze_screen(
            "Is there any error message or warning on this screen? "
            "If yes, what does it say? Keep it short."
        )

    def analyze_image_file(
        self, image_path: str, prompt: str = "Describe this image."
    ) -> str:
        path = Path(image_path)
        if not path.exists():
            return f"Image not found: {image_path}"
        try:
            img = Image.open(path)
            return self._analyze_image(img, prompt)
        except Exception:
            return "Couldn't analyze that image."

    def save_screenshot(self, filename: str = None) -> str:
        """Save screenshot to disk — only called when user explicitly asks."""
        try:
            if not filename:
                from datetime import datetime

                filename = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            desktop = os.path.join(os.path.expanduser("~"), "Desktop")
            filepath = os.path.join(desktop, filename)
            ImageGrab.grab().save(filepath)
            log.info(f"Screenshot saved: {filepath}")
            return f"Screenshot saved to Desktop as {filename}."
        except Exception as e:
            log.error(f"Screenshot save error: {e}")
            return "Couldn't save screenshot."

    # ===================================================================
    # AI ANALYSIS — Gemini -> Local model -> OCR
    # ===================================================================

    def _analyze_image(self, image: Image.Image, prompt: str) -> str:
        """Analyze image: Gemini Vision -> local Ollama -> OCR fallback."""
        # Resize to max 1280px wide — faster API, less RAM
        if image.size[0] > 1280:
            ratio = 1280 / image.size[0]
            image = image.resize((1280, int(image.size[1] * ratio)), Image.LANCZOS)

        if self._gemini_available:
            result = self._gemini_analyze(image, prompt)
            if result:
                return result

        if self._local_vision_model:
            result = self._local_analyze(image, prompt)
            if result:
                return result

        return self._ocr_fallback(image)

    def _to_base64(self, image: Image.Image) -> str:
        """Convert PIL Image to base64 string — entirely in RAM."""
        buf = io.BytesIO()
        image.save(buf, format="JPEG", quality=85)
        return base64.b64encode(buf.getvalue()).decode()

    def _gemini_analyze(self, image: Image.Image, prompt: str) -> str:
        try:
            image_b64 = self._to_base64(image)
            url = GEMINI_VISION_URL.format(key=config.GEMINI_API_KEY)
            body = {
                "contents": [
                    {
                        "parts": [
                            {"text": prompt},
                            {
                                "inline_data": {
                                    "mime_type": "image/jpeg",
                                    "data": image_b64,
                                }
                            },
                        ]
                    }
                ]
            }
            resp = requests.post(url, json=body, timeout=20)
            if resp.status_code == 200:
                parts = safe_json_extract(
                    resp.json(), "candidates", 0, "content", "parts", default=[]
                )
                if not parts:
                    log.error("Gemini Vision response missing parts field")
                    return ""
                return next(
                    (
                        p["text"]
                        for p in reversed(parts)
                        if "text" in p and not p.get("thought", False)
                    ),
                    "",
                ).strip()
            elif resp.status_code == 429:
                log.warning(
                    "Gemini Vision: quota exceeded — disabling for this session."
                )
                self._gemini_available = False
                return ""
        except Exception as e:
            log.warning(f"Gemini Vision error: {e}")
        return ""

    def _local_analyze(self, image: Image.Image, prompt: str) -> str:
        try:
            image_b64 = self._to_base64(image)
            resp = requests.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": self._local_vision_model,
                    "prompt": prompt,
                    "images": [image_b64],
                    "stream": False,
                    "options": {"num_predict": 100, "temperature": 0.3},
                },
                timeout=60,
            )
            if resp.status_code == 200:
                return resp.json().get("response", "").strip()
        except Exception as e:
            log.warning(f"Local vision error: {e}")
        return ""

    def _ocr_fallback(self, image: Image.Image) -> str:
        try:
            import pytesseract

            text = pytesseract.image_to_string(image).strip()
            if text:
                lines = [l.strip() for l in text.splitlines() if l.strip()][:5]
                return "I can see text: " + ", ".join(lines)
        except ImportError:
            pass
        except Exception:
            pass
        return (
            "My vision AI is temporarily unavailable, sir. "
            "This could be because the API quota is at limit. "
            "Try again later, or install a local vision model: ollama pull moondream"
        )


# Quick test
if __name__ == "__main__":
    vision = VisionHandler()
    print("Testing camera identification...")
    print(vision.identify_objects())
