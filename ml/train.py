"""Builds a SYNTHETIC demo dataset and trains a TF-IDF + Logistic Regression severity classifier.
Run: python ml/train.py   (NOT clinically validated - prototype only)"""
import os, random, pandas as pd, joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
D = os.path.dirname(os.path.abspath(__file__)); MODEL = os.path.join(D, "model.pkl"); DATA = os.path.join(D, "dataset.csv")
SEED = {
 "CRITICAL": ["severe chest pain and difficulty breathing","unconscious and not responding","heavy bleeding that will not stop","face drooping, slurred speech, arm weakness","not breathing properly, lips turning blue","chest pain spreading to left arm with sweating","seizure and unresponsive","choking and cannot speak","collapsed suddenly and unresponsive","severe head injury after road accident, vomiting"],
 "HIGH": ["suspected fracture after fall, severe pain","road accident with leg injury","high fever with confusion","deep cut with bleeding, pressure applied","pregnant woman with labour pains","severe abdominal pain and vomiting","burn injury on arm and chest","persistent vomiting and dehydration","asthma attack, inhaler helping slightly","allergic reaction with swelling of face"],
 "MODERATE": ["mild fever and headache","sprained ankle, can walk with pain","minor cut, bleeding controlled","stomach ache since morning","dizziness but alert and talking","mild allergic rash","small burn on hand","back pain after lifting","nausea, vomited once","twisted wrist, can move fingers"]}
def build():
    random.seed(1); rows = []
    for sev, items in SEED.items():
        rows += [(t, sev) for t in items]
        rows += [(", ".join(random.sample(items, 2)), sev) for _ in range(25)]
    pd.DataFrame(rows, columns=["symptoms", "severity"]).to_csv(DATA, index=False)
def train():
    if not os.path.exists(DATA): build()
    df = pd.read_csv(DATA)
    m = make_pipeline(TfidfVectorizer(ngram_range=(1, 2)), LogisticRegression(max_iter=1000, C=5))
    m.fit(df.symptoms, df.severity); joblib.dump(m, MODEL); return m
if __name__ == "__main__":
    build(); train(); print("Trained model ->", MODEL)
