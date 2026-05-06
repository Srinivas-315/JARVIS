"""
JARVIS — brain/train_model.py
Train the intent classifier and save it.
Uses TF-IDF + Logistic Regression — fast, accurate, fully offline.

Run: python brain/train_model.py
"""

import os
import pickle
import numpy as np
from pathlib import Path
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import cross_val_score
from sklearn.pipeline import Pipeline

# Import training data
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from brain.training_data import TRAINING_DATA


def train():
    """Train the intent classifier and save to disk."""
    # Split data
    texts = [t[0] for t in TRAINING_DATA]
    labels = [t[1] for t in TRAINING_DATA]

    print(f"📊 Training data: {len(texts)} examples, {len(set(labels))} intents")
    print(f"   Intents: {sorted(set(labels))}")

    # Build pipeline: TF-IDF + Logistic Regression
    model = Pipeline([
        ("tfidf", TfidfVectorizer(
            ngram_range=(1, 2),      # Unigrams + bigrams
            max_features=5000,
            sublinear_tf=True,       # Logarithmic TF scaling
            strip_accents="unicode",
            lowercase=True,
        )),
        ("classifier", LogisticRegression(
            max_iter=1000,
            C=10.0,                  # Regularization
            class_weight="balanced", # Handle imbalanced classes
            multi_class="multinomial",
            solver="lbfgs",
        ))
    ])

    # Train
    print("\n🏋️ Training model...")
    model.fit(texts, labels)

    # Evaluate with 5-fold cross-validation
    scores = cross_val_score(model, texts, labels, cv=5, scoring="accuracy")
    print(f"\n📈 Cross-validation accuracy: {scores.mean():.1%} (±{scores.std():.1%})")
    print(f"   Per fold: {[f'{s:.1%}' for s in scores]}")

    # Save model
    model_dir = Path(__file__).parent / "models"
    model_dir.mkdir(exist_ok=True)
    model_path = model_dir / "intent_classifier.pkl"

    with open(model_path, "wb") as f:
        pickle.dump(model, f)

    file_size = os.path.getsize(model_path) / 1024
    print(f"\n💾 Model saved: {model_path} ({file_size:.0f} KB)")

    # Test predictions
    print("\n🧪 Test predictions:")
    test_phrases = [
        "open spotify",
        "what's the weather like",
        "play despacito",
        "close notepad",
        "send message to banty hi",
        "what time is it",
        "search for laptops on amazon",
        "tell me a joke",
        "next song please",
        "remind me to call mom",
        "who is narendra modi",
        "my name is srini",
        "goodbye jarvis",
        "take a screenshot",
        "hello",
    ]

    for phrase in test_phrases:
        prediction = model.predict([phrase])[0]
        confidence = model.predict_proba([phrase]).max()
        print(f"   '{phrase}' → {prediction} ({confidence:.0%})")

    print(f"\n✅ Model trained successfully! {len(set(labels))} intents ready.")
    return model


if __name__ == "__main__":
    train()
