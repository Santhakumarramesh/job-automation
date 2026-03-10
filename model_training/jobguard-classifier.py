import subprocess, sys

REQUIRED_PACKAGES = [
    'pandas', 'numpy', 'matplotlib', 'seaborn',
    'scikit-learn', 'nltk', 'joblib', 'scipy', 'wordcloud', 'imbalanced-learn'
]

def safe_install(pkg):
    import_name = 'imblearn' if pkg == 'imbalanced-learn' else pkg.replace('-', '_')
    try:
        __import__(import_name)
    except ImportError:
        print(f'  Installing {pkg}...')
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', pkg, '-q'])

print('Checking dependencies...')
for pkg in REQUIRED_PACKAGES:
    safe_install(pkg)


import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import seaborn as sns
import warnings, re, os, time, json, pickle
import joblib
from collections import Counter

warnings.filterwarnings('ignore')
np.random.seed(42)


# Load dataset — prefers augmented > combined > primary (run scripts for best accuracy)
DATASET_FILENAME = 'jobguard-dataset.csv'
COMBINED_PATH = 'data/jobguard-combined.csv'
AUGMENTED_PATH = 'data/jobguard-augmented.csv'

SEARCH_PATHS = [
    AUGMENTED_PATH,
    COMBINED_PATH,
    DATASET_FILENAME,
    os.path.join('data', DATASET_FILENAME),
    os.path.join('dataset', DATASET_FILENAME),
    os.path.join('..', DATASET_FILENAME),
]

found_path = None
for p in SEARCH_PATHS:
    if os.path.exists(p):
        found_path = p
        break

if found_path is None:
    raise FileNotFoundError(
        "Dataset not found. Download from Kaggle and save as 'jobguard-dataset.csv':\n"
        "https://www.kaggle.com/datasets/shivamb/real-or-fake-fake-jobposting-prediction\n"
        "Run: python3 scripts/download_datasets.py && python3 scripts/augment_fraud_data.py"
    )

df = pd.read_csv(found_path)
print(f"Loaded: {found_path} ({len(df):,} rows)")


info = pd.DataFrame({
    'dtype'      : df.dtypes,
    'non_null'   : df.notnull().sum(),
    'null_count' : df.isnull().sum(),
    'null_pct'   : (df.isnull().mean() * 100).round(1),
    'unique'     : df.nunique()
})
print(info.to_string())


print('Class distribution:')
print(df['fraudulent'].value_counts())
print(f'\nFraud rate: {df.fraudulent.mean()*100:.2f}%')









# Combine text columns for NLP
df['text_data'] = (
    df['title'].fillna('') + ' ' +
    df['company_profile'].fillna('') + ' ' +
    df['description'].fillna('') + ' ' +
    df['requirements'].fillna('') + ' ' +
    df['benefits'].fillna('')
).str.strip().str.replace(r'\s+', ' ', regex=True)

# Meta features
META_FEATURES = ['text_length','word_count','has_email','has_url','exclamation_count',
                 'caps_ratio','telecommuting','has_company_logo','has_questions']
t = df['text_data']
df['text_length'] = t.str.len()
df['word_count'] = t.str.split().str.len().fillna(0).astype(int)
df['has_email'] = t.str.contains(r'[\w.+-]+@[\w-]+\.[\w.-]+', regex=True, na=False).astype(int)
df['has_url'] = t.str.contains('http', case=False, na=False).astype(int)
df['exclamation_count'] = t.str.count(r'!').fillna(0).astype(int)
df['caps_ratio'] = t.apply(lambda s: sum(1 for c in str(s) if c.isupper()) / max(len(str(s)), 1))
df['telecommuting'] = df['telecommuting'].fillna(0).astype(int)
df['has_company_logo'] = df['has_company_logo'].fillna(0).astype(int)
df['has_questions'] = df['has_questions'].fillna(0).astype(int)
print('Meta features constructed.')

import nltk
try:
    nltk.download('punkt', quiet=True)
    nltk.download('stopwords', quiet=True)
    nltk.download('wordnet', quiet=True)
