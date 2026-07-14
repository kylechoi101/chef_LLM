"""Download the Food.com dump. Needs ~/.kaggle/kaggle.json (kaggle.com → Account → Create API Token)."""
import subprocess
import sys
from pathlib import Path

RAW = Path(__file__).resolve().parent.parent / "data" / "raw"
DATASET = "shuyangli94/food-com-recipes-and-user-interactions"

if __name__ == "__main__":
    RAW.mkdir(parents=True, exist_ok=True)
    if not (Path.home() / ".kaggle" / "kaggle.json").exists():
        sys.exit("Missing ~/.kaggle/kaggle.json — create an API token at kaggle.com/settings, then rerun.")
    subprocess.run(
        ["uvx", "--from", "kaggle", "kaggle", "datasets", "download", DATASET,
         "-p", str(RAW), "--unzip"],
        check=True,
    )
    print("done:", sorted(p.name for p in RAW.iterdir()))
