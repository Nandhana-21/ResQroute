"""Severity prediction = ML probabilities + transparent safety rules (decision support only)."""
import os, joblib
from ml.train import MODEL, train
_m = None
CRIT_KW = ["unconscious","not breathing","difficulty breathing","chest pain","severe bleeding","heavy bleeding","stroke","slurred","face drooping","seizure","unresponsive","choking","blue lips"]
CRIT_TYPES = {"Chest pain","Breathing difficulty","Stroke symptoms","Unconsciousness","Severe bleeding"}
ORDER = ["MODERATE", "HIGH", "CRITICAL"]
REASON = {"CRITICAL": "Symptoms may indicate a serious cardiac, respiratory, neurological or bleeding emergency and require immediate medical evaluation.",
          "HIGH": "Symptoms suggest an urgent condition that needs prompt medical attention.",
          "MODERATE": "Symptoms need medical assistance but do not appear immediately life-threatening."}
def predict(symptoms, etype=""):
    global _m
    if _m is None: _m = joblib.load(MODEL) if os.path.exists(MODEL) else train()
    text = f"{symptoms} {etype}".lower()
    probs = dict(zip(_m.classes_, _m.predict_proba([text])[0]))
    sev = max(probs, key=probs.get); hits = [k for k in CRIT_KW if k in text]
    floor = "CRITICAL" if hits else ("HIGH" if etype in CRIT_TYPES else "MODERATE")
    overridden = ORDER.index(floor) > ORDER.index(sev)
    if overridden: sev = floor
    conf = min(0.95, 0.6 + 0.1 * len(hits)) if overridden else probs[sev]
    why = REASON[sev] + (f" Key terms detected: {', '.join(hits)}." if hits else "") + " (Prototype AI - not a medical diagnosis.)"
    return sev, round(float(conf), 2), why