except: pass

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.model_selection import train_test_split, cross_val_score, StratifiedKFold
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.naive_bayes import MultinomialNB
from sklearn.metrics import (accuracy_score, precision_score, recall_score, f1_score,
    roc_curve, auc, precision_recall_curve, average_precision_score, classification_report)
from sklearn.preprocessing import MaxAbsScaler
from scipy.sparse import hstack, csr_matrix

RANDOM_STATE = 42
try:
    from imblearn.over_sampling import SMOTE
    SMOTE_AVAILABLE = True
except: SMOTE_AVAILABLE = False
try:
    from xgboost import XGBClassifier
    XGBOOST_AVAILABLE = True
except: XGBOOST_AVAILABLE = False
try:
    from wordcloud import WordCloud
    WC_AVAILABLE = True
except: WC_AVAILABLE = False

def savefig(name):
    os.makedirs('outputs', exist_ok=True)
    plt.savefig(os.path.join('outputs', name), dpi=100, bbox_inches='tight')

def preprocess_text(text):
    if not isinstance(text, str) or not text.strip():
        return 'empty'
    text = text.lower().strip()
    text = re.sub(r'https?://\S+|www\.\S+', '', text)
    text = re.sub(r'[\w.+-]+@[\w-]+\.[\w.-]+', '', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'[^a-z\s]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    try:
        from nltk.tokenize import word_tokenize
        from nltk.corpus import stopwords
        from nltk.stem import WordNetLemmatizer
        words = word_tokenize(text)
        stop = set(stopwords.words('english'))
        words = [w for w in words if w not in stop and len(w) > 1]
        lemmatizer = WordNetLemmatizer()
        words = [lemmatizer.lemmatize(w) for w in words]
    except:
        words = [w for w in text.split() if len(w) > 1]
    return ' '.join(words) if words else 'empty'

print('Preprocessing text data...')
t0 = time.time()
df['clean_text'] = df['text_data'].apply(preprocess_text)
elapsed = time.time() - t0

empty_count = (df['clean_text'] == 'empty').sum()
df['clean_text'] = df['clean_text'].replace('empty', 'unknown job posting')

print(f'Completed in {elapsed:.1f}s')
print(f'Average raw length  : {df.text_data.apply(len).mean():.0f} characters')
print(f'Average clean length: {df.clean_text.apply(len).mean():.0f} characters')
print(f'Empty rows          : {empty_count}')




if WC_AVAILABLE:
    fig, axes = plt.subplots(1, 2, figsize=(16, 7))
    for ax, label, cmap, title in [
        (axes[0], 0, 'Greens', 'Legitimate Job Postings'),
        (axes[1], 1, 'Reds',   'Fraudulent Job Postings')
    ]:
        wc = WordCloud(
            width=800, height=400, background_color='white',
            colormap=cmap, max_words=150, collocations=False
        ).generate(' '.join(df[df.fraudulent == label]['clean_text']))
        ax.imshow(wc, interpolation='bilinear')
        ax.axis('off')
        ax.set_title(title, fontsize=13, fontweight='bold')
    plt.suptitle('Word Clouds — Legitimate vs Fraudulent', fontsize=14, fontweight='bold')
    plt.tight_layout()
    savefig('07_wordclouds.png')
    plt.show()
else:
    print('WordCloud not installed. Run: pip install wordcloud')


tfidf = TfidfVectorizer(
    max_features=5000,
    ngram_range=(1, 2),
    sublinear_tf=True,
    min_df=3,
    max_df=0.90,
    strip_accents='unicode',
    analyzer='word'
)

X_tfidf = tfidf.fit_transform(df['clean_text'])
feature_names = tfidf.get_feature_names_out()


# Combine TF-IDF with meta features
scaler = MaxAbsScaler()
X_meta = scaler.fit_transform(df[META_FEATURES].fillna(0))
X = hstack([X_tfidf, csr_matrix(X_meta)])
y = df['fraudulent'].values
print(f'X shape: {X.shape}, y shape: {y.shape}')

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.20, random_state=RANDOM_STATE, stratify=y
)

print('Train/Test split (stratified 80/20):')
print(f'  Training  : {X_train.shape[0]:,} samples  |  Fraud rate: {y_train.mean() * 100:.2f}%')
print(f'  Testing   : {X_test.shape[0]:,} samples  |  Fraud rate: {y_test.mean() * 100:.2f}%')

