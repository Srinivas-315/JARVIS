"""
JARVIS — brain/auto_trainer.py
Auto-generate training data using Gemini AI + retrain intent classifier.

Usage:
    python brain/auto_trainer.py

What it does:
  1. Asks Gemini to generate 40 voice commands per intent (31 intents = 1240 new)
  2. Adds Indian English + casual speech phrases manually
  3. Merges with existing training_data.py
  4. Retrains the intent classifier
  5. Saves new model to brain/models/
  6. Reports accuracy improvement
"""

import sys
import os
import json
import pickle
import time
import re
from pathlib import Path

# ── Setup path ────────────────────────────────────────────────
_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

from utils.logger import log

# ══════════════════════════════════════════════════════════════
# INTENTS TO GENERATE FOR
# ══════════════════════════════════════════════════════════════

INTENTS = [
    "open_app", "close_app", "system_volume", "system_brightness",
    "screenshot", "weather", "news", "youtube", "google_search",
    "browser_search", "wikipedia", "send_email", "read_email",
    "reminder", "timer", "whatsapp", "time_date", "joke",
    "media", "shopping", "vision_screen", "file_open", "file_create",
    "code_run", "shutdown", "stop", "reset", "greeting",
    "memory", "calendar", "chat",
]

# ══════════════════════════════════════════════════════════════
# INTENT DESCRIPTIONS (helps Gemini understand each intent)
# ══════════════════════════════════════════════════════════════

INTENT_DESCRIPTIONS = {
    "open_app":       "opening/launching an application on the computer",
    "close_app":      "closing/quitting/killing an application",
    "system_volume":  "controlling audio volume (up, down, mute, unmute)",
    "system_brightness": "controlling screen brightness",
    "screenshot":     "taking a screenshot or screen capture",
    "weather":        "asking about weather, temperature, rain forecast",
    "news":           "asking for news, headlines, current events",
    "youtube":        "playing videos or searching on YouTube",
    "google_search":  "searching Google or the internet for something",
    "browser_search": "searching in a web browser",
    "wikipedia":      "asking factual questions, 'what is', 'who is', 'tell me about'",
    "send_email":     "composing or sending an email to someone",
    "read_email":     "reading, checking, or opening inbox emails",
    "reminder":       "setting a reminder, alarm, or notification",
    "timer":          "setting a countdown timer or stopwatch",
    "whatsapp":       "sending a WhatsApp message to someone",
    "time_date":      "asking current time, date, or day",
    "joke":           "asking for a joke, funny story, or humor",
    "media":          "controlling music/Spotify (play, pause, skip, next)",
    "shopping":       "searching for products on Amazon, Flipkart, Myntra etc",
    "vision_screen":  "asking what's on screen, reading screen content, screen analysis",
    "file_open":      "opening a file or folder in file explorer",
    "file_create":    "creating a new file or saving notes",
    "code_run":       "writing code, creating script files, running programs",
    "shutdown":       "shutting down, restarting, sleeping the computer",
    "stop":           "stopping/quitting JARVIS, saying goodbye",
    "reset":          "clearing conversation history or starting fresh",
    "greeting":       "saying hello, hi, good morning to JARVIS",
    "memory":         "telling JARVIS personal facts to remember",
    "calendar":       "adding events, checking schedule, managing calendar",
    "chat":           "general conversation, questions, asking for help",
}

# ══════════════════════════════════════════════════════════════
# HAND-CRAFTED EXTRA COMMANDS (Indian English + casual)
# ══════════════════════════════════════════════════════════════

