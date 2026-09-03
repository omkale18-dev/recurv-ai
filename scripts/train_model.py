"""
Convenience CLI script to train the recovery classifier model.

Usage:
    python scripts/train_model.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.ml.train import train_and_evaluate

if __name__ == "__main__":
    train_and_evaluate()
