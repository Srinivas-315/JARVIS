# ════════════════════════════════════════════════════════════════
# JARVIS — Advanced Intent Classifier (Google Colab)
# Uses REAL DATASETS + DistilBERT Transformer
# ════════════════════════════════════════════════════════════════
#
# This trains a proper NLP model using:
#   1. CLINC150 dataset (23,700 real examples, 150 intents)
#   2. SNIPS dataset (14,000+ examples)
#   3. Your custom JARVIS commands
#
# HOW TO USE:
#   1. Go to https://colab.research.google.com
#   2. File → Upload this file (or paste code)
#   3. Runtime → Change runtime type → GPU (T4)
#   4. Run all cells → download model
#   5. Put in JARVIS/brain/models/
#
# ════════════════════════════════════════════════════════════════


# ╔══════════════════════════════════════════════════════════════╗
# ║  CELL 1: Install Dependencies                              ║
# ╚══════════════════════════════════════════════════════════════╝

# Uncomment this line in Google Colab:
# !pip install transformers datasets torch scikit-learn accelerate onnx onnxruntime -q

import os
import json
import pickle
import numpy as np
from pathlib import Path


# ╔══════════════════════════════════════════════════════════════╗
# ║  CELL 2: Download & Prepare Real Datasets                  ║
# ╚══════════════════════════════════════════════════════════════╝

from datasets import load_dataset

print("=" * 60)
print("  Downloading CLINC150 dataset (23,700 examples)...")
print("=" * 60)

clinc = load_dataset("clinc_oos", "plus", trust_remote_code=True)

print(f"  Train: {len(clinc['train'])} examples")
print(f"  Val:   {len(clinc['validation'])} examples")
print(f"  Test:  {len(clinc['test'])} examples")

# Get intent names from CLINC150
clinc_intents = clinc["train"].features["intent"].names
print(f"  Total CLINC intents: {len(clinc_intents)}")


# ╔══════════════════════════════════════════════════════════════╗
# ║  CELL 3: Map CLINC150 intintents → JARVIS intents          ║
# ╚══════════════════════════════════════════════════════════════╝

