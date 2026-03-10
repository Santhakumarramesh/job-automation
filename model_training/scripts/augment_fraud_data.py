#!/usr/bin/env python3
"""
Augment minority class (fraud) with synonym/variant replacements.
Increases fraud samples for more robust training.
"""
import os
import sys
import random
import pandas as pd

# Fraud phrase variants — creates diverse but realistic fraud samples
FRAUD_SYNONYMS = {
    'bank account': ['bank details', 'bank information', 'account number', 'banking info'],
    'bank details': ['bank account', 'account details', 'banking information'],
    'registration fee': ['application fee', 'processing fee', 'admin fee', 'setup fee'],
    'application fee': ['registration fee', 'processing fee', 'admin fee'],
    'ssn': ['social security number', 'social security', 'SSN'],
    'wire transfer': ['bank transfer', 'money transfer', 'electronic transfer'],
    'act now': ['apply now', 'limited time', 'hurry', 'don\'t wait'],
    'no experience': ['no experience needed', 'no experience required', 'entry level'],
    'guaranteed': ['guarantee', 'assured', 'certain'],
    'earn': ['make', 'get', 'receive'],
    'work from home': ['work at home', 'remote work', 'WFH', 'home based'],
    'urgent': ['immediate', 'asap', 'right away'],
}

def augment_text(text, n_variants=1):
    """Create augmented variants by replacing fraud phrases."""
    if not isinstance(text, str) or len(text) < 50:
        return []
    
    results = []
    text_lower = text.lower()
    
    for _ in range(n_variants):
        new_text = text
        for phrase, replacements in FRAUD_SYNONYMS.items():
            if phrase in text_lower and random.random() < 0.5:
                rep = random.choice(replacements)
                # Case-insensitive replace
                idx = text_lower.find(phrase)
                if idx >= 0:
                    new_text = new_text[:idx] + rep + new_text[idx+len(phrase):]
                    text_lower = new_text.lower()
        if new_text != text:
            results.append(new_text)
    
    return results[:n_variants]

def main():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    paths = [
        os.path.join(base, 'data', 'jobguard-combined.csv'),
        os.path.join(base, 'jobguard-dataset.csv'),
    ]
    
    for p in paths:
        if os.path.exists(p):
            df = pd.read_csv(p)
            break
    else:
        print("Dataset not found")
        sys.exit(1)
    
    fraud_df = df[df['fraudulent'] == 1].copy()
    legit_count = (df['fraudulent'] == 0).sum()
    
    # Target: 2x fraud samples (or 20% of legit, whichever is smaller)
    target_fraud = min(len(fraud_df) * 2, int(legit_count * 0.2))
    to_add = target_fraud - len(fraud_df)
    
    if to_add <= 0:
        print("Fraud samples sufficient. No augmentation needed.")
        sys.exit(0)
    
    augmented = []
    random.seed(42)
    
    while len(augmented) < to_add:
        row = fraud_df.sample(1).iloc[0]
        text = ' '.join(str(row.get(c, '')) for c in ['title', 'company_profile', 'description', 'requirements', 'benefits'])
        variants = augment_text(text, n_variants=1)
        if variants:
            new_row = row.to_dict()
            # Put augmented text into description (main content field)
            new_row['description'] = variants[0][:10000]
            augmented.append(new_row)
    
    new_df = pd.DataFrame(augmented[:to_add])
    combined = pd.concat([df, new_df], ignore_index=True)
    
    out_path = os.path.join(base, 'data', 'jobguard-augmented.csv')
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    combined.to_csv(out_path, index=False)
    
    print(f"Augmented: {len(fraud_df):,} → {len(fraud_df) + len(augmented):,} fraud samples")
    print(f"Total: {len(combined):,} rows, fraud rate {combined.fraudulent.mean()*100:.1f}%")
    print(f"Saved: {out_path}")

if __name__ == '__main__':
    main()
