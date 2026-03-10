# Job Guard Model Training

Train the fraud detection model with more data for higher accuracy.

## Quick Start (Enhanced Training)

```bash
# From project root
python model_training/train_enhanced.py
```

This uses:
- **Data augmentation**: +500 synthetic fraudulent samples (mix-up)
- **Threshold tuning**: Optimizes F1 score
- **Evaluation**: Precision, recall, F1, ROC-AUC

## Options

```bash
# More augmentation (1000 extra fraud samples)
python model_training/train_enhanced.py --augment 1000

# Use Random Forest instead of Logistic Regression
python model_training/train_enhanced.py --model random_forest

# Grid search for best hyperparameters (slower)
python model_training/train_enhanced.py --tune

# Load multiple datasets
python model_training/train_enhanced.py --data model_training/jobguard-dataset.csv extra_data/fake_job_postings.csv

# Disable augmentation
python model_training/train_enhanced.py --augment 0
```

## Adding More Data

### Option 1: Kaggle

1. Install: `pip install kaggle`
2. Add `~/.kaggle/kaggle.json` (from Kaggle → Account → API)
3. Run: `python model_training/fetch_more_data.py`
4. Merge CSVs and add to `--data`

### Option 2: Manual CSV

Add a CSV with columns: `title`, `company_profile`, `description`, `requirements`, `benefits`, `fraudulent` (0/1), plus optional: `telecommuting`, `has_company_logo`, `has_questions`.

### Option 3: Same schema

Any CSV matching the `jobguard-dataset.csv` schema can be passed to `--data`.

## Output

- `model_artifacts/classifier.pkl`
- `model_artifacts/tfidf_vectorizer.pkl`
- `model_artifacts/meta_scaler.pkl`
- `model_artifacts/model_config.json` (includes tuned threshold)

The Job Guard in `agents/job_guard.py` loads these automatically.

## Original Script

`train_fast.py` – minimal training, no augmentation or tuning. Use for quick iterations.