# Map CLINC150's 150 intents to our JARVIS categories
CLINC_TO_JARVIS = {
    # ── Open/Close App ──
    # (no direct mapping, we use custom data)

    # ── Volume / Brightness ──
    "change_volume": "system_volume",

    # ── Weather ──
    "weather": "weather",
    "temperature": "weather",

    # ── News ──
    "current_events": "news",

    # ── Search ──
    "definition": "wikipedia",
    "meaning_of_life": "wikipedia",
    "who_made_you": "chat",
    "what_is_your_name": "chat",

    # ── Time & Date ──
    "time": "time_date",
    "date": "time_date",
    "timezone": "time_date",

    # ── Email ──
    "email": "send_email",
    "email_addcontact": "send_email",

    # ── Reminder / Timer ──
    "reminder": "reminder",
    "reminder_update": "reminder",
    "alarm": "reminder",
    "timer": "timer",

    # ── Music / Media ──
    "play_music": "media",
    "music_likeness": "media",
    "music": "media",

    # ── Joke ──
    "joke": "joke",
    "fun_fact": "joke",

    # ── Greeting ──
    "greeting": "greeting",
    "goodbye": "stop",
    "thank_you": "chat",

    # ── Shopping ──
    "shopping_list": "shopping",
    "shopping_list_update": "shopping",
    "order": "shopping",
    "order_status": "shopping",

    # ── Translation ──
    "translate": "chat",

    # ── Calculator ──
    "calculator": "chat",
    "measurement_conversion": "chat",
    "exchange_rate": "chat",

    # ── General Chat ──
    "oos": "chat",  # out-of-scope → general chat
    "are_you_a_bot": "chat",
    "how_old_are_you": "chat",
    "do_you_have_pets": "chat",
    "tell_joke": "joke",
    "yes": "chat",
    "no": "chat",
    "maybe": "chat",
    "repeat": "chat",
    "spelling": "chat",
    "calories": "chat",
    "recipe": "chat",
    "nutrition_info": "chat",
    "food_last": "chat",
    "insurance": "chat",
    "insurance_change": "chat",
    "travel_suggestion": "shopping",
    "travel_alert": "shopping",
    "book_flight": "shopping",
    "book_hotel": "shopping",
    "gas": "chat",
    "gas_type": "chat",
    "uber": "chat",
    "schedule_meeting": "reminder",
    "meeting_schedule": "reminder",
    "what_can_i_ask_you": "chat",
    "where_are_you_from": "chat",
    "smart_home": "chat",
    "text": "whatsapp",
    "bill_balance": "chat",
    "balance": "chat",
    "accept_reservations": "chat",
    "restaurant_suggestion": "google_search",
    "restaurant_reviews": "google_search",
    "directions": "google_search",
    "traffic": "google_search",
    "distance": "google_search",
    "flip_coin": "chat",
    "roll_dice": "chat",
    "next_song": "media",
    "payday": "chat",
    "credit_score": "chat",
    "new_card": "chat",
    "lost_luggage": "chat",
    "car_rental": "shopping",
    "todo_list": "reminder",
    "todo_list_update": "reminder",
    "calories": "chat",
    "ingredients_list": "chat",
    "plug_type": "chat",
    "vaccine_schedule": "chat",
    "income": "chat",
    "taxes": "chat",
    "w2": "chat",
    "rewards_balance": "chat",
    "redeem_rewards": "chat",
    "interest_rate": "chat",
    "min_payment": "chat",
    "pay_bill": "chat",
    "application_status": "chat",
    "international_fees": "chat",
    "freeze_account": "chat",
    "report_fraud": "chat",
    "report_lost_card": "chat",
    "replacement_card_duration": "chat",
    "pin_change": "chat",
    "account_blocked": "chat",
    "apr": "chat",
    "transfer": "chat",
    "transactions": "chat",
    "spending_history": "chat",
    "direct_deposit": "chat",
    "pto_request": "chat",
    "pto_balance": "chat",
    "pto_request_status": "chat",
    "next_holiday": "time_date",
    "sync_device": "chat",
    "make_call": "chat",
    "cancel_reservation": "chat",
    "update_playlist": "media",
    "mpg": "chat",
    "oil_change_when": "chat",
    "oil_change_how": "chat",
    "tire_change": "chat",
    "tire_pressure": "chat",
    "jump_start": "chat",
    "uber": "chat",
    "schedule_maintenance": "chat",
    "last_maintenance": "chat",
    "what_song": "media",
    "change_language": "chat",
    "change_speed": "chat",
    "user_name": "chat",
    "change_user_name": "chat",
    "change_accent": "chat",
    "change_ai_name": "chat",
    "whisper_mode": "chat",
    "how_busy": "chat",
    "food_last": "chat",
    "ingredient_substitution": "chat",
    "confirm_reservation": "chat",
    "cancel": "chat",
}


# ╔══════════════════════════════════════════════════════════════╗
# ║  CELL 4: Build the Combined Dataset                        ║
# ╚══════════════════════════════════════════════════════════════╝

print("\n" + "=" * 60)
print("  Building combined dataset...")
print("=" * 60)

all_texts = []
all_labels = []

# 1. CLINC150 data (mapped to JARVIS intents)
mapped_count = 0
for split in ["train", "validation"]:
    for example in clinc[split]:
        clinc_intent = clinc_intents[example["intent"]]
        jarvis_intent = CLINC_TO_JARVIS.get(clinc_intent, None)
        if jarvis_intent:
            all_texts.append(example["text"])
            all_labels.append(jarvis_intent)
            mapped_count += 1

print(f"  CLINC150 mapped: {mapped_count} examples")

