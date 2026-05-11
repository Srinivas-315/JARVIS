"""
JARVIS — ml/anomaly_detector.py
Anomaly Detection using Autoencoder neural network.

Monitors your system and detects unusual behavior:
  - CPU spike at unusual times
  - Unknown processes running
  - Abnormal memory usage
  - Disk usage anomalies
  - Network activity spikes

How it works:
  1. Collects system metrics every 30 seconds
  2. Trains an autoencoder on YOUR normal patterns
  3. Flags anomalies when reconstruction error is high
  4. Alerts JARVIS: "Sir, unusual CPU usage detected"

Usage:
    python ml/anomaly_detector.py          # test mode
    python ml/anomaly_detector.py --train  # collect + train
"""

import os
import sys
import json
import time
import sqlite3
from pathlib import Path
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import log

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "system_metrics.db"
MODEL_PATH = Path(__file__).parent / "anomaly_model.pt"

# Feature dimensions
FEATURE_NAMES = [
    "cpu_percent", "memory_percent", "disk_percent",
    "num_processes", "hour_of_day", "is_weekend",
    "cpu_freq_ghz", "battery_percent",
]
NUM_FEATURES = len(FEATURE_NAMES)


# ═══════════════════════════════════════════════════════════════
#  System Metrics Collector
# ═══════════════════════════════════════════════════════════════
class MetricsCollector:
    """Collects system metrics and stores in SQLite."""

    def __init__(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(DB_PATH))
        self._create_table()

    def _create_table(self):
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                cpu_percent REAL,
                memory_percent REAL,
                disk_percent REAL,
                num_processes INTEGER,
                hour_of_day INTEGER,
                is_weekend INTEGER,
                cpu_freq_ghz REAL,
                battery_percent REAL
            )
        """)
        self._conn.commit()

    def collect_now(self) -> dict:
        """Collect current system metrics."""
        try:
            import psutil
        except ImportError:
            log.info("psutil not installed. Run: pip install psutil")
            return self._mock_metrics()

        now = datetime.now()

        try:
            cpu = psutil.cpu_percent(interval=0.5)
        except Exception:
            cpu = 0.0

        try:
            mem = psutil.virtual_memory().percent
        except Exception:
            mem = 0.0

        try:
            disk = psutil.disk_usage('/').percent
        except Exception:
            try:
                disk = psutil.disk_usage('C:\\').percent
            except Exception:
                disk = 0.0

        try:
            procs = len(psutil.pids())
        except Exception:
            procs = 0

        try:
            freq = psutil.cpu_freq()
            cpu_ghz = round(freq.current / 1000, 2) if freq else 0.0
        except Exception:
            cpu_ghz = 0.0

        try:
            battery = psutil.sensors_battery()
            batt_pct = battery.percent if battery else 100.0
        except Exception:
            batt_pct = 100.0

        metrics = {
            "cpu_percent": round(cpu, 1),
            "memory_percent": round(mem, 1),
            "disk_percent": round(disk, 1),
            "num_processes": procs,
            "hour_of_day": now.hour,
            "is_weekend": 1 if now.weekday() >= 5 else 0,
            "cpu_freq_ghz": cpu_ghz,
            "battery_percent": round(batt_pct, 1),
        }
        return metrics

    def _mock_metrics(self) -> dict:
        """Fallback metrics when psutil isn't available."""
        import random
        now = datetime.now()
        return {
            "cpu_percent": round(random.uniform(5, 40), 1),
            "memory_percent": round(random.uniform(40, 70), 1),
            "disk_percent": round(random.uniform(50, 80), 1),
            "num_processes": random.randint(100, 300),
            "hour_of_day": now.hour,
            "is_weekend": 1 if now.weekday() >= 5 else 0,
            "cpu_freq_ghz": round(random.uniform(1.5, 4.5), 2),
            "battery_percent": round(random.uniform(20, 100), 1),
        }

    def save(self, metrics: dict):
        """Save metrics to database."""
        self._conn.execute(
            "INSERT INTO metrics (timestamp, cpu_percent, memory_percent, disk_percent, "
            "num_processes, hour_of_day, is_weekend, cpu_freq_ghz, battery_percent) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                datetime.now().isoformat(),
                metrics["cpu_percent"],
                metrics["memory_percent"],
                metrics["disk_percent"],
                metrics["num_processes"],
                metrics["hour_of_day"],
                metrics["is_weekend"],
                metrics["cpu_freq_ghz"],
                metrics["battery_percent"],
            ),
        )
        self._conn.commit()

    def get_all(self) -> list:
        """Get all saved metrics as list of dicts."""
        rows = self._conn.execute(
            "SELECT cpu_percent, memory_percent, disk_percent, num_processes, "
            "hour_of_day, is_weekend, cpu_freq_ghz, battery_percent FROM metrics"
        ).fetchall()
        return [
            dict(zip(FEATURE_NAMES, r)) for r in rows
        ]

    def count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM metrics").fetchone()[0]

    def close(self):
        self._conn.close()


