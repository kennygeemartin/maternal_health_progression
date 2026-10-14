"""Strict JSON interface for a documented, version-pinned hosted maternal model."""
import hashlib
import json
import math
import os
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

FEATURES = ["Age", "SystolicBP", "DiastolicBP", "BS", "BodyTemp", "HeartRate"]
CLASSES = ["low", "mid", "high"]
SCHEMA = "uci-maternal-v1"
SPACE = "Silvio0/maternal-risk-gradio-direct"
REVISION = "82ffc870e3bbfb5693b02a8a7804f1f1f7a21dc0"
HF_URL = "https://silvio0-maternal-risk-gradio-direct.hf.space"
INPUT_RANGES = {"Age": (10,70), "SystolicBP": (70,160), "DiastolicBP": (49,100),
                "BS": (6,19), "BodyTemp": (98,103), "HeartRate": (60,90)}

def provider():
    return os.getenv("RISK_MODEL_PROVIDER", "rest" if os.getenv("RISK_MODEL_URL") else "bundled")

class ModelUnavailable(RuntimeError):
    pass

def configured():
    return provider() == "huggingface" or (provider() == "rest" and bool(os.getenv("RISK_MODEL_URL") and os.getenv("RISK_MODEL_VERSION") and os.getenv("RISK_MODEL_CARD_URL")))

def settings():
    if provider() == "huggingface":
        return HF_URL, REVISION, "https://huggingface.co/spaces/" + SPACE
    endpoint = os.getenv("RISK_MODEL_URL", "")
    parsed = urlparse(endpoint)
    source = os.getenv("RISK_MODEL_CARD_URL", "")
    if not configured() or parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or not source.startswith("https://"):
        raise ModelUnavailable("A documented HTTPS assessment endpoint and model version have not been configured.")
    return endpoint, os.environ["RISK_MODEL_VERSION"], source

def metadata():
    endpoint, version, source = settings()
    identity = hashlib.sha256((endpoint + version + source).encode()).hexdigest()[:20]
    return {"version": "hosted-" + identity, "remote_version": version, "provider_url": endpoint,
            "source_url": source, "features": FEATURES, "classes": CLASSES,
            "feature_schema": SCHEMA, "decision_rule": "argmax of validated probabilities",
            "sequence_note": "Single-visit assessment using six measurements; no longitudinal sequence or imputation.",
            "status": "external-research-model", "test_accuracy": None,
            "description": "Externally hosted pretrained model. Clinical validation is not established by this integration.",
            "input_ranges": INPUT_RANGES if provider() == "huggingface" else None}

def feature_payload(values):
    # UCI defines BS in mmol/L. The observation form stores glucose in mg/dL.
    return {"Age": values["Age"], "SystolicBP": values["SystolicBP"],
            "DiastolicBP": values["DiastolicBP"], "BS": values["FastingGlucose"] / 18.0182,
            "BodyTemp": values["BodyTempC"] * 9 / 5 + 32 if "BodyTempC" in values else values["BodyTempF"],
            "HeartRate": values["HeartRate"]}

def predict(values):
    if provider() == "huggingface":
        return predict_huggingface(values)
    endpoint, expected_version, _ = settings()
    payload = {"feature_schema": SCHEMA, "features": feature_payload(values),
               "units": {"Age":"years", "SystolicBP":"mmHg", "DiastolicBP":"mmHg", "BS":"mmol/L", "BodyTemp":"degF", "HeartRate":"bpm"}}
    headers = {"Content-Type":"application/json", "User-Agent":"Bloom-research-assessment/1.0"}
    if os.getenv("RISK_MODEL_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["RISK_MODEL_TOKEN"]
    try:
        with urlopen(Request(endpoint, data=json.dumps(payload).encode(), headers=headers, method="POST"), timeout=15) as response:
            raw = response.read(65537)
        if len(raw) > 65536:
            raise ValueError("Oversized response")
        result = json.loads(raw)
        if result.get("model_version") != expected_version or result.get("feature_schema") != SCHEMA:
            raise ValueError("Model identity or feature schema changed")
        probs = result["probabilities"]
        if set(probs) != set(CLASSES) or any(isinstance(p, bool) or not isinstance(p, (int,float)) or not math.isfinite(p) or not 0 <= p <= 1 for p in probs.values()) or abs(sum(probs.values()) - 1) > .001:
            raise ValueError("Invalid probabilities")
        category = max(CLASSES, key=lambda key: probs[key])
        if result.get("category") != category:
            raise ValueError("Category and probabilities disagree")
        return {"category": category, "probabilities": probs, "outside_training_range": [],
                "remote_model_version": expected_version, "source": metadata()["source_url"]}
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, KeyError, TypeError, AttributeError):
        raise ModelUnavailable("The hosted assessment service is unavailable or returned an incompatible result. Your measurements remain saved.") from None

def predict_huggingface(values):
    features = feature_payload(values)
    unsupported = [key for key, (lo,hi) in INPUT_RANGES.items() if not lo <= features[key] <= hi]
    if unsupported:
        raise ModelUnavailable("This research service does not support these measurements: " + ", ".join(unsupported) + ". Its glucose range is 6–19 mmol/L (about 108–342 mg/dL). Values have not been changed; your measurements remain saved. Contact your care team for assessment.")
    try:
        headers = {"Content-Type": "application/json"}
        if os.getenv("HF_TOKEN"):
            headers["Authorization"] = "Bearer " + os.environ["HF_TOKEN"]
        with urlopen("https://huggingface.co/api/spaces/" + SPACE, timeout=5) as response:
            identity = json.load(response)
        if identity.get("sha") != REVISION or identity.get("runtime", {}).get("sha", REVISION) != REVISION:
            raise ValueError("Provider revision changed")
        root = HF_URL + "/gradio_api/call/process_maternal_health"
        request = Request(root, data=json.dumps({"data": [features[key] for key in FEATURES]}).encode(),
                          headers=headers, method="POST")
        with urlopen(request, timeout=8) as response:
            event = json.load(response)["event_id"]
        if not isinstance(event, str) or len(event) != 32 or any(c not in "0123456789abcdef" for c in event):
            raise ValueError("Invalid event")
        with urlopen(Request(root + "/" + event, headers=headers), timeout=25) as response:
            raw = response.read(2000001)
        if len(raw) > 2000000:
            raise ValueError("Oversized result")
        event_type = None
        outputs = None
        for line in raw.decode().splitlines():
            if line.startswith("event: "):
                event_type = line[7:]
            elif line.startswith("data: ") and event_type == "complete":
                outputs = json.loads(line[6:])
                break
        # Ignore the provider's HTML explanation entirely. Only structured label scores enter Bloom.
        scores = outputs[2]["confidences"]
        probs = {item["label"].lower().replace(" risk", ""): item["confidence"] for item in scores}
        if len(scores) != 3 or set(probs) != set(CLASSES) or any(isinstance(p,bool) or not isinstance(p,(int,float)) or not math.isfinite(p) or not 0 <= p <= 1 for p in probs.values()) or abs(sum(probs.values())-1) > .001:
            raise ValueError("Invalid scores")
        category = max(CLASSES, key=lambda key: probs[key])
        if outputs[0].lower().replace(" risk", "") != category:
            raise ValueError("Inconsistent category")
        return {"category": category, "probabilities": probs, "outside_training_range": [],
                "remote_model_version": REVISION, "source": metadata()["source_url"]}
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, KeyError, TypeError, AttributeError, IndexError):
        raise ModelUnavailable("The public research assessment service is unavailable or its version changed. Your measurements remain saved. Try again later or contact your care team.") from None
