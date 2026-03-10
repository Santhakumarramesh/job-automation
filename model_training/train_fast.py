import pandas as pd
import numpy as np
import re
import os
import ssl

try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError:
    pass
else:
    ssl._create_default_https_context = _create_unverified_https_context
import re
import os
import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import MaxAbsScaler
from scipy.sparse import hstack, csr_matrix

try:
    from nltk.tokenize import word_tokenize
    from nltk.corpus import stopwords
    from nltk.stem import WordNetLemmatizer
    import nltk
    nltk.download('punkt', quiet=True)
    nltk.download('punkt_tab', quiet=True)
    nltk.download('stopwords', quiet=True)
    nltk.download('wordnet', quiet=True)
    USE_NLTK = True
except:
    USE_NLTK = False

print("Loading dataset...")
df = pd.read_csv('model_training/jobguard-dataset.csv')

def preprocess_text(text):
    if not isinstance(text, str) or not text.strip():
        return 'empty'
    text = str(text).lower().strip()
    text = re.sub(r'https?://\S+|www\.\S+', '', text)
    text = re.sub(r'[\w.+-]+@[\w-]+\.[\w.-]+', '', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'[^a-z\s]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    if USE_NLTK:
        words = word_tokenize(text)
        stop = set(stopwords.words('english'))
        words = [w for w in words if w not in stop and len(w) > 1]
        lemmatizer = WordNetLemmatizer()
        words = [lemmatizer.lemmatize(w) for w in words]
        return ' '.join(words) if words else 'empty'
    return text

print("Combining text...")
df['text_data'] = (
    df['title'].fillna('') + ' ' +
    df['company_profile'].fillna('') + ' ' +
    df['description'].fillna('') + ' ' +
    df['requirements'].fillna('') + ' ' +
    df['benefits'].fillna('')
).str.strip().str.replace(r'\s+', ' ', regex=True)

print("Extracting meta features...")
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

print("Preprocessing text...")
df['clean_text'] = df['text_data'].apply(preprocess_text)

print("Vectorizing...")
tfidf = TfidfVectorizer(max_features=5000, ngram_range=(1, 2), min_df=3, max_df=0.90)
X_tfidf = tfidf.fit_transform(df['clean_text'])

scaler = MaxAbsScaler()
X_meta = scaler.fit_transform(df[META_FEATURES].fillna(0))
X = hstack([X_tfidf, csr_matrix(X_meta)])
y = df['fraudulent'].values

print(f"Training Logistic Regression on {X.shape[0]} samples...")
model = LogisticRegression(C=1.0, max_iter=1000, class_weight='balanced', solver='lbfgs', random_state=42)
model.fit(X, y)

os.makedirs('model_artifacts', exist_ok=True)
joblib.dump(model, 'model_artifacts/classifier.pkl')
joblib.dump(tfidf, 'model_artifacts/tfidf_vectorizer.pkl')
joblib.dump(scaler, 'model_artifacts/meta_scaler.pkl')

import json
json.dump({'meta_features': META_FEATURES, 'threshold': 0.5}, open('model_artifacts/model_config.json', 'w'))
print("Saved artifacts to model_artifacts/")
