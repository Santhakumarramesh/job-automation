import os
import json
import re
import numpy as np
import joblib
from scipy.sparse import hstack, csr_matrix

from agents.state import AgentState

# Load ML Artifacts once to avoid latency
MODEL_DIR = 'model_artifacts'
try:
    classifier = joblib.load(os.path.join(MODEL_DIR, 'classifier.pkl'))
    tfidf = joblib.load(os.path.join(MODEL_DIR, 'tfidf_vectorizer.pkl'))
    scaler = joblib.load(os.path.join(MODEL_DIR, 'meta_scaler.pkl'))
    
    with open(os.path.join(MODEL_DIR, 'model_config.json'), 'r') as f:
        config = json.load(f)
        META_FEATURES = config['meta_features']
        # The dataset logic treats 1 as fraudulent, 0 as legit.
        THRESHOLD = config['threshold']
    MODEL_LOADED = True
except Exception as e:
    print(f"Job Guard DB Warning: {e}")
    MODEL_LOADED = False

# NLTK imports
try:
    from nltk.tokenize import word_tokenize
    from nltk.corpus import stopwords
    from nltk.stem import WordNetLemmatizer
    import nltk
    USE_NLTK = True
except:
    USE_NLTK = False

def preprocess_text(text):
    if not isinstance(text, str): return ""
    text = str(text).lower().strip()
    text = re.sub(r'https?://\S+|www\.\S+', '', text)
    text = re.sub(r'[\w.+-]+@[\w-]+\.[\w.-]+', '', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'[^a-z\s]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    if USE_NLTK:
        try:
            words = word_tokenize(text)
            stop = set(stopwords.words('english'))
            words = [w for w in words if w not in stop and len(w) > 1]
            lemmatizer = WordNetLemmatizer()
            words = [lemmatizer.lemmatize(w) for w in words]
            return ' '.join(words) if words else 'empty'
        except:
            return text
    return text

def extract_meta(text: str) -> np.ndarray:
    # Ensure caps_ratio is between 0 and 1
    caps_ratio = sum(1 for c in text if c.isupper()) / max(len(text), 1)
    caps_ratio = min(caps_ratio, 1.0)

    feats = {
        'text_length': len(text),
        'word_count': len(text.split()),
        'has_email': int(bool(re.search(r'[\w.+-]+@[\w-]+\.[\w.-]+', text))),
        'has_url': int(bool(re.search(r'https?://', text))),
        'exclamation_count': text.count('!'),
        'caps_ratio': caps_ratio,
        'telecommuting': 0,
        'has_company_logo': 0,
        'has_questions': 0,
    }
    return np.array([[feats.get(n, 0) for n in META_FEATURES]], dtype=float)

def guard_job_quality(state: AgentState):
    """
    Evaluates raw job descriptions natively using a trained Scikit-learn
    fraud detection model to instantly reject scams or garbage posts.
    """
    # Initialize basic validation flags implicitly
    if "job_description" not in state or not state["job_description"].strip():
        return {"is_eligible": False}

    jd_text = state["job_description"]

    # F1 OPT Security Clearance / Extreme Seniority Heuristic
    if re.search(r'(10\+|12\+|15\+)\s*years?', jd_text, re.IGNORECASE) or \
       re.search(r'(top secret|ts/sci|dod clearance|security clearance)', jd_text, re.IGNORECASE):
        state["eligibility_reason"] = "Required Security Clearance or 10+ YOE"
        return {"is_eligible": False}

    if not MODEL_LOADED:
        return {"is_eligible": True}  # Gracefully fallback if no artifacts

    try:
        clean_text = preprocess_text(jd_text)
        X_text = tfidf.transform([clean_text])
        X_meta = scaler.transform(extract_meta(jd_text))
        X_in = hstack([X_text, csr_matrix(X_meta)])
        
        # 1 is fraudulent, 0 is legitimate
        fraud_prob = classifier.predict_proba(X_in)[0][1]
        
        # If the Guard rejects it, we immediately set is_eligible to False so the pipeline skips it.
        if fraud_prob >= THRESHOLD:
            state["eligibility_reason"] = f"Job Guard ML blocked as Fraud/Spam (Risk: {fraud_prob*100:.1f}%)"
            return {"is_eligible": False}
    except AttributeError as e:
        if "'MaxAbsScaler' object has no attribute 'clip'" in str(e):
            print("⚠️ Job Guard Warning: ML model is incompatible. Fraud detection is temporarily offline. Allowing job to proceed.")
        else:
            # If it's a different AttributeError, we should still know about it
            print(f"Job Guard encountered an unexpected AttributeError: {e}")
    except Exception as e:
        print(f"An unexpected error occurred in Job Guard: {e}")
        
    return {"is_eligible": True}
