import sys
import os

# Ensure we're in the right directory
sys.path.insert(0, os.path.abspath('.'))

import config
config.SPEAKER_ENABLED = False  # Disable real TTS
config.CAMERA_INDEX = -1

from main import JARVIS

def run_tests():
    print("\n--- INITIALIZING JARVIS FOR TESTING ---")
    j = JARVIS()
    
    # Mocking hardware-dependent methods
    def mock_speak(text, **kwargs):
        print(f"\n🗣️ [JARVIS SPEAKS]: {text}")
        
    def mock_what_is_on_screen():
        print(f"👁️ [JARVIS VISION]: capturing screen...")
        return "I see a LeetCode problem on your screen."
        
    def mock_camera():
        print(f"📷 [JARVIS CAMERA]: capturing webcam...")
        return "I see nothing on the webcam."
        
    def mock_gemini(prompt, **kwargs):
        print(f"🧠 [GEMINI CALLED]: {prompt}")
        return "I am Gemini, solving the problem."

    j._speak = mock_speak
    j.vision.what_is_on_screen = mock_what_is_on_screen
    j.vision.read_text_from_camera = mock_camera
    if hasattr(j, 'gemini'):
        j.gemini.ask = mock_gemini
    
    print("\n==========================================")
    print("▶️ TEST 1: Single Intent (Memory)")
    print("Command: 'Remember that I am preparing for Google interviews.'")
    print("==========================================")
    j._process_command_inner("Remember that I am preparing for Google interviews.")
    
    print("\n==========================================")
    print("▶️ TEST 2: Single Intent (Vision Routing)")
    print("Command: 'Analyze this problem on my screen.'")
    print("==========================================")
    j._process_command_inner("Analyze this problem on my screen.")
    
    print("\n==========================================")
    print("▶️ TEST 3: Multi-Intent (Memory + Vision)")
    print("Command: 'Remember that I am preparing for Google interviews. Also analyze this problem on my screen.'")
    print("==========================================")
    j._process_command_inner("Remember that I am preparing for Google interviews. Also analyze this problem on my screen.")
    print("\nDone.")

if __name__ == '__main__':
    run_tests()
