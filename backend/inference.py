"""Match the supplied training pipeline exactly; never refit the scaler."""
import hashlib
import json
import pickle
from pathlib import Path
from functools import lru_cache
from . import hosted_model

ROOT = Path(__file__).resolve().parents[1] / "Results"
FEATURES = ["Age", "BodyTempF", "HeartRate", "SystolicBP", "DiastolicBP", "BMI", "HbA1c", "FastingGlucose"]
CLASSES = ["low", "mid", "high"]
UNIT_ISSUE = ("The supplied dataset has HbA1c values 30–50 and fasting glucose 3.6–8.9, "
              "inconsistent with its percent and mg/dL labels. Model assessment is disabled "
              "until the dataset units and preprocessing are verified. Your measurements remain saved.")


def metadata():
    if hosted_model.configured():
        return hosted_model.metadata()
    report = json.loads((ROOT / "maternal_model_results.json").read_text())
    digest = hashlib.sha256((ROOT / "proposed_lstm.pt").read_bytes()).hexdigest()
    return {"version": "proposed-lstm-" + digest[:12], "sha256": digest,
            "scaler_sha256": hashlib.sha256((ROOT / "maternal_model_scaler.pkl").read_bytes()).hexdigest(),
            "features": FEATURES, "classes": CLASSES, "decision_rule": "argmax; no clinical thresholds supplied",
            "sequence_note": report["model_training"]["proposed_lstm"]["sequence_note"],
            "test_accuracy": report["main_test_results"][0]["accuracy"], "status": "blocked-unit-verification",
            "unit_issue": UNIT_ISSUE}


@lru_cache
def load():
    import torch
    from torch import nn

    class Classifier(nn.Module):
        def __init__(self):
            super().__init__()
            self.lstm = nn.LSTM(1, 50, num_layers=1, batch_first=True)
            self.dropout = nn.Dropout(0.20)
            self.fc = nn.Linear(50, 3)

        def forward(self, x):
            out, _ = self.lstm(x)
            return self.fc(self.dropout(out[:, -1, :]))

    model = Classifier()
    model.load_state_dict(torch.load(ROOT / "proposed_lstm.pt", map_location="cpu", weights_only=True))
    model.eval()
    # This is a trusted, locally supplied training artifact. Never accept uploaded pickle files.
    with (ROOT / "maternal_model_scaler.pkl").open("rb") as source:
        scaler = pickle.load(source)
    if list(scaler.feature_names_in_) != FEATURES:
        raise RuntimeError("Scaler feature schema does not match the model")
    return model, scaler


def predict(values):
    if hosted_model.configured():
        return hosted_model.predict(values)
    # A successful state-dict load is insufficient evidence of valid clinical units.
    # Release this guard only alongside verified source-unit preprocessing and tests.
    raise RuntimeError(UNIT_ISSUE)


def predict_artifact(values):
    """Raw source-feature inference for artifact compatibility tests, never a clinical API."""
    import pandas as pd
    import torch
    model, scaler = load()
    frame = pd.DataFrame([[values[name] for name in FEATURES]], columns=FEATURES)
    scaled = scaler.transform(frame)
    # Complete records only: no padding, masking or imputation is needed for [1,8,1].
    with torch.inference_mode():
        probs = torch.softmax(model(torch.tensor(scaled.reshape(1, 8, 1), dtype=torch.float32)), dim=1)[0].tolist()
    outside = [name for i, name in enumerate(FEATURES)
               if values[name] < scaler.data_min_[i] or values[name] > scaler.data_max_[i]]
    return {"category": CLASSES[max(range(3), key=lambda i: probs[i])],
            "probabilities": dict(zip(CLASSES, probs)), "outside_training_range": outside}
