"""
JARVIS — ml/train_intent_model.py
Fine-tunes DistilBERT on JARVIS commands for offline intent classification.

This creates a small, fast model (~66M params) that runs on CPU in <50ms
and classifies user commands into 39 skill categories WITHOUT needing
any API calls. Your RTX 4050 will train this in ~3-5 minutes.

Usage:
    1. First run: python ml/generate_training_data.py
    2. Then run:  python ml/train_intent_model.py
    3. Model saved to: ml/jarvis_intent_model/
"""

import json
import os
import sys
import warnings

warnings.filterwarnings("ignore")

import numpy as np
import torch
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score
from transformers import (
    DistilBertTokenizer,
    DistilBertForSequenceClassification,
    Trainer,
    TrainingArguments,
    EarlyStoppingCallback,
)
from torch.utils.data import Dataset

# Paths
ML_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(ML_DIR, "training_data.json")
MODEL_DIR = os.path.join(ML_DIR, "jarvis_intent_model")
LABEL_MAP_PATH = os.path.join(MODEL_DIR, "label_map.json")


class IntentDataset(Dataset):
    """PyTorch dataset for intent classification."""

    def __init__(self, texts, labels, tokenizer, max_length=64):
        self.encodings = tokenizer(
            texts,
            truncation=True,
            padding="max_length",
            max_length=max_length,
            return_tensors="pt",
        )
        self.labels = torch.tensor(labels, dtype=torch.long)

    def __len__(self):
        return len(self.labels)

    def __getitem__(self, idx):
        item = {key: val[idx] for key, val in self.encodings.items()}
        item["labels"] = self.labels[idx]
        return item


def compute_metrics(eval_pred):
    """Compute accuracy for evaluation."""
    logits, labels = eval_pred
    preds = np.argmax(logits, axis=-1)
    acc = accuracy_score(labels, preds)
    return {"accuracy": acc}