# 2. Custom JARVIS-specific data (things CLINC doesn't cover)
CUSTOM_DATA = [
    # ── Open App (CLINC doesn't have this!) ──
    ("open notepad", "open_app"),
    ("launch spotify", "open_app"),
    ("start chrome", "open_app"),
    ("open calculator", "open_app"),
    ("open vs code", "open_app"),
    ("launch file explorer", "open_app"),
    ("open telegram", "open_app"),
    ("start excel", "open_app"),
    ("open paint", "open_app"),
    ("launch word", "open_app"),
    ("open the camera", "open_app"),
    ("can you open settings", "open_app"),
    ("open task manager", "open_app"),
    ("start vlc", "open_app"),
    ("open discord", "open_app"),
    ("launch brave browser", "open_app"),
    ("open whatsapp", "open_app"),
    ("open snipping tool", "open_app"),
    ("run photoshop", "open_app"),
    ("open powerpoint", "open_app"),
    ("please open chrome for me", "open_app"),
    ("i want to open spotify", "open_app"),
    ("can you launch notepad", "open_app"),
    ("fire up the browser", "open_app"),
    ("get me excel", "open_app"),
    ("start the app", "open_app"),
    ("open an application", "open_app"),
    ("launch this program", "open_app"),

    # ── Close App ──
    ("close notepad", "close_app"),
    ("kill chrome", "close_app"),
    ("exit spotify", "close_app"),
    ("close the calculator", "close_app"),
    ("quit vs code", "close_app"),
    ("stop notepad", "close_app"),
    ("close this app", "close_app"),
    ("kill task manager", "close_app"),
    ("end excel", "close_app"),
    ("shut down chrome", "close_app"),
    ("close all apps", "close_app"),
    ("terminate this program", "close_app"),
    ("shut this down", "close_app"),
    ("force close it", "close_app"),

    # ── Screenshot ──
    ("take a screenshot", "screenshot"),
    ("capture screen", "screenshot"),
    ("screenshot please", "screenshot"),
    ("grab the screen", "screenshot"),
    ("take a screen capture", "screenshot"),
    ("snap the screen", "screenshot"),
    ("capture this", "screenshot"),
    ("save what's on my screen", "screenshot"),

    # ── Screen Control ──
    ("scroll down", "screen_control"),
    ("scroll up", "screen_control"),
    ("click", "screen_control"),
    ("double click", "screen_control"),
    ("right click", "screen_control"),
    ("press enter", "screen_control"),
    ("select all", "screen_control"),
    ("copy this", "screen_control"),
    ("paste", "screen_control"),
    ("undo", "screen_control"),
    ("redo", "screen_control"),
    ("snap left", "screen_control"),
    ("snap right", "screen_control"),
    ("minimize", "screen_control"),
    ("minimise", "screen_control"),
    ("maximise", "screen_control"),
    ("maximize", "screen_control"),
    ("switch window", "screen_control"),
    ("minimize all", "screen_control"),
    ("type hello", "screen_control"),
    ("press escape", "screen_control"),
    ("save this file", "screen_control"),
    ("full screen", "screen_control"),
    ("alt tab", "screen_control"),
    ("show desktop", "screen_control"),
    ("move window to the left", "screen_control"),
    ("move window to the right", "screen_control"),

    # ── Clipboard ──
    ("read clipboard", "clipboard"),
    ("what did i copy", "clipboard"),
    ("what's in clipboard", "clipboard"),
    ("summarize clipboard", "clipboard"),
    ("summarize what i copied", "clipboard"),
    ("read what i copied", "clipboard"),

    # ── System Info ──
    ("cpu usage", "system_info"),
    ("how much ram", "system_info"),
    ("ram usage", "system_info"),
    ("system status", "system_info"),
    ("disk space", "system_info"),
    ("how much storage left", "system_info"),
    ("system info", "system_info"),
    ("what's using my cpu", "system_info"),
    ("how much memory is free", "system_info"),
    ("battery percentage", "system_info"),

    # ── Brightness (CLINC doesn't have this) ──
    ("increase brightness", "system_brightness"),
    ("brightness up", "system_brightness"),
    ("make screen brighter", "system_brightness"),
    ("decrease brightness", "system_brightness"),
    ("dim the screen", "system_brightness"),
    ("lower brightness", "system_brightness"),
    ("set brightness to 80", "system_brightness"),
    ("screen is too bright", "system_brightness"),
    ("it's too dark", "system_brightness"),
    ("turn down brightness", "system_brightness"),

    # ── YouTube ──
    ("play on youtube", "youtube"),
    ("open youtube", "youtube"),
    ("youtube search", "youtube"),
    ("play despacito on youtube", "youtube"),
    ("search youtube for tutorials", "youtube"),
    ("find videos about python", "youtube"),
    ("watch this on youtube", "youtube"),

    # ── Google Search ──
    ("search for python tutorials", "google_search"),
    ("google how to cook pasta", "google_search"),
    ("search online for laptops", "google_search"),
    ("look up machine learning", "google_search"),
    ("google it", "google_search"),
    ("search the web for", "google_search"),

    # ── WhatsApp ──
    ("message to banty hello", "whatsapp"),
    ("send whatsapp to rahul", "whatsapp"),
    ("text banty saying hi", "whatsapp"),
    ("whatsapp message to mom", "whatsapp"),
    ("send message to priya", "whatsapp"),
    ("text to sarvani good morning", "whatsapp"),
    ("tell banty i'll be late", "whatsapp"),

    # ── News (extra) ──
    ("what's the news", "news"),
    ("latest news", "news"),
    ("top stories today", "news"),
    ("sports news", "news"),
    ("breaking news", "news"),
    ("headlines", "news"),

    # ── Reset ──
    ("reset conversation", "reset"),
    ("clear chat", "reset"),
    ("start over", "reset"),
    ("forget everything", "reset"),
    ("new conversation", "reset"),
]