EXTRA_COMMANDS = [
    # ── Indian English style ──────────────────────────────────
    ("jarvis yaar open youtube", "youtube"),
    ("bhai what is the time", "time_date"),
    ("ek second mera schedule dekho", "calendar"),
    ("weather kaisa hai aaj", "weather"),
    ("yaar play some music na", "media"),
    ("bhai send message to rahul", "whatsapp"),
    ("kya news hai aaj", "news"),
    ("jarvis bata mujhe time", "time_date"),
    ("chrome kholo", "open_app"),
    ("screenshot le bhai", "screenshot"),
    ("volume badha do", "system_volume"),
    ("volume kam karo", "system_volume"),
    ("screen thodi bright karo", "system_brightness"),

    # ── Short/lazy commands ───────────────────────────────────
    ("yt", "youtube"),
    ("screenshot", "screenshot"),
    ("time", "time_date"),
    ("date", "time_date"),
    ("weather", "weather"),
    ("news", "news"),
    ("music", "media"),
    ("mute", "system_volume"),
    ("unmute", "system_volume"),
    ("hello", "greeting"),
    ("hi jarvis", "greeting"),
    ("bye", "stop"),
    ("quit jarvis", "stop"),

    # ── Multi-step / complex commands ─────────────────────────
    ("open chrome and go to google", "open_app"),
    ("what time is my next meeting", "calendar"),
    ("play some good music on spotify", "media"),
    ("search and play despacito", "youtube"),
    ("send hi to mom on whatsapp", "whatsapp"),
    ("remind me to call dad at 6pm", "reminder"),
    ("check if i have any meetings today", "calendar"),
    ("open youtube and search coding tutorials", "youtube"),
    ("set volume to max", "system_volume"),
    ("make my screen brighter please", "system_brightness"),

    # ── More calendar ─────────────────────────────────────────
    ("do i have class tomorrow", "calendar"),
    ("when is my next exam", "calendar"),
    ("add cricket match to calendar", "calendar"),
    ("schedule project meeting friday 2pm", "calendar"),
    ("what's on my schedule this week", "calendar"),
    ("am i free tomorrow afternoon", "calendar"),
    ("add reminder for mom birthday", "calendar"),
    ("cancel my 5pm appointment", "calendar"),

    # ── More memory ───────────────────────────────────────────
    ("my name is srini", "memory"),
    ("i am from hyderabad", "memory"),
    ("remember i like biryani", "memory"),
    ("my college is jntu", "memory"),
    ("i wake up at 6am", "memory"),
    ("i study computer science", "memory"),
    ("save my phone number", "memory"),
    ("remember that i prefer dark mode", "memory"),
    ("what is my name", "memory"),
    ("what do you remember about me", "memory"),
    ("forget what i said", "memory"),

    # ── More code runner ──────────────────────────────────────
    ("write a python script to read files", "code_run"),
    ("generate a hello world program", "code_run"),
    ("create a simple calculator in python", "code_run"),
    ("make a new html file", "code_run"),
    ("write code to send an email", "code_run"),
    ("run the last script", "code_run"),
    ("execute my python file", "code_run"),
    ("run this code please", "code_run"),

    # ── More vision/screen ────────────────────────────────────
    ("what does my screen show", "vision_screen"),
    ("read the text on screen", "vision_screen"),
    ("what app is currently open", "vision_screen"),
    ("any error message on screen", "vision_screen"),
    ("describe what i see on my monitor", "vision_screen"),
    ("can you see my screen", "vision_screen"),
    ("what is displayed right now", "vision_screen"),

    # ── WhatsApp variations ───────────────────────────────────
    ("whatsapp banty saying i am coming", "whatsapp"),
    ("send a message to priya on whatsapp", "whatsapp"),
    ("text ganesh good morning", "whatsapp"),
    ("message my mom", "whatsapp"),
    ("drop a text to sarvani", "whatsapp"),
    ("ping rahul on whatsapp", "whatsapp"),
    ("send voice note to friend", "whatsapp"),

    # ── Casual chat ───────────────────────────────────────────
    ("tell me a fact", "chat"),
    ("what do you know", "chat"),
    ("help me out", "chat"),
    ("i need your help", "chat"),
    ("give me advice", "chat"),
    ("what should i do", "chat"),
    ("recommend me something", "chat"),
    ("i am bored", "chat"),
    ("talk to me", "chat"),
    ("are you smart", "chat"),
    ("how intelligent are you", "chat"),

    # ── Shutdown ──────────────────────────────────────────────
    ("shut it down", "shutdown"),
    ("please restart", "shutdown"),
    ("system restart", "shutdown"),
    ("put to sleep", "shutdown"),
    ("turn off system", "shutdown"),
    ("switch off computer", "shutdown"),

    # ── Greeting variations ───────────────────────────────────
    ("good morning jarvis", "greeting"),
    ("good night jarvis", "greeting"),
    ("hey there", "greeting"),
    ("are you awake", "greeting"),
    ("you there jarvis", "greeting"),
    ("jarvis you there", "greeting"),
    ("can you hear me", "greeting"),
    ("testing testing", "greeting"),

    # ── Media control ─────────────────────────────────────────
    ("volume up on spotify", "media"),
    ("play the next one", "media"),
    ("go to previous track", "media"),
    ("shuffle my songs", "media"),
    ("i want to listen to music", "media"),
    ("play something chill", "media"),
    ("play something loud", "media"),
    ("pause the track", "media"),
    ("resume the track", "media"),
    ("stop the music please", "media"),
]

# ══════════════════════════════════════════════════════════════
# GEMINI DATA GENERATOR
# ══════════════════════════════════════════════════════════════