def main():
    print("=" * 60)
    print("  JARVIS Intent Classifier — Training")
    print("=" * 60)

    # ── 1. Check GPU ─────────────────────────────────────────
    device = "cuda" if torch.cuda.is_available() else "cpu"
    if device == "cuda":
        gpu_name = torch.cuda.get_device_name(0)
        gpu_mem = torch.cuda.get_device_properties(0).total_memory / 1e9
        print(f"\n  GPU: {gpu_name} ({gpu_mem:.1f} GB)")
    else:
        print("\n  Running on CPU (will be slower)")

    # ── 2. Load data ─────────────────────────────────────────
    if not os.path.exists(DATA_PATH):
        print(f"\n  ERROR: No training data found at {DATA_PATH}")
        print("  Run 'python ml/generate_training_data.py' first!")
        return

    with open(DATA_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    print(f"\n  Training examples: {len(data)}")

    # ── 3. Create label mapping ──────────────────────────────
    labels = sorted(set(item["label"] for item in data))
    label2id = {label: i for i, label in enumerate(labels)}
    id2label = {i: label for label, i in label2id.items()}
    num_labels = len(labels)

    print(f"  Intent categories: {num_labels}")

    # ── 4. Prepare data ──────────────────────────────────────
    texts = [item["text"] for item in data]
    encoded_labels = [label2id[item["label"]] for item in data]

    # 80/20 split
    train_texts, val_texts, train_labels, val_labels = train_test_split(
        texts, encoded_labels, test_size=0.2, random_state=42, stratify=encoded_labels
    )

    print(f"  Train: {len(train_texts)}, Validation: {len(val_texts)}")

    # ── 5. Load tokenizer + model ────────────────────────────
    print("\n  Loading DistilBERT model...")
    model_name = "distilbert-base-uncased"

    tokenizer = DistilBertTokenizer.from_pretrained(model_name)
    model = DistilBertForSequenceClassification.from_pretrained(
        model_name,
        num_labels=num_labels,
        id2label=id2label,
        label2id=label2id,
    )

    print(f"  Model parameters: {sum(p.numel() for p in model.parameters()):,}")

    # ── 6. Create datasets ───────────────────────────────────
    train_dataset = IntentDataset(train_texts, train_labels, tokenizer)
    val_dataset = IntentDataset(val_texts, val_labels, tokenizer)

    # ── 7. Training config ───────────────────────────────────
    training_args = TrainingArguments(
        output_dir=os.path.join(ML_DIR, "training_output"),
        num_train_epochs=8,
        per_device_train_batch_size=32,
        per_device_eval_batch_size=64,
        learning_rate=3e-5,
        weight_decay=0.01,
        warmup_steps=100,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="accuracy",
        greater_is_better=True,
        logging_dir=os.path.join(ML_DIR, "logs"),
        logging_steps=50,
        save_total_limit=2,
        fp16=torch.cuda.is_available(),  # Mixed precision on GPU
        report_to="none",  # Don't send to wandb/etc
        dataloader_num_workers=0,  # Windows compatibility
    )

    # ── 8. Train! ────────────────────────────────────────────
    print("\n  Starting training...")
    print("  " + "-" * 50)

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
        compute_metrics=compute_metrics,
        callbacks=[EarlyStoppingCallback(early_stopping_patience=3)],
    )

    trainer.train()

    # ── 9. Evaluate ──────────────────────────────────────────
    print("\n  " + "=" * 50)
    print("  Final Evaluation")
    print("  " + "=" * 50)

    results = trainer.evaluate()
    print(f"\n  Accuracy: {results['eval_accuracy']:.1%}")

    # Detailed report
    preds = trainer.predict(val_dataset)
    pred_labels = np.argmax(preds.predictions, axis=-1)
    true_labels = val_labels

    report = classification_report(
        true_labels, pred_labels,
        target_names=labels,
        zero_division=0,
    )
    print("\n" + report)

    # ── 10. Save model ───────────────────────────────────────
    print(f"\n  Saving model to: {MODEL_DIR}")
    os.makedirs(MODEL_DIR, exist_ok=True)

    trainer.save_model(MODEL_DIR)
    tokenizer.save_pretrained(MODEL_DIR)

    # Save label mapping
    with open(LABEL_MAP_PATH, "w") as f:
        json.dump({"label2id": label2id, "id2label": id2label}, f, indent=2)

    # ── 11. Quick inference test ─────────────────────────────
    print("\n  " + "=" * 50)
    print("  Quick Test — Let's see if it works!")
    print("  " + "=" * 50)

    test_commands = [
        "open chrome",
        "can you please launch firefox for me",
        "what's the weather like",
        "send hi to sarvani on whatsapp",
        "play believer by imagine dragons",
        "set volume to 50",
        "take a screenshot",
        "what time is it right now",
        "tell me a joke",
        "remind me to call mom at 5pm",
        "hey jarvis close notepad",
        "i need to search for laptops",
    ]

    model.eval()
    model.to(device)

    print()
    for cmd in test_commands:
        inputs = tokenizer(cmd, return_tensors="pt", truncation=True, max_length=64).to(device)
        with torch.no_grad():
            outputs = model(**inputs)
            probs = torch.softmax(outputs.logits, dim=-1)
            pred_id = torch.argmax(probs, dim=-1).item()
            confidence = probs[0][pred_id].item()

        intent = id2label[pred_id]
        bar = "#" * int(confidence * 20)
        print(f"  [{confidence:.0%}] {bar:20s} | {intent:20s} | \"{cmd}\"")

    # ── 12. Model size ───────────────────────────────────────
    model_size = sum(
        os.path.getsize(os.path.join(MODEL_DIR, f))
        for f in os.listdir(MODEL_DIR)
        if os.path.isfile(os.path.join(MODEL_DIR, f))
    )
    print(f"\n  Model size: {model_size / 1e6:.1f} MB")
    print(f"  Location: {MODEL_DIR}")
    print("\n  DONE! Your JARVIS now has an offline brain.")
    print("  Next: The model will auto-load when JARVIS starts.")


if __name__ == "__main__":
    main()