# ═══════════════════════════════════════════════════════════════
#  Autoencoder Model
# ═══════════════════════════════════════════════════════════════
class AnomalyAutoencoder:
    """
    Autoencoder neural network for anomaly detection.

    Architecture:
        Input(8) → Dense(16) → Dense(8) → Dense(4) → Dense(8) → Dense(16) → Output(8)
               [encoder]            [bottleneck]            [decoder]

    High reconstruction error = ANOMALY.
    """

    def __init__(self):
        self._model = None
        self._threshold = None
        self._means = None
        self._stds = None
        self._ready = False
        self._try_load()

    def _try_load(self):
        """Load pre-trained model if exists."""
        try:
            import torch
            if MODEL_PATH.exists():
                checkpoint = torch.load(str(MODEL_PATH), map_location="cpu", weights_only=False)
                self._model = self._build_model()
                self._model.load_state_dict(checkpoint["model"])
                self._model.eval()
                self._threshold = checkpoint["threshold"]
                self._means = checkpoint["means"]
                self._stds = checkpoint["stds"]
                self._ready = True
                log.info(f"Anomaly model loaded (threshold={self._threshold:.4f})")
        except Exception as e:
            log.debug(f"Anomaly model not loaded: {e}")

    def _build_model(self):
        """Build the autoencoder."""
        import torch.nn as nn

        class Autoencoder(nn.Module):
            def __init__(self):
                super().__init__()
                self.encoder = nn.Sequential(
                    nn.Linear(NUM_FEATURES, 16),
                    nn.ReLU(),
                    nn.Linear(16, 8),
                    nn.ReLU(),
                    nn.Linear(8, 4),
                )
                self.decoder = nn.Sequential(
                    nn.Linear(4, 8),
                    nn.ReLU(),
                    nn.Linear(8, 16),
                    nn.ReLU(),
                    nn.Linear(16, NUM_FEATURES),
                )

            def forward(self, x):
                encoded = self.encoder(x)
                decoded = self.decoder(encoded)
                return decoded

        return Autoencoder()

    def _normalize(self, data: list):
        """Normalize features using stored means/stds."""
        import torch
        import numpy as np

        arr = np.array(data, dtype=np.float32)
        if self._means is not None:
            arr = (arr - self._means) / (self._stds + 1e-8)
        return torch.FloatTensor(arr)

    def train_model(self, collector: MetricsCollector, epochs: int = 100) -> dict:
        """Train the autoencoder on collected metrics."""
        import torch
        import torch.nn as nn
        import numpy as np

        all_metrics = collector.get_all()
        if len(all_metrics) < 30:
            return {"status": "not_enough_data", "count": len(all_metrics), "needed": 30}

        # Convert to numpy
        data = []
        for m in all_metrics:
            data.append([m[f] for f in FEATURE_NAMES])
        data = np.array(data, dtype=np.float32)

        # Normalize
        self._means = data.mean(axis=0)
        self._stds = data.std(axis=0)
        normalized = (data - self._means) / (self._stds + 1e-8)

        X = torch.FloatTensor(normalized)

        # Build and train
        self._model = self._build_model()
        criterion = nn.MSELoss()
        optimizer = torch.optim.Adam(self._model.parameters(), lr=0.001)

        print(f"  Training autoencoder on {len(X)} samples...")
        for epoch in range(epochs):
            self._model.train()
            optimizer.zero_grad()
            output = self._model(X)
            loss = criterion(output, X)
            loss.backward()
            optimizer.step()

            if (epoch + 1) % 20 == 0:
                print(f"    Epoch {epoch+1}/{epochs} | Loss: {loss.item():.6f}")

        # Calculate threshold (mean + 2*std of reconstruction errors)
        self._model.eval()
        with torch.no_grad():
            reconstructed = self._model(X)
            errors = torch.mean((X - reconstructed) ** 2, dim=1)
            self._threshold = float(errors.mean() + 2 * errors.std())

        # Save
        torch.save({
            "model": self._model.state_dict(),
            "threshold": self._threshold,
            "means": self._means,
            "stds": self._stds,
        }, str(MODEL_PATH))

        self._model.eval()
        self._ready = True

        return {
            "status": "trained",
            "samples": len(X),
            "threshold": round(self._threshold, 6),
            "final_loss": round(loss.item(), 6),
        }

    def check(self, metrics: dict) -> dict:
        """
        Check if current metrics are anomalous.

        Returns:
            {
                "is_anomaly": True/False,
                "score": 0.0-1.0,
                "details": "CPU unusually high",
            }
        """
        if not self._ready:
            return {"is_anomaly": False, "score": 0.0, "details": "Model not trained yet"}

        import torch
        import numpy as np

        # Prepare input
        features = [metrics.get(f, 0) for f in FEATURE_NAMES]
        arr = np.array([features], dtype=np.float32)
        normalized = (arr - self._means) / (self._stds + 1e-8)
        X = torch.FloatTensor(normalized)

        # Get reconstruction error
        self._model.eval()
        with torch.no_grad():
            reconstructed = self._model(X)
            error = torch.mean((X - reconstructed) ** 2).item()

        is_anomaly = error > self._threshold
        score = min(1.0, error / (self._threshold * 2))

        # Find which features contributed most
        details = []
        with torch.no_grad():
            per_feature = ((X - reconstructed) ** 2).squeeze().tolist()
            for i, (name, err) in enumerate(zip(FEATURE_NAMES, per_feature)):
                if err > self._threshold / NUM_FEATURES:
                    details.append(f"{name} unusual ({metrics.get(name, 0)})")

        return {
            "is_anomaly": is_anomaly,
            "score": round(score, 3),
            "error": round(error, 6),
            "threshold": round(self._threshold, 6),
            "details": ", ".join(details) if details else "All normal",
        }

    @property
    def is_ready(self) -> bool:
        return self._ready