def generate_with_gemini(intent: str, count: int = 40) -> list[tuple[str, str]]:
    """Ask Gemini to generate `count` voice commands for an intent."""
    try:
        import google.generativeai as genai
        import config

        key = config.GEMINI_API_KEY if hasattr(config, 'GEMINI_API_KEY') else None
        if not key:
            # Try .env
            from dotenv import load_dotenv
            load_dotenv(_ROOT / ".env")
            key = os.getenv("GEMINI_API_KEY")

        if not key:
            print("  ⚠️  No Gemini API key found, skipping Gemini generation")
            return []

        genai.configure(api_key=key)
        model = genai.GenerativeModel("gemini-1.5-flash")

        desc = INTENT_DESCRIPTIONS.get(intent, intent)

        prompt = f"""You are helping train a voice assistant. Generate exactly {count} short, realistic voice commands that a user might say for this intent: "{intent}" ({desc}).

Rules:
- Each command on a new line
- No numbers, bullets, or punctuation at the start
- 2 to 10 words each
- Mix formal and casual speech
- Include some partial/abbreviated commands
- Include some Indian English style
- NO repetition, maximum variety
- Do NOT include the intent name itself as a word

Generate exactly {count} commands now:"""

        response = model.generate_content(prompt)
        raw = response.text.strip()

        # Parse lines
        lines = [l.strip().lower() for l in raw.split('\n') if l.strip()]
        # Clean up: remove leading numbers/bullets
        cleaned = []
        for line in lines:
            line = re.sub(r'^[\d\.\-\*\•]+\s*', '', line)
            line = re.sub(r'["\']', '', line)
            line = line.strip()
            if 2 <= len(line.split()) <= 12 and line:
                cleaned.append((line, intent))

        return cleaned[:count]

    except Exception as e:
        print(f"  ⚠️  Gemini error for {intent}: {e}")
        return []


# ══════════════════════════════════════════════════════════════
# MAIN AUTO-TRAINER
# ══════════════════════════════════════════════════════════════

def run_auto_trainer():
    print()
    print("=" * 60)
    print("  JARVIS Auto-Trainer — Powered by Gemini AI")
    print("=" * 60)
    print()

    # Step 1: Load existing training data
    from brain.training_data import TRAINING_DATA as EXISTING
    existing_texts = set(t.lower() for t, _ in EXISTING)
    print(f"📊 Existing examples: {len(EXISTING)}")
    print(f"   Intents: {len(set(l for _, l in EXISTING))}")
    print()

    # Step 2: Generate with Gemini
    all_new = []
    print("🤖 Generating with Gemini AI...")
    print("-" * 40)

    for i, intent in enumerate(INTENTS, 1):
        print(f"  [{i:02d}/{len(INTENTS)}] {intent}...", end=" ", flush=True)
        generated = generate_with_gemini(intent, count=40)

        # Deduplicate
        unique = [(t, l) for t, l in generated if t not in existing_texts]
        for t, l in unique:
            existing_texts.add(t)
        all_new.extend(unique)

        print(f"✅ +{len(unique)} new")
        time.sleep(0.8)  # Rate limit

    print()
    print(f"✅ Gemini generated: {len(all_new)} new examples")

    # Step 3: Add hand-crafted extra commands
    extra_unique = [(t, l) for t, l in EXTRA_COMMANDS if t.lower() not in existing_texts]
    all_new.extend(extra_unique)
    print(f"✅ Hand-crafted added: {len(extra_unique)} new examples")

    # Step 4: Combine all data
    combined = list(EXISTING) + all_new
    print(f"\n📊 Total training examples: {len(combined)}")
    print(f"   Improvement: +{len(all_new)} new examples ({len(all_new)/len(EXISTING)*100:.0f}% more)")

    # Step 5: Write updated training_data.py
    training_file = _ROOT / "brain" / "training_data.py"
    _write_training_file(combined, training_file)
    print(f"\n✅ Saved: {training_file}")

    # Step 6: Retrain model
    print("\n🧠 Retraining intent classifier...")
    _retrain_model(combined)

    print("\n" + "=" * 60)
    print("  ✅ JARVIS is now SMARTER!")
    print("=" * 60)
    print("\nRun JARVIS: python main.py --gui")
    print()


def _write_training_file(data: list, path: Path):
    """Write the training data to a Python file."""
    from collections import Counter
    counts = Counter(l for _, l in data)

    lines = [
        '"""',
        'JARVIS — brain/training_data.py',
        'Auto-generated + hand-crafted training data.',
        f'Total: {len(data)} examples | Intents: {len(counts)}',
        '"""',
        '',
        'TRAINING_DATA = [',
    ]

    # Group by intent for readability
    from itertools import groupby
    sorted_data = sorted(data, key=lambda x: x[1])
    for intent, group in groupby(sorted_data, key=lambda x: x[1]):
        lines.append(f'')
        lines.append(f'    # ── {intent} ({counts[intent]} examples) ──')
        for text, _ in group:
            escaped = text.replace("'", "\\'")
            lines.append(f"    ('{escaped}', '{intent}'),")

    lines.append(']')
    lines.append('')

    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))


