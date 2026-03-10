"""
Enhanced Job Guard Model Training - Higher accuracy with more data.
- Cross-validation & proper metrics (precision, recall, F1, ROC-AUC)
- Threshold tuning
- Data augmentation for minority class (fraudulent)
- Multi-dataset loading
- Optional stronger models (RandomForest, XGBoost)
"""
import argparse
import json
import os
import re
import ssl

import joblib
import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix, hstack
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
    roc_curve,
)
from sklearn.model_selection import GridSearchCV, StratifiedKFold, train_test_split
from sklearn.preprocessing import MaxAbsScaler

try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError:
    pass
else:
    ssl._create_default_https_context = _create_unverified_https_context

try:
    from nltk.tokenize import word_tokenize
    from nltk.corpus import stopwords
    from nltk.stem import WordNetLemmatizer
    import nltk
    nltk.download("punkt", quiet=True)
    nltk.download("punkt_tab", quiet=True)
    nltk.download("stopwords", quiet=True)
    nltk.download("wordnet", quiet=True)
    USE_NLTK = True
except Exception:
    USE_NLTK = False

META_FEATURES = [
    "text_length", "word_count", "has_email", "has_url", "exclamation_count",
    "caps_ratio", "telecommuting", "has_company_logo", "has_questions",
]


