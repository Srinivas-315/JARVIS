"""
JARVIS — vision/ocr_reader.py
Read text from anything shown to camera using EasyOCR.

Supports: Books, signs, labels, whiteboards, screens, handwriting
Languages: English + Hindi (auto-detected)
"""

from pathlib import Path

_ROOT = Path(__file__).parent.parent


class OCRReader:
    """
    Reads text from images using EasyOCR.
    Supports printed text, handwriting, signs, labels.
    """

    def __init__(self):
        self._reader = None
        self._ready  = False
        self._load()

    def _load(self):
        try:
            import easyocr
            # English + Hindi — downloads models once (~50 MB)
            print("  Loading EasyOCR (first run downloads ~50 MB)...")
            self._reader = easyocr.Reader(["en"], gpu=False, verbose=False)
            self._ready  = True
            print("  EasyOCR ready -- can read text from anything")
        except ImportError:
            print("  [WARN] easyocr not installed. Run: pip install easyocr")
        except Exception as e:
            print(f"  [WARN] EasyOCR failed: {e}")

    def read_from_camera(self) -> str:
        """
        Open camera, capture image, extract all text.
        Returns JARVIS-style response.
        """
        if not self._ready:
            return "Text reading module isn't available, sir."

        try:
            import cv2
            from brain.vision_handler import VisionHandler
            
            vh = VisionHandler()
            print("  Reading text -- capturing image...")
            best_frame, meta = vh.capture_cv2_frame()

            if best_frame is None:
                return "I couldn't capture the image from the camera, sir."

            # Save temp image
            tmp = str(_ROOT / "data" / "captures" / "ocr_tmp.jpg")
            cv2.imwrite(tmp, best_frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
            return self.read_from_file(tmp)

        except Exception as e:
            return f"I had trouble reading the text, sir: {str(e)[:60]}"

    def read_from_file(self, image_path: str) -> str:
        """Extract text from an image file."""
        if not self._ready:
            return "Text reading module isn't available, sir."
        try:
            results = self._reader.readtext(image_path)

            if not results:
                return ("I don't see any readable text in this image, sir. "
                        "Try holding it closer and steadier.")

            # Filter low confidence results
            texts = [r[1].strip() for r in results if r[2] > 0.4 and r[1].strip()]

            if not texts:
                return ("I can see text but couldn't read it clearly, sir. "
                        "Better lighting might help.")

            combined = " ".join(texts)
            if len(combined) > 300:
                combined = combined[:300] + "..."

            line_count = len(texts)
            if line_count == 1:
                return f"It says: \"{combined}\", sir."
            else:
                return (f"I can read {line_count} lines of text, sir. "
                        f"It says: \"{combined}\"")

        except Exception as e:
            return f"Text reading failed, sir: {str(e)[:60]}"

    @property
    def is_ready(self):
        return self._ready
