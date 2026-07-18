"""
Clean training_data.py (remove duplicates) and retrain the ML model.
Run: python scripts/clean_and_retrain.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain.training_data import TRAINING_DATA
from collections import Counter, OrderedDict

# ── Step 1: Deduplicate (preserving first occurrence order) ──
seen = OrderedDict()
for item in TRAINING_DATA:
    if not isinstance(item, tuple) or len(item) != 2:
        print(f"  ⚠️  Skipping malformed entry: {item!r}")
        continue
    text, label = item
    key = (text.strip().lower(), label)
    if key not in seen:
        seen[key] = (text, label)

unique_data = list(seen.values())

before = len(TRAINING_DATA)
after = len(unique_data)
removed = before - after
print(f"✅ Deduplication complete")
print(f"   Before: {before} entries")
print(f"   After:  {after} unique entries")
print(f"   Removed: {removed} duplicates")

# ── Step 2: Show intent distribution ──
intents = Counter(label for _, label in unique_data)
print(f"\n📊 Intent distribution ({len(intents)} intents):")
for intent, count in sorted(intents.items(), key=lambda x: -x[1]):
    bar = "█" * min(count, 50)
    print(f"   {count:4d}  {intent:<25}  {bar}")

# ── Step 3: Write cleaned training_data.py ──
print(f"\n📝 Writing cleaned training_data.py...")

# Group by intent for readability
from collections import defaultdict
by_intent = defaultdict(list)
for text, label in unique_data:
    by_intent[label].append(text)

lines = ['"""\n']
lines.append('JARVIS Training Data — auto-cleaned, duplicates removed.\n')
lines.append('DO NOT manually add duplicates — the ML model needs diversity, not repetition.\n')
lines.append('"""\n\n')
lines.append('TRAINING_DATA = [\n')

for intent in sorted(by_intent.keys()):
    examples = by_intent[intent]
    lines.append(f'\n    # ── {intent} ({len(examples)} examples) ──\n')
    for text in examples:
        # Escape single quotes
        escaped = text.replace("'", "\\'")
        lines.append(f"    ('{escaped}', '{intent}'),\n")

lines.append(']\n')

out_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        'brain', 'training_data.py')
with open(out_path, 'w', encoding='utf-8') as f:
    f.writelines(lines)
print(f"   Saved to: {out_path}")

# ── Step 4: Retrain the model ──
print(f"\n🤖 Retraining ML model...")
try:
    from brain.auto_trainer import AutoTrainer
    trainer = AutoTrainer()
    result = trainer.train()
    if result:
        print(f"✅ Model retrained successfully!")
    else:
        print(f"⚠️  Trainer returned False — check auto_trainer.py")
except Exception as e:
    print(f"❌ Trainer error: {e}")
    import traceback
    traceback.print_exc()
    print("\nTrying direct training...")
    try:
        from ml.intent_classifier import train_model
        train_model()
        print("✅ Direct training complete!")
    except Exception as e2:
        print(f"❌ Direct training also failed: {e2}")

print("\n🎉 Done! Restart JARVIS for the new model to take effect.")
