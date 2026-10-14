"""Token-free inference from the inspected, pinned pretrained numeric model.

No pickle, native model library, runtime download, training, or external call.
"""
import hashlib
import json
import math
import struct
from functools import lru_cache
from pathlib import Path
from .hosted_model import FEATURES, CLASSES, ModelUnavailable, feature_payload

MODEL_PATH = Path(__file__).resolve().parent / "models" / "maternal_catboost.json"
EXPECTED_SHA256 = "3aa8650ae2405c3b32e82a4afcf0ce7379f5e80d751944701fa239a0e4215837"
VERSION = "bundled-catboost-" + EXPECTED_SHA256[:16]

@lru_cache(maxsize=1)
def load():
    raw = MODEL_PATH.read_bytes()
    if hashlib.sha256(raw).hexdigest() != EXPECTED_SHA256:
        raise ModelUnavailable("The bundled model failed its integrity check. Your measurements remain saved.")
    model = json.loads(raw)
    if model["format"] != "bloom-catboost-numeric-v1" or model["features"] != FEATURES or model["classes"] != CLASSES:
        raise ModelUnavailable("The bundled model schema is incompatible. Your measurements remain saved.")
    return model

def metadata():
    model = load()
    return {"version": VERSION, "sha256": EXPECTED_SHA256,
        "remote_version": model["source_revision"], "source_url": model["source_url"],
        "features": FEATURES, "classes": CLASSES, "feature_schema": "uci-maternal-v1",
        "status": "bundled-research-model", "provider": "bundled", "external": False,
        "architecture": "Pretrained CatBoost multiclass classifier; 500 symmetric trees",
        "decision_rule": "argmax of original model scores; out-of-reference-range results require review",
        "sequence_note": "Single-visit classification with original fitted scaling. No longitudinal prediction or missing-value imputation.",
        "description": "Pretrained research model runs inside Bloom without an API key, token, model-service fee or external transmission. Clinical validation is not established.",
        "test_accuracy": None, "input_ranges": None,
        "reference_ranges": model["reference_ranges"],
        "range_note": "Bounds describe the cleaned source dataset, not guaranteed training-fold coverage or healthy clinical ranges.",
        "limitations": "The source reports limited mid-risk recall. Glucose fasting status is unspecified. Scores are not calibrated clinical probabilities."}

def scores_for_features(row):
    model = load()
    if len(row) != 6 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in row):
        raise ModelUnavailable("Six finite measured inputs are required. Missing clinical measurements cannot be invented.")
    # CatBoost quantizes numeric inputs to float32 after the fitted StandardScaler.
    scaled = [struct.unpack("f", struct.pack("f", (v-mean)/scale))[0]
              for v,mean,scale in zip(row,model["mean"],model["scale"])]
    scores = [0.0,0.0,0.0]
    for tree in model["trees"]:
        leaf = 0
        for bit,(feature,border) in enumerate(tree["splits"]):
            if scaled[feature] > border:
                leaf |= 1 << bit
        for category in range(3):
            scores[category] += tree["leaves"][3*leaf+category]
    scale,bias = model["scale_and_bias"]
    logits = [value*scale+offset for value,offset in zip(scores,bias)]
    maximum = max(logits)
    exponents = [math.exp(value-maximum) for value in logits]
    total = sum(exponents)
    return [value/total for value in exponents]

def predict(values):
    try:
        features = feature_payload(values)
    except (KeyError,TypeError,ValueError):
        raise ModelUnavailable("Six measured inputs with known units are required. Your measurements remain saved.") from None
    scores = scores_for_features([features[key] for key in FEATURES])
    probabilities = dict(zip(CLASSES,scores))
    outside = [key for key,(lo,hi) in load()["reference_ranges"].items() if not lo <= features[key] <= hi]
    return {"category": max(CLASSES,key=lambda key:probabilities[key]),
        "probabilities": probabilities, "outside_training_range": outside,
        "review_required": bool(outside), "source": load()["source_url"],
        "source_revision": load()["source_revision"], "assessment_mode": "bundled",
        "review_message": "Some readings are outside the source dataset range. The research scores may be unreliable; contact your maternity care team for assessment." if outside else None}
