"""
JARVIS — vision/face_login.py
Face Recognition Login System.

Features:
  - Enroll your face once (50 photos captured automatically)
  - On every JARVIS startup: scan face → verify → allow or deny
  - Fallback password if camera unavailable
  - Continuous monitoring (optional): lock if unrecognized face detected

Usage:
  Enroll:       python vision/face_login.py --enroll
  Test login:   python vision/face_login.py --test
  From JARVIS:  FaceLogin().authenticate() → True/False
"""

import cv2
import os
import sys
import json
import time
import threading
import numpy as np
from pathlib import Path

_ROOT       = Path(__file__).parent.parent
_FACE_DIR   = _ROOT / "data" / "faces"
_MODEL_PATH = _ROOT / "data" / "faces" / "face_model.yml"
_META_PATH  = _ROOT / "data" / "faces" / "face_meta.json"
_TEMP_FRAME = _ROOT / "data" / "faces" / "temp_auth.jpg"

# ── Haar cascade for face detection ──────────────────────────
_CASCADE_PATH = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"


class FaceLogin:
    """
    Face Recognition Login Manager.
    Uses OpenCV LBPH (fast, lightweight, no heavy downloads).
    Falls back to DeepFace if available for higher accuracy.
    """

    def __init__(self):
        _FACE_DIR.mkdir(parents=True, exist_ok=True)
        self.face_cascade = cv2.CascadeClassifier(_CASCADE_PATH)
        self.recognizer   = cv2.face.LBPHFaceRecognizer_create(
            radius=2, neighbors=8, grid_x=8, grid_y=8
        )
        self._clahe       = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        self._model_loaded = False
        self._owner_name   = "Srini"
        self._load_meta()

        # Try loading trained model
        if _MODEL_PATH.exists():
            try:
                self.recognizer.read(str(_MODEL_PATH))
                self._model_loaded = True
            except Exception:
                pass

    # ═══════════════════════════════════════════════════════════
    # ENROLLMENT — Run once to train JARVIS on your face
    # ═══════════════════════════════════════════════════════════

    def enroll(self, name: str = "Srini", target: int = 60):
        """
        Enroll a face. Opens webcam, captures `target` frames,
        trains LBPH model, saves to disk.
        """
        print()
        print("=" * 55)
        print("  JARVIS Face Enrollment")
        print("=" * 55)
        print(f"\n  Owner: {name}")
        print(f"  Target: {target} face captures")
        print()
        print("  👤 Look at the camera naturally.")
        print("  🔄 Move your head SLOWLY left/right/up/down.")
        print("  💡 Make sure room is well-lit.")
        print()
        print("  Press Q to cancel.")
        print()

        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            print("❌ Could not open webcam!")
            return False

        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        faces_data = []
        labels     = []
        captured   = 0

        print(f"  Starting capture in 3 seconds...")
        time.sleep(3)

        while captured < target:
            ret, frame = cap.read()
            if not ret:
                break

            gray  = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray  = self._clahe.apply(gray)   # equalize for better low-light detection
            faces = self.face_cascade.detectMultiScale(
                gray, scaleFactor=1.1, minNeighbors=4,
                minSize=(50, 50)
            )

            display = frame.copy()

            for (x, y, w, h) in faces:
                # Draw rectangle
                color = (0, 255, 0) if captured < target else (0, 0, 255)
                cv2.rectangle(display, (x, y), (x+w, y+h), color, 2)

                if captured < target:
                    face_roi = gray[y:y+h, x:x+w]
                    face_roi = cv2.resize(face_roi, (160, 160))  # smaller = faster
                    faces_data.append(face_roi)
                    labels.append(0)
                    captured += 1
                    time.sleep(0.08)   # small delay for pose variety

            # Progress bar
            progress = int((captured / target) * 30)
            bar = "█" * progress + "░" * (30 - progress)
            pct = int(captured / target * 100)

            cv2.putText(display,
                f"Capturing: [{bar}] {captured}/{target}",
                (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                (0, 255, 0), 2)

            cv2.putText(display,
                f"Look around slowly! {pct}%",
                (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                (255, 255, 0), 2)

            cv2.imshow("JARVIS — Face Enrollment", display)
            print(f"\r  Captured: {captured}/{target} frames {pct}%", end="", flush=True)

            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                print("\n  Cancelled.")
                cap.release()
                cv2.destroyAllWindows()
                return False

            time.sleep(0.05)  # Small delay for variety

        cap.release()
        cv2.destroyAllWindows()

        if captured < 20:
            print(f"\n❌ Not enough frames ({captured}). Need at least 20.")
            return False

        print(f"\n\n  ✅ Captured {captured} frames!")
        print("  Training face model...", end=" ", flush=True)

        # Train LBPH recognizer
        self.recognizer.train(faces_data, np.array(labels))
        self.recognizer.save(str(_MODEL_PATH))
        self._model_loaded = True

        # Save metadata
        meta = {
            "owner":       name,
            "enrolled_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "frames":      captured,
            "model":       str(_MODEL_PATH),
        }
        self._save_meta(meta)
        self._owner_name = name

        print("done!")
        print(f"\n  ✅ Face enrolled successfully!")
        print(f"  📁 Model saved: {_MODEL_PATH}")
        print(f"\n  JARVIS will now recognize you every time! 🎉")
        return True

    # ═══════════════════════════════════════════════════════════
    # AUTHENTICATION — Called on every JARVIS startup
    # ═══════════════════════════════════════════════════════════

    def authenticate(self, timeout: int = 30) -> tuple[bool, str]:
        """
        Authenticate user via face recognition.

        Returns:
            (True, owner_name)  if recognized
            (False, "Unknown")  if not recognized
            (True, "Bypassed")  if no model enrolled (first run)
        """
        # No model yet → allow (first run)
        if not _MODEL_PATH.exists() or not self._model_loaded:
            print("  ℹ️  No face enrolled. Run with --enroll first.")
            print("  ℹ️  Allowing access (unenrolled mode).")
            return True, "User"

        print()
        print("  🔍 Face authentication starting...")
        print(f"  ⏱️  Timeout: {timeout} seconds | Press Q to enter password")
        print()

        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            print("  ⚠️  Webcam unavailable — using password fallback")
            return self._password_fallback()

        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        start_time = time.time()
        confidence_scores = []
        verified = False
        CONFIDENCE_THRESHOLD = 88   # LBPH: lower = more similar. 88 good for real-world
        REQUIRED_MATCHES     = 4    # need 4 good matches in a row

        while time.time() - start_time < timeout:
            ret, frame = cap.read()
            if not ret:
                break

            gray  = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray  = self._clahe.apply(gray)  # ← equalize contrast for better recognition
            faces = self.face_cascade.detectMultiScale(
                gray, scaleFactor=1.1, minNeighbors=4,
                minSize=(50, 50)
            )

            display    = frame.copy()
            elapsed    = int(time.time() - start_time)
            remaining  = timeout - elapsed

            # Status bar background
            cv2.rectangle(display, (0, 0), (640, 80), (0, 0, 0), -1)

            for (x, y, w, h) in faces:
                face_roi = gray[y:y+h, x:x+w]
                face_roi = cv2.resize(face_roi, (200, 200))

                try:
                    label, confidence = self.recognizer.predict(face_roi)
                    confidence_scores.append(confidence)

                    if confidence < CONFIDENCE_THRESHOLD:
                        color  = (0, 255, 0)
                        status = f"✅ Recognized! ({int(confidence)})"
                    else:
                        color  = (0, 165, 255)
                        status = f"🔍 Scanning... ({int(confidence)})"

                    cv2.rectangle(display, (x, y), (x+w, y+h), color, 3)
                    cv2.putText(display, status,
                        (x, y-10), cv2.FONT_HERSHEY_SIMPLEX,
                        0.7, color, 2)

                    # Check if enough consecutive matches
                    recent = confidence_scores[-REQUIRED_MATCHES:]
                    if (len(recent) >= REQUIRED_MATCHES and
                            all(c < CONFIDENCE_THRESHOLD for c in recent)):
                        verified = True
                        break

                except Exception:
                    pass

            if verified:
                break

            # UI overlay
            cv2.putText(display,
                f"JARVIS Face Login | Time: {remaining}s",
                (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                (0, 200, 255), 2)

            if len(faces) == 0:
                cv2.putText(display,
                    "No face detected — move CLOSER to camera",
                    (10, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                    (100, 100, 255), 2)
            else:
                cv2.putText(display,
                    f"Faces detected: {len(faces)}",
                    (10, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                    (0, 255, 100), 2)

            cv2.imshow("JARVIS Authentication", display)

            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                cap.release()
                cv2.destroyAllWindows()
                return self._password_fallback()

        cap.release()
        cv2.destroyAllWindows()

        if verified:
            avg_conf = np.mean([c for c in confidence_scores
                                if c < CONFIDENCE_THRESHOLD])
            print(f"  ✅ Face verified! Confidence: {avg_conf:.1f}")
            return True, self._owner_name
        else:
            print("  ❌ Face not recognized!")
            return self._password_fallback()

    # ═══════════════════════════════════════════════════════════
    # PASSWORD FALLBACK
    # ═══════════════════════════════════════════════════════════

    def _password_fallback(self) -> tuple[bool, str]:
        """Allow entry via password if face fails."""
        meta = self._load_meta()
        saved_pw = meta.get("password", "jarvis")

        print()
        print("  🔐 Enter password to access JARVIS:")
        for attempt in range(3):
            try:
                pw = input(f"  Password (attempt {attempt+1}/3): ").strip()
                if pw == saved_pw:
                    print("  ✅ Password correct!")
                    return True, self._owner_name
                else:
                    print("  ❌ Wrong password!")
            except KeyboardInterrupt:
                break

        print("  🚫 Access DENIED.")
        return False, "Unknown"

    # ═══════════════════════════════════════════════════════════
    # CONTINUOUS MONITORING (background thread)
    # ═══════════════════════════════════════════════════════════

    def start_monitoring(self, lock_callback=None, check_interval: int = 60):
        """
        Background thread: checks face every `check_interval` seconds.
        If unknown face detected 3× in a row → calls lock_callback().
        """
        def _monitor():
            fail_count = 0
            CONFIDENCE_THRESHOLD = 80

            while True:
                time.sleep(check_interval)

                try:
                    cap = cv2.VideoCapture(0)
                    ret, frame = cap.read()
                    cap.release()

                    if not ret:
                        continue

                    gray  = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    gray  = self._clahe.apply(gray)  # equalize for monitoring too
                    faces = self.face_cascade.detectMultiScale(
                        gray, scaleFactor=1.1, minNeighbors=4,
                        minSize=(50, 50)
                    )

                    recognized = False
                    for (x, y, w, h) in faces:
                        roi = cv2.resize(gray[y:y+h, x:x+w], (160, 160))
                        roi = self._clahe.apply(roi)   # BUG FIX: was outside loop
                        _, confidence = self.recognizer.predict(roi)
                        if confidence < CONFIDENCE_THRESHOLD:
                            recognized = True
                            break

                    if faces is not None and len(faces) > 0 and not recognized:
                        fail_count += 1
                        print(f"\n  ⚠️  Unrecognized face detected ({fail_count}/3)")
                        if fail_count >= 3 and lock_callback:
                            print("  🔒 LOCKING JARVIS — unauthorized user detected!")
                            lock_callback()
                    else:
                        fail_count = 0  # Reset on success

                except Exception:
                    pass

        t = threading.Thread(target=_monitor, daemon=True)
        t.start()
        return t

    # ═══════════════════════════════════════════════════════════
    # SET PASSWORD
    # ═══════════════════════════════════════════════════════════

    def set_password(self, password: str):
        """Set the fallback password."""
        meta = self._load_meta()
        meta["password"] = password
        self._save_meta(meta)
        print(f"  ✅ Password updated!")

    # ═══════════════════════════════════════════════════════════
    # STATUS / INFO
    # ═══════════════════════════════════════════════════════════

    def status(self) -> str:
        meta = self._load_meta()
        if not _MODEL_PATH.exists():
            return "❌ No face enrolled. Run: python vision/face_login.py --enroll"

        return (
            f"✅ Face Login Active\n"
            f"   Owner:    {meta.get('owner', 'Unknown')}\n"
            f"   Enrolled: {meta.get('enrolled_at', 'Unknown')}\n"
            f"   Frames:   {meta.get('frames', 0)} training photos\n"
            f"   Model:    {_MODEL_PATH.name}"
        )

    def is_enrolled(self) -> bool:
        return _MODEL_PATH.exists() and self._model_loaded

    # ═══════════════════════════════════════════════════════════
    # HELPERS
    # ═══════════════════════════════════════════════════════════

    def _load_meta(self) -> dict:
        try:
            if _META_PATH.exists():
                with open(_META_PATH) as f:
                    return json.load(f)
        except Exception:
            pass
        return {"owner": "Srini", "password": "jarvis"}

    def _save_meta(self, meta: dict):
        try:
            with open(_META_PATH, "w") as f:
                json.dump(meta, f, indent=2)
        except Exception as e:
            print(f"  ⚠️  Could not save meta: {e}")


# ═══════════════════════════════════════════════════════════════
# CLI ENTRY POINT
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="JARVIS Face Login")
    parser.add_argument("--enroll",   action="store_true", help="Enroll your face")
    parser.add_argument("--test",     action="store_true", help="Test face authentication")
    parser.add_argument("--status",   action="store_true", help="Show enrollment status")
    parser.add_argument("--password", type=str,            help="Set fallback password")
    parser.add_argument("--name",     type=str, default="Srini", help="Your name")
    args = parser.parse_args()

    fl = FaceLogin()

    if args.enroll:
        print("\n🎯 Starting face enrollment...")
        success = fl.enroll(name=args.name)
        if success:
            print("\n✅ Enrollment complete! JARVIS will now recognize you.")
        else:
            print("\n❌ Enrollment failed. Try again in better lighting.")

    elif args.test:
        print("\n🔍 Testing face authentication...")
        ok, name = fl.authenticate(timeout=30)
        if ok:
            print(f"\n✅ ACCESS GRANTED — Welcome, {name}!")
        else:
            print("\n❌ ACCESS DENIED")

    elif args.status:
        print()
        print(fl.status())

    elif args.password:
        fl.set_password(args.password)
        print(f"✅ Password set to: {args.password}")

    else:
        parser.print_help()
        print()
        print("Quick start:")
        print("  1. Enroll:  python vision/face_login.py --enroll")
        print("  2. Test:    python vision/face_login.py --test")
