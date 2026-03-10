# Train & Run – Accuracy & Testing

## Run All Tabs (Error Check)

```bash
cd "/Users/santhakumar/Desktop/resume ai agent "
source venv/bin/activate
python test_all_tabs.py
```

## LLM Model Configuration

| Component | Model | Temperature | Purpose |
|-----------|-------|-------------|---------|
| **ATS Scorer** | gpt-4o | 0.0 | Semantic ATS – deterministic |
| **Resume Editor** | gpt-4o | 0.7 | Tailoring – balanced |
| **Cover Letter** | gpt-4o | 0.7 | Generation |
| **Job Guard** | gpt-4o | 0.0 | Fraud detection |
| **Job Analyzer** | gpt-4o | 0.0 | JD extraction |
| **Project Generator** | gpt-4o | 0.8 | Creative ideas |
| **Interview Prep** | gpt-4o | 0.5 | Balanced |
| **Fast Scoring** (OpenClaw) | gpt-4o-mini | 0.0 | Lower cost |

Config file: `config/llm_config.json`

## Train JobGuard for More Accuracy

The JobGuard fraud-detection model (sklearn) was retrained with:

- **Augmentation**: 500 extra fraudulent samples
- **Grid search**: C=2.0, max_iter=1000
- **Threshold tuning**: 0.8 (F1-optimized)

### Results (after training)

| Metric | Value |
|--------|-------|
| Accuracy | 98.67% |
| Precision | 93.41% |
| Recall | 88.28% |
| F1 | 90.77% |
| ROC-AUC | 99.66% |

### Retrain

```bash
# Standard (recommended)
python model_training/train_enhanced.py --augment 500 --model logistic --tune

# With more augmentation
python model_training/train_enhanced.py --augment 1000 --model random_forest

# Multiple datasets
python model_training/train_enhanced.py --data model_training/jobguard-dataset.csv extra_data/*.csv
```

Artifacts are saved to `model_artifacts/`.

## Run the App

```bash
source venv/bin/activate
streamlit run app.py
```