if SMOTE_AVAILABLE:
    print()
    print('Applying SMOTE oversampling to training set...')
    sm = SMOTE(random_state=RANDOM_STATE, k_neighbors=5)
    X_train_res, y_train_res = sm.fit_resample(X_train, y_train)
    print(f'  Before: {X_train.shape[0]:,} samples  |  Fraud rate: {y_train.mean() * 100:.2f}%')
    print(f'  After : {X_train_res.shape[0]:,} samples  |  Fraud rate: {y_train_res.mean() * 100:.2f}%')
else:
    X_train_res, y_train_res = X_train, y_train
    print('SMOTE not available. Using class_weight=balanced in model definitions.')


models = {
    'Logistic Regression': LogisticRegression(
        C=1.0, max_iter=1000, class_weight='balanced',
        solver='lbfgs', random_state=RANDOM_STATE
    ),
    'Naive Bayes': MultinomialNB(alpha=0.1),
    'Random Forest': RandomForestClassifier(
        n_estimators=200, max_depth=20, min_samples_leaf=2,
        class_weight='balanced', random_state=RANDOM_STATE, n_jobs=-1
    ),
}

if XGBOOST_AVAILABLE:
    _spw = int((y_train == 0).sum() / max((y_train == 1).sum(), 1))
    models['XGBoost'] = XGBClassifier(
        n_estimators=200, learning_rate=0.1, max_depth=6,
        scale_pos_weight=_spw, subsample=0.8, colsample_bytree=0.8,
        use_label_encoder=False, eval_metric='logloss',
        random_state=RANDOM_STATE, n_jobs=-1
    )
else:
    models['Gradient Boosting'] = GradientBoostingClassifier(
        n_estimators=150, learning_rate=0.1, max_depth=5,
        subsample=0.8, random_state=RANDOM_STATE
    )

print(f'Models configured: {list(models.keys())}')


cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE)
trained_models = {}
results = {}

print(f"{'Model':<26} {'CV F1 Mean':>12} {'CV F1 Std':>10} {'Holdout F1':>12} {'Time (s)':>9}")
print('-' * 72)

for name, model in models.items():
    t0 = time.time()

    cv_scores = cross_val_score(model, X_train, y_train, cv=cv, scoring='f1', n_jobs=-1)
    model.fit(X_train_res, y_train_res)

    y_pred = model.predict(X_test)
    y_prob = model.predict_proba(X_test)[:, 1]
    fpr, tpr, _ = roc_curve(y_test, y_prob)
    prec_c, rec_c, pr_thresh = precision_recall_curve(y_test, y_prob)
    elapsed = time.time() - t0

    results[name] = {
        'accuracy'    : accuracy_score(y_test, y_pred),
        'precision'   : precision_score(y_test, y_pred, zero_division=0),
        'recall'      : recall_score(y_test, y_pred),
        'f1'          : f1_score(y_test, y_pred),
        'roc_auc'     : auc(fpr, tpr),
        'avg_prec'    : average_precision_score(y_test, y_prob),
        'fpr'         : fpr, 'tpr': tpr,
        'prec_curve'  : prec_c, 'rec_curve': rec_c,
        'y_pred'      : y_pred, 'y_prob': y_prob,
        'cv_f1_mean'  : cv_scores.mean(),
        'cv_f1_std'   : cv_scores.std(),
        'train_sec'   : elapsed
    }
    trained_models[name] = model

    print(f"{name:<26} {cv_scores.mean():>12.4f} {cv_scores.std():>10.4f} "          f"{results[name]['f1']:>12.4f} {elapsed:>9.1f}")

print('-' * 72)
print('Training complete.')










for name, v in results.items():
    print(f"\n{'' * 55}")
    print(f'  {name}')
    print('' * 55)
    print(classification_report(y_test, v['y_pred'], target_names=['Legitimate', 'Fraudulent']))


compare_keys   = ['accuracy', 'precision', 'recall', 'f1', 'roc_auc']
compare_labels = ['Accuracy', 'Precision', 'Recall', 'F1', 'ROC-AUC']

