"""
Retraining script for the transaction categoriser.
Reads labeled rows from state.db, combines with synthetic + OSM data,
trains TF-IDF + Logistic Regression, saves categorizer.pkl.
"""
import json
import logging
import os
import sqlite3
from pathlib import Path
from typing import Dict, List

import joblib
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import LabelEncoder
from sklearn.feature_extraction.text import TfidfVectorizer

log = logging.getLogger(__name__)

DB_PATH        = Path(os.getenv("DB_PATH",       "/data/state.db"))
MODEL_PATH     = Path(os.getenv("MODEL_PATH",    "/models/categorizer.pkl"))
OSM_PATH       = Path(__file__).parent / "osm_merchants.json"

ANCHOR_REPEATS      = 5   # OSM well-known brands — high weight
MERCHANT_REPEATS    = 1   # OSM broad coverage — standard weight
DB_LOCKED_REPEATS   = 5   # manually confirmed by user — treated like anchors
DB_UNLOCKED_REPEATS = 1   # auto-categorized by rules/ML — standard weight


def load_db_rows() -> pd.DataFrame:
    if not DB_PATH.exists():
        log.warning("DB not found at %s — training on synthetic+OSM only", DB_PATH)
        return pd.DataFrame(columns=["merchant_upper", "category", "category_locked"])

    with sqlite3.connect(DB_PATH) as con:
        df = pd.read_sql_query(
            """
            SELECT UPPER(merchant) AS merchant_upper, category, category_locked
            FROM transactions
            WHERE category IS NOT NULL
              AND category NOT IN ('uncategorized')
              AND merchant IS NOT NULL
            """,
            con,
        )
    locked_count = df[df["category_locked"] == 1]["merchant_upper"].nunique()
    log.info("Loaded %d labeled rows from DB (%d unique merchants, %d locked)",
             len(df), df["merchant_upper"].nunique(), locked_count)
    return df


def load_osm() -> tuple:
    """Returns (anchors, merchants) — two-tier training data from osm_merchants.json."""
    if not OSM_PATH.exists():
        log.warning("osm_merchants.json not found at %s", OSM_PATH)
        return {}, {}
    with open(OSM_PATH, encoding="utf-8") as f:
        data = json.load(f)
    anchors   = data.pop("anchors", {})
    merchants = data
    anchor_count   = sum(len(v) for v in anchors.values())
    merchant_count = sum(len(v) for v in merchants.values())
    log.info("OSM anchors: %d names | merchants: %d names", anchor_count, merchant_count)
    return anchors, merchants


def build_augmented(db_df: pd.DataFrame, anchors: dict, merchants: dict) -> pd.DataFrame:
    rows = []

    # DB locked merchants (manually confirmed) — deduplicated, anchor-level weight
    # DB unlocked merchants (auto-categorized) — deduplicated, standard weight
    if not db_df.empty:
        locked_df   = db_df[db_df["category_locked"] == 1].drop_duplicates("merchant_upper")
        unlocked_df = db_df[db_df["category_locked"] == 0].drop_duplicates("merchant_upper")
        locked_set  = set(locked_df["merchant_upper"])
        unlocked_df = unlocked_df[~unlocked_df["merchant_upper"].isin(locked_set)]

        for _, r in locked_df.iterrows():
            for _ in range(DB_LOCKED_REPEATS):
                rows.append({"merchant_upper": r["merchant_upper"], "category": r["category"]})

        for _, r in unlocked_df.iterrows():
            for _ in range(DB_UNLOCKED_REPEATS):
                rows.append({"merchant_upper": r["merchant_upper"], "category": r["category"]})

        log.info("DB: %d locked merchants (×%d) + %d unlocked (×%d)",
                 len(locked_df), DB_LOCKED_REPEATS, len(unlocked_df), DB_UNLOCKED_REPEATS)

    # OSM anchors — well-known brands, high repeat weight
    for cat, names in anchors.items():
        for name in names:
            for _ in range(ANCHOR_REPEATS):
                rows.append({"merchant_upper": str(name).upper(), "category": cat})

    # OSM merchants — broad coverage, standard weight
    for cat, names in merchants.items():
        for name in names:
            for _ in range(MERCHANT_REPEATS):
                rows.append({"merchant_upper": str(name).upper(), "category": cat})

    combined = pd.DataFrame(rows)
    combined = combined.dropna(subset=["merchant_upper", "category"])
    combined = combined[combined["merchant_upper"].str.strip() != ""]
    return combined


def train(combined: pd.DataFrame) -> tuple:
    """
    Train on all data, evaluate with merchant-based split.
    Returns (pipeline, report_dict, accuracy).
    """
    # Merchant-based split so same merchant never appears in both train and test
    unique_merchants = combined["merchant_upper"].unique()
    train_m, test_m = train_test_split(unique_merchants, test_size=0.15, random_state=42)
    train_df = combined[combined["merchant_upper"].isin(train_m)]
    test_df  = combined[combined["merchant_upper"].isin(test_m)]

    model = Pipeline([
        ("tfidf", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), min_df=1)),
        ("lr",    LogisticRegression(max_iter=1000, class_weight="balanced", C=1.0)),
    ])
    model.fit(train_df["merchant_upper"], train_df["category"])

    preds = model.predict(test_df["merchant_upper"])
    report = classification_report(test_df["category"], preds, output_dict=True, zero_division=0)
    accuracy = report["accuracy"]

    log.info("Train rows: %d  Test rows: %d  Accuracy: %.1f%%",
             len(train_df), len(test_df), accuracy * 100)
    return model, report, accuracy


def retrain() -> dict:
    """Full retrain cycle. Returns stats dict."""
    db_df             = load_db_rows()
    anchors, merchants = load_osm()
    combined          = build_augmented(db_df, anchors, merchants)

    log.info("Combined training set: %d rows", len(combined))
    model, report, accuracy = train(combined)

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, MODEL_PATH)
    log.info("Model saved to %s", MODEL_PATH)

    per_class = {
        cat: {"precision": round(v["precision"], 3), "recall": round(v["recall"], 3), "f1": round(v["f1-score"], 3)}
        for cat, v in report.items()
        if isinstance(v, dict) and cat not in ("macro avg", "weighted avg")
    }

    locked_merchants = int(db_df[db_df["category_locked"] == 1]["merchant_upper"].nunique()) if not db_df.empty else 0

    return {
        "accuracy":          round(accuracy, 4),
        "db_rows":           len(db_df),
        "locked_merchants":  locked_merchants,
        "combined_rows":     len(combined),
        "categories":        per_class,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    stats = retrain()
    print(f"Accuracy: {stats['accuracy']:.1%}")