def preprocess_text(text):
    if not isinstance(text, str) or not text.strip():
        return "empty"
    text = str(text).lower().strip()
    text = re.sub(r"https?://\S+|www\.\S+", "", text)
    text = re.sub(r"[\w.+-]+@[\w-]+\.[\w.-]+", "", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"[^a-z\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if USE_NLTK:
        try:
            words = word_tokenize(text)
            stop = set(stopwords.words("english"))
            words = [w for w in words if w not in stop and len(w) > 1]
            lemmatizer = WordNetLemmatizer()
            words = [lemmatizer.lemmatize(w) for w in words]
            return " ".join(words) if words else "empty"
        except Exception:
            pass
    return text


def load_and_prepare_data(csv_paths, augment_fraud=0):
    """Load one or more CSVs, optionally augment minority class."""
    dfs = []
    for p in csv_paths:
        if os.path.exists(p):
            dfs.append(pd.read_csv(p))
        else:
            print(f"Warning: {p} not found, skipping")
    if not dfs:
        raise FileNotFoundError("No dataset files found")
    df = pd.concat(dfs, ignore_index=True)
    if "job_id" in df.columns:
        df = df.drop_duplicates(subset=["job_id"], keep="first")
    
    # Combine text
    text_cols = ["title", "company_profile", "description", "requirements", "benefits"]
    for c in text_cols:
        if c not in df.columns:
            df[c] = ""
    df["text_data"] = (
        df["title"].fillna("") + " "
        + df["company_profile"].fillna("") + " "
        + df["description"].fillna("") + " "
        + df["requirements"].fillna("") + " "
        + df["benefits"].fillna("")
    ).str.strip().str.replace(r"\s+", " ", regex=True)

    # Meta features
    t = df["text_data"]
    df["text_length"] = t.str.len()
    df["word_count"] = t.str.split().str.len().fillna(0).astype(int)
    df["has_email"] = t.str.contains(r"[\w.+-]+@[\w-]+\.[\w.-]+", regex=True, na=False).astype(int)
    df["has_url"] = t.str.contains("http", case=False, na=False).astype(int)
    df["exclamation_count"] = t.str.count(r"!").fillna(0).astype(int)
    df["caps_ratio"] = t.apply(lambda s: sum(1 for c in str(s) if c.isupper()) / max(len(str(s)), 1))
    df["telecommuting"] = df["telecommuting"].fillna(0).astype(int)
    df["has_company_logo"] = df["has_company_logo"].fillna(0).astype(int)
    df["has_questions"] = df["has_questions"].fillna(0).astype(int)

    df["clean_text"] = df["text_data"].apply(preprocess_text)
    df = df[df["clean_text"] != "empty"]

    # Augment fraudulent samples (simple mix-up of two fraud posts)
    if augment_fraud > 0:
        fraud_df = df[df["fraudulent"] == 1]
        if len(fraud_df) >= 2:
            extra_rows = []
            for _ in range(augment_fraud):
                r1, r2 = fraud_df.sample(2, replace=True).iloc[0], fraud_df.sample(2, replace=True).iloc[1]
                t1, t2 = str(r1["text_data"]), str(r2["text_data"])
                new_text = (t1[: len(t1) // 2] + " " + t2[len(t2) // 2 :]).strip()
                row = r1.to_dict()
                row["text_data"] = new_text
                row["clean_text"] = preprocess_text(new_text)
                row["text_length"] = len(new_text)
                row["word_count"] = len(new_text.split())
                row["fraudulent"] = 1
                extra_rows.append(row)
            df = pd.concat([df, pd.DataFrame(extra_rows)], ignore_index=True)

    return df


def find_best_threshold(y_true, y_prob):
    """Find threshold that maximizes F1."""
    fpr, tpr, thresholds = roc_curve(y_true, y_prob)
    best_f1, best_t = 0, 0.5
    for t in np.arange(0.2, 0.8, 0.02):
        pred = (y_prob >= t).astype(int)
        f1 = f1_score(y_true, pred, zero_division=0)
        if f1 > best_f1:
            best_f1, best_t = f1, t
    return best_t


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", nargs="+", default=["model_training/jobguard-dataset.csv"],
                        help="CSV paths to load")
    parser.add_argument("--augment", type=int, default=500,
                        help="Augment fraudulent samples by this many (0 to disable)")
    parser.add_argument("--model", choices=["logistic", "random_forest"], default="logistic")
    parser.add_argument("--tune", action="store_true", help="Grid search hyperparameters")
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--out-dir", default="model_artifacts")
    args = parser.parse_args()

    print("Loading dataset(s)...")
    df = load_and_prepare_data(args.data, augment_fraud=args.augment)
    print(f"Total samples: {len(df)} | Fraudulent: {df['fraudulent'].sum()} | Legitimate: {(df['fraudulent']==0).sum()}")

    # Vectorize
    tfidf = TfidfVectorizer(max_features=6000, ngram_range=(1, 2), min_df=2, max_df=0.92)
    X_tfidf = tfidf.fit_transform(df["clean_text"])
    scaler = MaxAbsScaler()
    X_meta = scaler.fit_transform(df[META_FEATURES].fillna(0))
    X = hstack([X_tfidf, csr_matrix(X_meta)])
    y = df["fraudulent"].values

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=args.test_size, stratify=y, random_state=42
    )

    if args.model == "logistic":
        if args.tune:
            grid = GridSearchCV(
                LogisticRegression(class_weight="balanced", solver="lbfgs", max_iter=2000, random_state=42),
                {"C": [0.5, 1.0, 2.0], "max_iter": [1000, 2000]},
                cv=StratifiedKFold(5, shuffle=True, random_state=42),
                scoring="f1",
                n_jobs=-1,
            )
            grid.fit(X_train, y_train)
            model = grid.best_estimator_
            print(f"Best params: {grid.best_params_}")
        else:
            model = LogisticRegression(C=1.0, max_iter=2000, class_weight="balanced", solver="lbfgs", random_state=42)
            model.fit(X_train, y_train)
    else:
        model = RandomForestClassifier(n_estimators=200, max_depth=20, class_weight="balanced", random_state=42, n_jobs=-1)
        model.fit(X_train, y_train)

    # Threshold tuning
    y_prob = model.predict_proba(X_test)[:, 1]
    best_threshold = find_best_threshold(y_test, y_prob)
    y_pred = (y_prob >= best_threshold).astype(int)

    print("\n--- Evaluation (optimized threshold) ---")
    print(f"Threshold: {best_threshold:.3f}")
    print(f"Accuracy:  {accuracy_score(y_test, y_pred):.4f}")
    print(f"Precision: {precision_score(y_test, y_pred, zero_division=0):.4f}")
    print(f"Recall:    {recall_score(y_test, y_pred, zero_division=0):.4f}")
    print(f"F1:       {f1_score(y_test, y_pred, zero_division=0):.4f}")
    try:
        print(f"ROC-AUC:  {roc_auc_score(y_test, y_prob):.4f}")
    except Exception:
        pass
    print("\nClassification Report:")
    print(classification_report(y_test, y_pred, target_names=["Legitimate", "Fraudulent"]))

    os.makedirs(args.out_dir, exist_ok=True)
    joblib.dump(model, os.path.join(args.out_dir, "classifier.pkl"))
    joblib.dump(tfidf, os.path.join(args.out_dir, "tfidf_vectorizer.pkl"))
    joblib.dump(scaler, os.path.join(args.out_dir, "meta_scaler.pkl"))
    json.dump(
        {"meta_features": META_FEATURES, "threshold": round(best_threshold, 4)},
        open(os.path.join(args.out_dir, "model_config.json"), "w"),
    )
    print(f"\nSaved artifacts to {args.out_dir}/")


if __name__ == "__main__":
    main()