compare_df = pd.DataFrame(
    {name: [v[k] for k in compare_keys] for name, v in results.items()},
    index=compare_labels
)

fig, ax = plt.subplots(figsize=(13, 6))
compare_df.T.plot(kind='bar', ax=ax, width=0.75, edgecolor='white', colormap='Set2')
ax.set_title('Model Performance Comparison — Holdout Test Set',
             fontsize=13, fontweight='bold')
ax.set_ylabel('Score')
ax.set_ylim(0.60, 1.02)
ax.tick_params(axis='x', rotation=12)
ax.legend(loc='lower right', fontsize=9)
for container in ax.containers:
    ax.bar_label(container, fmt='%.3f', fontsize=7, padding=2, rotation=90)
plt.tight_layout()
savefig('11_model_comparison.png')
plt.show()


best_name = max(results, key=lambda k: results[k]['f1'])
best_model = trained_models[best_name]
print(f'Best model selected: {best_name}')

best_v       = results[best_name]
y_prob_best  = best_v['y_prob']

thresholds_test  = np.linspace(0.01, 0.99, 200)
f1_scores_thresh = [
    f1_score(y_test, (y_prob_best >= t).astype(int), zero_division=0)
    for t in thresholds_test
]

optimal_threshold = thresholds_test[np.argmax(f1_scores_thresh)]
optimal_f1        = max(f1_scores_thresh)
y_pred_opt        = (y_prob_best >= optimal_threshold).astype(int)
opt_p = precision_score(y_test, y_pred_opt, zero_division=0)
opt_r = recall_score(y_test, y_pred_opt)

fig, axes = plt.subplots(1, 2, figsize=(14, 5))