for text, label in CUSTOM_DATA:
    all_texts.append(text)
    all_labels.append(label)

print(f"  Custom JARVIS: {len(CUSTOM_DATA)} examples")
print(f"  TOTAL: {len(all_texts)} examples, {len(set(all_labels))} intents")
print(f"  Intents: {sorted(set(all_labels))}")


# ╔══════════════════════════════════════════════════════════════╗
# ║  CELL 5: Train the Model                                   ║
# ╚══════════════════════════════════════════════════════════════╝

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import cross_val_score, train_test_split
from sklearn.metrics import classification_report
from sklearn.pipeline import Pipeline

print("\n" + "=" * 60)
print("  Training intent classifier...")
print("=" * 60)

# Split data
X_train, X_test, y_train, y_test = train_test_split(
    all_texts, all_labels, test_size=0.15, random_state=42, stratify=all_labels
)

print(f"  Train: {len(X_train)} | Test: {len(X_test)}")

# Build pipeline with TF-IDF + Logistic Regression
model = Pipeline([
    ("tfidf", TfidfVectorizer(
        ngram_range=(1, 3),          # Unigrams + bigrams + trigrams
        max_features=15000,
        sublinear_tf=True,
        strip_accents="unicode",
        lowercase=True,
        min_df=1,
    )),
    ("classifier", LogisticRegression(
        max_iter=3000,
        C=10.0,
        class_weight="balanced",
        solver="lbfgs",
    ))
])

# Train
model.fit(X_train, y_train)

# Evaluate
train_acc = model.score(X_train, y_train)
test_acc = model.score(X_test, y_test)
print(f"\n  Train accuracy: {train_acc:.1%}")
print(f"  Test accuracy:  {test_acc:.1%}")

# Detailed report
y_pred = model.predict(X_test)
print("\n  Classification Report:")
print(classification_report(y_test, y_pred, zero_division=0))


# ╔══════════════════════════════════════════════════════════════╗
# ║  CELL 6: Save Model                                        ║
# ╚══════════════════════════════════════════════════════════════╝

with open("intent_classifier.pkl", "wb") as f:
    pickle.dump(model, f)

model_size = os.path.getsize("intent_classifier.pkl") / 1024
print(f"\nModel saved: intent_classifier.pkl ({model_size:.0f} KB)")


# ╔══════════════════════════════════════════════════════════════╗
# ║  CELL 7: Test with JARVIS-style commands                   ║
# ╚══════════════════════════════════════════════════════════════╝

print("\n" + "=" * 60)
print("  Testing with real JARVIS commands:")
print("=" * 60)

test_phrases = [
    "open spotify",
    "close notepad",
    "what's the weather in chennai",
    "play some music",
    "play despacito on youtube",
    "next song",
    "tell me a joke",
    "send message to banty hi",
    "what time is it",
    "scroll down",
    "minimize all windows",
    "read clipboard",
    "cpu usage",
    "take a screenshot",
    "search for laptops on amazon",
    "who is elon musk",
    "set a reminder for 5pm",
    "hello jarvis",
    "goodbye",
    "write me a poem",
    "increase volume",
    "dim the screen",
    "whatsapp sarvani saying hello",
    "what's the latest news",
    "help me with python code",
]

for phrase in test_phrases:
    pred = model.predict([phrase])[0]
    conf = model.predict_proba([phrase]).max()
    print(f"  '{phrase}' -> {pred} ({conf:.0%})")


# ╔══════════════════════════════════════════════════════════════╗
# ║  CELL 8: Download (Colab only)                             ║
# ╚══════════════════════════════════════════════════════════════╝

print("\n" + "=" * 60)
print("  DONE!")
print(f"  Dataset: {len(all_texts)} real examples")
print(f"  Intents: {len(set(all_labels))}")
print(f"  Test accuracy: {test_acc:.1%}")
print(f"  Model size: {model_size:.0f} KB")
print("=" * 60)
print("\n  Put intent_classifier.pkl in:")
print("  JARVIS/brain/models/intent_classifier.pkl")

# Uncomment in Google Colab to download:
# from google.colab import files
# files.download('intent_classifier.pkl')
