"""
Fetch additional job fraud datasets to merge for training.
Requires: pip install kaggle
Setup: Place kaggle.json in ~/.kaggle/ (from Kaggle API)
"""
import os
import shutil
import subprocess
import sys

KAGGLE_DATASETS = [
    "shivamb/real-or-fake-fake-jobposting-prediction",  # Original large dataset
    "subhajournal/fraudulent-job-posting",
]

def run(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

def main():
    out_dir = os.path.join(os.path.dirname(__file__), "extra_data")
    os.makedirs(out_dir, exist_ok=True)

    if run("kaggle --version").returncode != 0:
        print("Install Kaggle CLI: pip install kaggle")
        print("Then add ~/.kaggle/kaggle.json with your API credentials")
        sys.exit(1)

    for ds in KAGGLE_DATASETS:
        print(f"Downloading {ds}...")
        r = run(f"kaggle datasets download -d {ds} -p {out_dir} --unzip")
        if r.returncode != 0:
            print(f"  Failed: {r.stderr or r.stdout}")
        else:
            print(f"  OK -> {out_dir}")

    print("\nMerge CSVs manually or add paths to train_enhanced.py --data")
    print("Example: python model_training/train_enhanced.py --data model_training/jobguard-dataset.csv extra_data/*.csv")


if __name__ == "__main__":
    main()
