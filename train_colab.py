# JARVIS Intent Classifier — Google Colab Training Notebook
# Run this in Google Colab: https://colab.research.google.com
#
# STEP 1: Upload your training_data.py to Colab
# STEP 2: Run all cells top to bottom
# STEP 3: Download the trained model files
# STEP 4: Replace JARVIS/brain/models/ with downloaded files

# ─────────────────────────────────────────────────────────────
# CELL 1 — Install dependencies
# ─────────────────────────────────────────────────────────────
# !pip install scikit-learn numpy

# ─────────────────────────────────────────────────────────────
# CELL 2 — Imports
# ─────────────────────────────────────────────────────────────
import os, sys, json, pickle
import numpy as np
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier, VotingClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.model_selection import cross_val_score, train_test_split
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.preprocessing import LabelEncoder

print("✅ All imports done!")

# ─────────────────────────────────────────────────────────────
# CELL 3 — Paste OR upload training_data.py
# If running in Colab: upload training_data.py first, then run this
# ─────────────────────────────────────────────────────────────

# Option A: If you uploaded training_data.py to Colab
# from training_data import TRAINING_DATA

# Option B: Paste the TRAINING_DATA list directly here
# (copy from brain/training_data.py)

# For now — load from file if exists, else use inline sample
try:
    sys.path.insert(0, "/content")
    from training_data import TRAINING_DATA
    print(f"✅ Loaded from file: {len(TRAINING_DATA)} examples")
except ImportError:
    print("⚠️  Upload training_data.py to Colab, then re-run this cell")
    TRAINING_DATA = []

# ─────────────────────────────────────────────────────────────
# CELL 4 — Prepare data
# ─────────────────────────────────────────────────────────────
if not TRAINING_DATA:
    raise ValueError("❌ TRAINING_DATA is empty! Upload training_data.py first.")

texts  = [t.lower().strip() for t, _ in TRAINING_DATA]
labels = [l for _, l in TRAINING_DATA]

# Stats
from collections import Counter
intent_counts = Counter(labels)
print(f"\n📊 Dataset Stats:")
print(f"   Total examples : {len(texts)}")
print(f"   Unique intents : {len(intent_counts)}")
print(f"\n   Examples per intent:")
for intent, count in sorted(intent_counts.items()):
    bar = "█" * count
    print(f"   {intent:<20} {count:3d}  {bar}")

# ─────────────────────────────────────────────────────────────
# CELL 5 — Train/test split
# ─────────────────────────────────────────────────────────────
X_train, X_test, y_train, y_test = train_test_split(
    texts, labels, test_size=0.15, random_state=42, stratify=labels
)
print(f"Train: {len(X_train)} | Test: {len(X_test)}")

# ─────────────────────────────────────────────────────────────
# CELL 6 — Build & train models
# ─────────────────────────────────────────────────────────────

# Model 1: LinearSVC (fast, excellent for text)
svm_pipeline = Pipeline([
    ("tfidf", TfidfVectorizer(
        ngram_range=(1, 3),       # 1-word, 2-word, 3-word combos
        min_df=1,
        sublinear_tf=True,
        analyzer="word",
        strip_accents="unicode"
    )),
    ("clf", LinearSVC(
        C=1.5,
        max_iter=2000,
        class_weight="balanced"   # Handles rare intents better
    ))
])

# Model 2: Logistic Regression
lr_pipeline = Pipeline([
    ("tfidf", TfidfVectorizer(
        ngram_range=(1, 3),
        min_df=1,
        sublinear_tf=True
    )),
    ("clf", LogisticRegression(
        C=5.0,
        max_iter=1000,
        solver="lbfgs",
        multi_class="multinomial"
    ))
])

# Train both
print("⏳ Training LinearSVC...")
svm_pipeline.fit(X_train, y_train)
svm_acc = svm_pipeline.score(X_test, y_test)
print(f"   LinearSVC accuracy: {svm_acc:.1%}")

print("⏳ Training Logistic Regression...")
lr_pipeline.fit(X_train, y_train)
lr_acc = lr_pipeline.score(X_test, y_test)
print(f"   Logistic Regression accuracy: {lr_acc:.1%}")

# Pick the better one
best_model = svm_pipeline if svm_acc >= lr_acc else lr_pipeline
best_name  = "LinearSVC" if svm_acc >= lr_acc else "LogisticRegression"
print(f"\n🏆 Best model: {best_name} ({max(svm_acc, lr_acc):.1%})")