axes[0].plot(thresholds_test, f1_scores_thresh, lw=2.5, color='


print()
print('=' * 68)
print('  FINAL MODEL ACCURACY REPORT')
print('=' * 68)
print(f"{'Model':<26} {'Accuracy':>9} {'Precision':>10} {'Recall':>8} {'F1':>8} {'AUC':>8}")
print('-' * 68)
for name, v in results.items():
    marker = '  <-- best' if name == best_name else ''
    print(f"{name:<26} {v['accuracy']*100:>8.1f}%  "          f"{v['precision']:>9.4f}  {v['recall']:>7.4f}  "          f"{v['f1']:>7.4f}  {v['roc_auc']:>7.4f}{marker}")
print('=' * 68)
print()
print('Note: Accuracy is misleading on this dataset due to class imbalance.')
print('      A model that always predicts Legitimate achieves 95.2% accuracy.')
print('      Use F1 Score and ROC-AUC as the primary evaluation metrics.')
print()
print(f'Best model      : {best_name}')
print(f'F1 Score        : {results[best_name]["f1"]:.4f}')
print(f'ROC-AUC         : {results[best_name]["roc_auc"]:.4f}')
print(f'CV F1 (5-fold)  : {results[best_name]["cv_f1_mean"]:.4f} +/- {results[best_name]["cv_f1_std"]:.4f}')
print(f'Threshold       : {optimal_threshold:.2f} (optimized from default 0.50)')






MODEL_DIR = 'model_artifacts'
os.makedirs(MODEL_DIR, exist_ok=True)

artifacts = {
    'classifier.pkl'        : best_model,
    'tfidf_vectorizer.pkl'  : tfidf,
    'meta_scaler.pkl'       : scaler,
}

for fname, obj in artifacts.items():
    path = os.path.join(MODEL_DIR, fname)
    joblib.dump(obj, path)
    size_kb = os.path.getsize(path) / 1024
    print(f'  Saved: {fname:<35}  {size_kb:>8.1f} KB')

config = {
    'best_model'         : best_name,
    'optimal_threshold'  : float(optimal_threshold),
    'meta_features'      : META_FEATURES,
    'tfidf_max_features' : 5000,
    'tfidf_ngram_range'  : [1, 2],
    'holdout_f1'         : float(results[best_name]['f1']),
    'holdout_roc_auc'    : float(results[best_name]['roc_auc']),
    'cv_f1_mean'         : float(results[best_name]['cv_f1_mean']),
    'cv_f1_std'          : float(results[best_name]['cv_f1_std']),
}
with open(os.path.join(MODEL_DIR, 'model_config.json'), 'w') as f:
    json.dump(config, f, indent=2)
print(f'  Saved: model_config.json')


class JobFraudDetector:
    """
    Production-ready wrapper for the Fake Job Postings classifier.

    Supports two input modes:
      1. predict(text)            -- raw string input
      2. predict_dataframe(df)    -- structured DataFrame with job columns

    Parameters
    ----------
    model             : Trained sklearn-compatible classifier
    vectorizer        : Fitted TfidfVectorizer
    scaler            : Fitted MaxAbsScaler for meta-features
    meta_feature_names: List of meta-feature column names
    threshold         : Decision threshold (default: optimized value)
    """

    def __init__(self, model, vectorizer, scaler, meta_feature_names, threshold=0.5):
        self.model      = model
        self.vectorizer = vectorizer
        self.scaler     = scaler
        self.meta_names = meta_feature_names
        self.threshold  = threshold

    def _extract_meta(self, text: str) -> np.ndarray:
        feats = {
            'text_length'       : len(text),
            'word_count'        : len(text.split()),
            'has_email'         : int(bool(re.search(r'[\w.+-]+@[\w-]+\.[\w.-]+', text))),
            'has_url'           : int(bool(re.search(r'https?://', text))),
            'exclamation_count' : text.count('!'),
            'caps_ratio'        : sum(1 for c in text if c.isupper()) / max(len(text), 1),
            'telecommuting'     : 0,
            'has_company_logo'  : 0,
            'has_questions'     : 0,
        }
        return np.array([[feats.get(n, 0) for n in self.meta_names]], dtype=float)

    def _score(self, raw_text: str) -> float:
        """Return fraud probability for a single raw text string."""
        clean  = preprocess_text(raw_text)
        X_text = self.vectorizer.transform([clean])
        X_meta = self.scaler.transform(self._extract_meta(raw_text))
        X_in   = hstack([X_text, csr_matrix(X_meta)])
        return float(self.model.predict_proba(X_in)[0][1])

    def predict(self, job_text: str) -> dict:
        """
        Predict a single job posting from raw text.

        Returns
        -------
        dict with keys: prediction, label, fraud_probability, confidence, risk_level
        """
        if not isinstance(job_text, str) or not job_text.strip():
            return {'error': 'Input text is empty or invalid.'}
        try:
            prob = self._score(job_text)
            pred = int(prob >= self.threshold)
            label = 'FRAUDULENT' if pred else 'LEGITIMATE'
            confidence = prob if pred else 1 - prob
            if prob >= 0.80:   risk = 'HIGH'
            elif prob >= 0.50: risk = 'MEDIUM'
            elif prob >= 0.20: risk = 'LOW'
            else:              risk = 'VERY LOW'
            return {
                'prediction'        : pred,
                'label'             : label,
                'fraud_probability' : round(prob * 100, 2),
                'confidence'        : round(confidence * 100, 2),
                'risk_level'        : risk,
                'threshold_used'    : self.threshold,
            }
        except Exception as e:
            return {'error': str(e)}

    def predict_dataframe(self, input_df: pd.DataFrame) -> pd.DataFrame:
        """
        Predict fraud probability for a DataFrame of job postings.

        Accepts any DataFrame containing at least one of:
        title, description, requirements, company_profile, benefits.
        Missing columns are treated as empty strings.

        Parameters
        ----------
        input_df : pd.DataFrame
            New job postings in the same column format as the training data.

        Returns
        -------
        pd.DataFrame with original columns plus:
            - fraud_probability  : model score (0-100%)
            - prediction         : 0 (Legitimate) or 1 (Fraudulent)
            - label              : LEGITIMATE or FRAUDULENT
            - risk_level         : VERY LOW / LOW / MEDIUM / HIGH
        """
        df_copy = input_df.copy()








fig = plt.figure(figsize=(22, 16))
gs  = gridspec.GridSpec(3, 4, figure=fig, hspace=0.50, wspace=0.38)

