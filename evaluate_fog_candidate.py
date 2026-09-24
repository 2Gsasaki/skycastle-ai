#!/usr/bin/env python3
"""夜間条件を使う雲海・霧AI候補を、従来の雲海AIと比較する。"""

from __future__ import annotations

from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

import evaluate_scientific_candidate as castle


HISTORY_PATH = Path("data/history.csv")
FOG_MODEL_PATH = Path("model/skycastle_fog.pkl")
TRAIN_END = pd.Timestamp("2024-08-31")
TUNE_START = pd.Timestamp("2024-09-01")
TUNE_END = pd.Timestamp("2025-08-31")
TEST_START = pd.Timestamp("2025-09-01")
TEST_END = pd.Timestamp("2026-09-18")


def load_frame() -> pd.DataFrame:
    weather = castle.load_frame()
    labels = pd.read_csv(HISTORY_PATH, usecols=["date", "fog_observed"])
    labels["date"] = pd.to_datetime(labels["date"], errors="coerce")
    labels["fog_observed"] = pd.to_numeric(labels["fog_observed"], errors="coerce")
    labels = labels.dropna(subset=["date", "fog_observed"])
    labels = labels.sort_values("date").drop_duplicates("date", keep="last")
    frame = weather.merge(labels, on="date", how="inner")
    return frame.sort_values("date")


def old_features(frame: pd.DataFrame) -> pd.DataFrame:
    return castle.old_feature_frame(frame)


def candidate_model() -> lgb.LGBMClassifier:
    return lgb.LGBMClassifier(
        objective="binary",
        n_estimators=180,
        num_leaves=15,
        learning_rate=0.025,
        min_child_samples=20,
        reg_lambda=3.0,
        random_state=42,
        verbosity=-1,
    )


def summary(name: str, probability: np.ndarray, actual: pd.Series) -> dict:
    probability = np.asarray(probability)
    actual = actual.astype(int)
    result = {
        "name": name,
        "brier": brier_score_loss(actual, probability),
        "ap": average_precision_score(actual, probability),
        "auc": roc_auc_score(actual, probability),
        "max": probability.max(),
    }
    for threshold in (0.5, 0.7, 0.9):
        selected = probability >= threshold
        count = int(selected.sum())
        result[f"{threshold:.1f}_count"] = count
        result[f"{threshold:.1f}_hits"] = int(actual.iloc[np.flatnonzero(selected)].sum()) if count else 0
    return result


def print_summary(result: dict) -> None:
    print(
        f"{result['name']}: Brier={result['brier']:.4f} / AP={result['ap']:.3f} / "
        f"AUC={result['auc']:.3f} / 最大={result['max']:.1%}"
    )
    for threshold in (0.5, 0.7, 0.9):
        count = result[f"{threshold:.1f}_count"]
        hits = result[f"{threshold:.1f}_hits"]
        print(f"  {threshold:.0%}以上: {hits}/{count}" if count else f"  {threshold:.0%}以上: なし")


def main() -> None:
    frame = load_frame()
    train = frame[frame.date <= TRAIN_END]
    tune = frame[frame.date.between(TUNE_START, TUNE_END)]
    test = frame[frame.date.between(TEST_START, TEST_END)]
    print(
        f"利用可能 {len(frame)}日・霧{int(frame.fog_observed.sum())}日 / "
        f"学習 {len(train)}日・霧{int(train.fog_observed.sum())}日 / "
        f"調整 {len(tune)}日・霧{int(tune.fog_observed.sum())}日 / "
        f"最終検証 {len(test)}日・霧{int(test.fog_observed.sum())}日"
    )
    candidate = candidate_model()
    candidate.fit(train[castle.SCIENTIFIC_FEATURES], train.fog_observed)
    candidate_test = candidate.predict_proba(test[castle.SCIENTIFIC_FEATURES])[:, 1]
    old = joblib.load(FOG_MODEL_PATH)
    old_test = old.predict_proba(old_features(frame).loc[test.index])[:, 1]
    print("\n最終検証（2025年9月以降。学習には未使用）")
    old_result = summary("従来の雲海AI", old_test, test.fog_observed)
    candidate_result = summary("夜間条件付き雲海AI候補", candidate_test, test.fog_observed)
    print_summary(old_result)
    print_summary(candidate_result)
    print("\n湿度70%未満で高確率となった件数")
    for name, probability in (("従来", old_test), ("候補", candidate_test)):
        selected = (test.humidity_05_06_mean < 70) & (probability >= 0.7)
        print(f"  {name}: {int(selected.sum())}件")


if __name__ == "__main__":
    main()