# ─────────────────────────────────────────────────────────────
# CELL 7 — Cross-validation (5-fold)
# ─────────────────────────────────────────────────────────────
print("⏳ Running 5-fold cross-validation...")
cv_scores = cross_val_score(best_model, texts, labels, cv=5, scoring="accuracy")
print(f"\n📊 Cross-validation results:")
print(f"   Fold scores: {[f'{s:.1%}' for s in cv_scores]}")
print(f"   Mean: {cv_scores.mean():.1%}  ±{cv_scores.std():.1%}")

# ─────────────────────────────────────────────────────────────
# CELL 8 — Detailed classification report
# ─────────────────────────────────────────────────────────────
y_pred = best_model.predict(X_test)
print("\n📋 Classification Report:")
print(classification_report(y_test, y_pred))

# Show mistakes
print("❌ Mistakes (test set):")
mistake_count = 0
for txt, true, pred in zip(X_test, y_test, y_pred):
    if true != pred:
        print(f"   '{txt}'")
        print(f"   True: {true} | Predicted: {pred}")
        mistake_count += 1
if mistake_count == 0:
    print("   None! Perfect test set accuracy 🎉")

# ─────────────────────────────────────────────────────────────
# CELL 9 — Interactive test
# ─────────────────────────────────────────────────────────────
def test_model(queries):
    print("\n🧪 Model predictions:")
    print("-" * 50)
    for q in queries:
        pred = best_model.predict([q.lower()])[0]
        # Get confidence if LR (has predict_proba)
        if hasattr(best_model.named_steps["clf"], "predict_proba"):
            proba = best_model.predict_proba([q.lower()]).max()
            conf = f" ({proba:.0%} confident)"
        else:
            conf = ""
        print(f"  '{q}'")
        print(f"  → {pred}{conf}\n")

# Test with your own phrases!
test_model([
    "open youtube",
    "what time is it",
    "add meeting tomorrow at 3pm",
    "bitcoin price",
    "create hello.py",
    "change voice to george",
    "remind me to drink water",
    "what's on my screen",
    "my name is srini",
    "play some music",
])

# ─────────────────────────────────────────────────────────────
# CELL 10 — Save model + metadata
# ─────────────────────────────────────────────────────────────
os.makedirs("/content/jarvis_model", exist_ok=True)

# Save model
model_path = "/content/jarvis_model/intent_classifier.pkl"
with open(model_path, "wb") as f:
    pickle.dump(best_model, f)
print(f"✅ Model saved: {model_path}")

# Save metadata (so JARVIS knows what intents exist)
metadata = {
    "model_type":    best_name,
    "accuracy":      round(max(svm_acc, lr_acc), 4),
    "cv_mean":       round(cv_scores.mean(), 4),
    "intents":       sorted(list(set(labels))),
    "num_examples":  len(TRAINING_DATA),
    "sklearn_version": __import__("sklearn").__version__,
    "trained_date":  __import__("datetime").datetime.now().isoformat(),
}
meta_path = "/content/jarvis_model/model_metadata.json"
with open(meta_path, "w") as f:
    json.dump(metadata, f, indent=2)
print(f"✅ Metadata saved: {meta_path}")
print(f"\n📊 Summary:")
print(f"   Model:     {best_name}")
print(f"   Accuracy:  {max(svm_acc, lr_acc):.1%}")
print(f"   CV Mean:   {cv_scores.mean():.1%}")
print(f"   Intents:   {len(set(labels))}")
print(f"   Examples:  {len(TRAINING_DATA)}")

# ─────────────────────────────────────────────────────────────
# CELL 11 — Download files to your PC
# ─────────────────────────────────────────────────────────────
from google.colab import files

print("📥 Downloading model files...")
files.download("/content/jarvis_model/intent_classifier.pkl")
files.download("/content/jarvis_model/model_metadata.json")
print("\n✅ DONE!")
print("\n📋 NEXT STEPS:")
print("1. Move intent_classifier.pkl to:  JARVIS/brain/models/")
print("2. Move model_metadata.json to:   JARVIS/brain/models/")
print("3. Restart JARVIS — it auto-loads the new model!")
print("\nJARVIS will now understand all new intents! 🚀")