def _retrain_model(data: list):
    """Retrain the intent classifier with new data."""
    from sklearn.pipeline import Pipeline
    from sklearn.svm import LinearSVC
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.model_selection import cross_val_score, train_test_split
    from sklearn.metrics import classification_report
    import warnings
    warnings.filterwarnings('ignore')

    texts  = [t.lower() for t, _ in data]
    labels = [l for _, l in data]

    # Train/test split
    X_train, X_test, y_train, y_test = train_test_split(
        texts, labels, test_size=0.1, random_state=42, stratify=labels
    )

    # Build model
    model = Pipeline([
        ('tfidf', TfidfVectorizer(
            ngram_range=(1, 3),
            sublinear_tf=True,
            min_df=1,
            analyzer='word',
        )),
        ('clf', LinearSVC(
            C=2.0,
            max_iter=3000,
            class_weight='balanced'
        ))
    ])

    model.fit(X_train, y_train)
    test_acc = model.score(X_test, y_test)

    # Cross-validation
    print("  Running 5-fold cross-validation...")
    cv_scores = cross_val_score(model, texts, labels, cv=5, scoring='accuracy')

    print(f"\n  📊 Results:")
    print(f"     Test accuracy:  {test_acc:.1%}")
    print(f"     CV mean:        {cv_scores.mean():.1%} ± {cv_scores.std():.1%}")
    print(f"     CV scores:      {[f'{s:.1%}' for s in cv_scores]}")

    # Show any mistakes
    y_pred = model.predict(X_test)
    mistakes = [(X_test[i], y_test[i], y_pred[i])
                for i in range(len(X_test)) if y_test[i] != y_pred[i]]
    if mistakes:
        print(f"\n  ❌ Test mistakes ({len(mistakes)}):")
        for txt, true, pred in mistakes[:5]:
            print(f"     '{txt}' → predicted {pred} (true: {true})")
    else:
        print("\n  ✅ Zero mistakes on test set!")

    # Retrain on ALL data for best production model
    model.fit(texts, labels)

    # Save
    model_dir = _ROOT / "brain" / "models"
    model_dir.mkdir(parents=True, exist_ok=True)
    model_path = model_dir / "intent_classifier.pkl"

    with open(model_path, 'wb') as f:
        pickle.dump(model, f)

    # Save metadata
    meta = {
        "test_accuracy": round(test_acc, 4),
        "cv_mean": round(cv_scores.mean(), 4),
        "total_examples": len(data),
        "intents": sorted(list(set(labels))),
        "trained_date": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(model_dir / "model_metadata.json", "w") as f:
        json.dump(meta, f, indent=2)

    print(f"\n  ✅ Model saved: {model_path}")
    print(f"  ✅ Metadata saved: {model_dir / 'model_metadata.json'}")


# ══════════════════════════════════════════════════════════════
# QUICK TEST
# ══════════════════════════════════════════════════════════════

def test_model():
    """Test the trained model with sample commands."""
    model_path = _ROOT / "brain" / "models" / "intent_classifier.pkl"
    if not model_path.exists():
        print("No model found. Run auto_trainer first.")
        return

    with open(model_path, 'rb') as f:
        model = pickle.load(f)

    tests = [
        # Easy
        "open youtube", "what time is it", "take a screenshot",
        # Medium
        "add meeting tomorrow at 3pm", "remind me to drink water",
        "my name is srini", "create hello.py",
        # Hard / casual
        "jarvis yaar open chrome", "bhai what is the time",
        "yaar play some music na", "chrome kholo",
        "yt", "weather kaisa hai", "wapp message to rahul",
        # Voice switch (should be chat)
        "change voice to george", "what voice are you using",
    ]

    print("\n🧪 Model Test:")
    print("-" * 50)
    for t in tests:
        pred = model.predict([t.lower()])[0]
        print(f"  [{pred:<20}] '{t}'")


# ══════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="JARVIS Auto-Trainer")
    parser.add_argument("--test-only", action="store_true",
                        help="Only test existing model, don't retrain")
    parser.add_argument("--no-gemini", action="store_true",
                        help="Skip Gemini generation, only add hand-crafted commands")
    args = parser.parse_args()

    if args.test_only:
        test_model()
    elif args.no_gemini:
        # Fast mode: just add hand-crafted + retrain
        print("Running without Gemini (hand-crafted only mode)...")
        from brain.training_data import TRAINING_DATA as EXISTING
        existing_texts = set(t.lower() for t, _ in EXISTING)
        extra = [(t, l) for t, l in EXTRA_COMMANDS if t.lower() not in existing_texts]
        combined = list(EXISTING) + extra
        print(f"Total: {len(combined)} examples (+{len(extra)} new)")
        _write_training_file(combined, _ROOT / "brain" / "training_data.py")
        _retrain_model(combined)
        print("Done!")
    else:
        run_auto_trainer()