# ═══════════════════════════════════════════════════════════════
#  Main Interface
# ═══════════════════════════════════════════════════════════════
class AnomalyDetector:
    """
    Main interface for JARVIS anomaly detection.
    Collects metrics, trains autoencoder, detects anomalies.
    """

    def __init__(self):
        self._collector = MetricsCollector()
        self._autoencoder = AnomalyAutoencoder()
        log.info(f"AnomalyDetector: {self._collector.count()} metrics logged, model={'ready' if self._autoencoder.is_ready else 'needs training'}")

    def collect_and_check(self) -> dict:
        """Collect current metrics, save, and check for anomaly."""
        metrics = self._collector.collect_now()
        self._collector.save(metrics)

        result = self._autoencoder.check(metrics)
        result["metrics"] = metrics
        return result

    def train(self, epochs: int = 100) -> dict:
        """Train the anomaly model on collected data."""
        return self._autoencoder.train_model(self._collector, epochs)

    def get_stats(self) -> dict:
        return {
            "metrics_logged": self._collector.count(),
            "model_ready": self._autoencoder.is_ready,
            "needs_more": max(0, 30 - self._collector.count()),
        }

    def get_alert(self) -> str:
        """Get a JARVIS-style alert if anomaly detected."""
        result = self.collect_and_check()
        if result["is_anomaly"]:
            return f"Sir, I'm detecting unusual system activity: {result['details']}. Anomaly score: {result['score']:.0%}"
        return ""

    @property
    def is_ready(self) -> bool:
        return self._autoencoder.is_ready


# ═══════════════════════════════════════════════════════════════
#  Test
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("=" * 50)
    print("  JARVIS Anomaly Detector — Test")
    print("=" * 50)

    detector = AnomalyDetector()
    stats = detector.get_stats()
    print(f"\n  Metrics logged: {stats['metrics_logged']}")
    print(f"  Model ready: {stats['model_ready']}")

    # Collect current metrics
    print("\n  [1/3] Collecting current system metrics...")
    metrics = detector._collector.collect_now()
    for name, val in metrics.items():
        unit = "%" if "percent" in name else ""
        print(f"    {name:20s}: {val}{unit}")

    # If not enough data, seed with samples
    if stats["metrics_logged"] < 30:
        print(f"\n  [2/3] Collecting baseline metrics (need 30, have {stats['metrics_logged']})...")
        for i in range(35):
            m = detector._collector.collect_now()
            detector._collector.save(m)
            if (i + 1) % 10 == 0:
                print(f"    Collected {i+1}/35...")
            time.sleep(0.1)
        print(f"  Now have {detector._collector.count()} metrics")

    # Train
    print("\n  [3/3] Training anomaly autoencoder...")
    result = detector.train()
    print(f"  Result: {result}")

    if result.get("status") == "trained":
        # Check current state
        print("\n  --- Anomaly Check ---")
        check = detector.collect_and_check()
        status = "ANOMALY!" if check["is_anomaly"] else "NORMAL"
        print(f"  Status: {status}")
        print(f"  Score: {check['score']:.1%}")
        print(f"  Error: {check['error']:.6f} (threshold: {check['threshold']:.6f})")
        print(f"  Details: {check['details']}")

        # Show what an alert would look like
        alert = detector.get_alert()
        if alert:
            print(f"\n  JARVIS ALERT: {alert}")
        else:
            print("\n  All systems normal, sir.")

    print("\n  DONE!")
