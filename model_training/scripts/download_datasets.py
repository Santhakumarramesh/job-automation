#!/usr/bin/env python3
"""
Download and merge multiple fake job posting datasets for robust model training.
Combines: Kaggle (primary) + Hugging Face balanced + optional sources.
"""
import os
import sys
import hashlib
import pandas as pd

# Add project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

OUTPUT_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'jobguard-combined.csv')
PRIMARY_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'jobguard-dataset.csv')

REQUIRED_COLUMNS = ['title', 'description', 'company_profile', 'requirements', 'benefits', 
                   'telecommuting', 'has_company_logo', 'has_questions', 'fraudulent']

def load_primary():
    """Load primary Kaggle dataset."""
    paths = [PRIMARY_PATH, 'jobguard-dataset.csv', 'data/jobguard-dataset.csv']
    for p in paths:
        if os.path.exists(p):
            df = pd.read_csv(p)
            df['_source'] = 'kaggle'
            return df
    return None

def load_huggingface():
    """Load Hugging Face datasets (balanced + full) and merge."""
    try:
        from datasets import load_dataset
    except ImportError:
        print("  Install: pip install datasets")
        return None
    
    dfs = []
    # Balanced dataset (50/50) - may have unique samples
    try:
        ds = load_dataset('gplsi/fake_job_postings_balanced_en', split='train')
        df = ds.to_pandas()
        df['_source'] = 'hf_balanced'
        dfs.append(df)
        print(f"  Loaded HuggingFace balanced: {len(df):,} rows")
    except Exception as e:
        print(f"  HF balanced load failed: {e}")
    
    # Full dataset (same as Kaggle) - for dedup check
    try:
        ds = load_dataset('victor/real-or-fake-fake-jobposting-prediction', split='train')
        df = ds.to_pandas()
        df['_source'] = 'hf_full'
        dfs.append(df)
        print(f"  Loaded HuggingFace full: {len(df):,} rows")
    except Exception as e:
        print(f"  HF full load failed: {e}")
    
    return pd.concat(dfs, ignore_index=True) if dfs else None

def normalize_columns(df):
    """Ensure consistent column names and types."""
    # Map common variations
    col_map = {
        'company_profile': 'company_profile',
        'Company Profile': 'company_profile',
        'job_description': 'description',
        'Job Description': 'description',
    }
    df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
    
    # Fill missing with empty
    for c in ['title', 'description', 'company_profile', 'requirements', 'benefits']:
        if c in df.columns:
            df[c] = df[c].fillna('').astype(str)
        else:
            df[c] = ''
    
    for c in ['telecommuting', 'has_company_logo', 'has_questions']:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0).astype(int)
        else:
            df[c] = 0
    
    if 'fraudulent' not in df.columns and 'fraud' in df.columns:
        df['fraudulent'] = df['fraud']
    df['fraudulent'] = pd.to_numeric(df['fraudulent'], errors='coerce').fillna(0).astype(int)
    return df

def text_hash(row):
    """Hash for deduplication."""
    t = '|'.join(str(row.get(c, '')) for c in ['title', 'description'])
    return hashlib.md5(t.encode()).hexdigest()

def merge_and_dedupe(primary_df, extra_df):
    """Merge datasets and remove duplicates."""
    if extra_df is None or len(extra_df) == 0:
        return primary_df
    
    # Normalize both
    primary_df = normalize_columns(primary_df.copy())
    extra_df = normalize_columns(extra_df.copy())
    
    # Align columns - use primary's schema
    use_cols = [c for c in primary_df.columns if not c.startswith('_')]
    extra_cols = [c for c in use_cols if c in extra_df.columns]
    missing = [c for c in use_cols if c not in extra_df.columns]
    for c in missing:
        extra_df[c] = '' if c in ['title','description','company_profile','requirements','benefits'] else 0
    
    # Dedupe by text hash
    primary_df = primary_df.copy()
    primary_df['_hash'] = primary_df.apply(text_hash, axis=1)
    extra_df['_hash'] = extra_df.apply(text_hash, axis=1)
    existing = set(primary_df['_hash'])
    
    new_rows = extra_df[~extra_df['_hash'].isin(existing)].copy()
    primary_df = primary_df.drop(columns=['_hash'])
    
    if len(new_rows) > 0:
        new_rows = new_rows[use_cols]
        combined = pd.concat([primary_df[use_cols], new_rows], ignore_index=True)
        print(f"  Added {len(new_rows):,} unique rows from extra sources")
        return combined
    return primary_df[use_cols]

def main():
    print("JobGuard — Dataset Download & Merge")
    print("=" * 50)
    
    primary = load_primary()
    if primary is None:
        print("ERROR: Primary dataset (jobguard-dataset.csv) not found.")
        print("Download from: https://www.kaggle.com/datasets/shivamb/real-or-fake-fake-jobposting-prediction")
        sys.exit(1)
    
    print(f"Primary (Kaggle): {len(primary):,} rows, fraud rate {primary.fraudulent.mean()*100:.1f}%")
    
    extra = load_huggingface()
    combined = merge_and_dedupe(primary, extra)
    
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    combined.to_csv(OUTPUT_PATH, index=False)
    
    print(f"\nCombined dataset: {len(combined):,} rows")
    print(f"  Legitimate: {(combined.fraudulent==0).sum():,}")
    print(f"  Fraudulent: {(combined.fraudulent==1).sum():,}")
    print(f"  Fraud rate: {combined.fraudulent.mean()*100:.1f}%")
    print(f"\nSaved to: {OUTPUT_PATH}")

if __name__ == '__main__':
    main()
