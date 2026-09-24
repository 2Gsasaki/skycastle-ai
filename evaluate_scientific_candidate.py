#!/usr/bin/env python3
"""夜間の気象条件を使う新AI候補と従来AIを、同じ最終期間で比較する。"""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score


DATA_PATH = Path("data/analysis/daily_history_2017_2026.csv")
FOG_MODEL = Path("model/skycastle_fog.pkl")
CASTLE_MODEL = Path("model/skycastle_castle.pkl")
CALIBRATOR = Path("model/skycastle_event_calibrator.pkl")

TRAIN_END = pd.Timestamp("2024-08-31")
TUNE_START = pd.Timestamp("2024-09-01")
TUNE_END = pd.Timestamp("2025-08-31")
TEST_START = pd.Timestamp("2025-09-01")
TEST_END = pd.Timestamp("2026-09-17")

SCIENTIFIC_FEATURES = [
    "prev_18_23_rain_sum",
    "rain_00_01_sum",
    "min_temp_02_04",
    "temp_drop_to_04",
    "humidity_05_06_mean",
    "wind_05_06_mean",
    "cloud_05_06_mean",
    "rain_05_06_sum",
    "dew_spread_05_06",
    "cloud_06_08_mean",
    "rain_06_08_sum",
    "wind_06_08_mean",
    "hours_since_rain_at_06",
    "month",
    "day_of_year_sin",
    "day_of_year_cos",
]
OLD_FEATURES = [
    "temp", "humidity", "wind", "cloud", "rain",
    "prev_temp", "prev_humidity", "prev_wind", "prev_cloud", "prev_rain",
    "temp_prev_diff",
]


def load_frame() -> pd.DataFrame:
    frame = pd.read_csv(DATA_PATH)
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame = frame.dropna(subset=["date", "castle_visible", *SCIENTIFIC_FEATURES]).copy()
    return frame.sort_values("date").drop_duplicates("date", keep="last")


def old_feature_frame(frame: pd.DataFrame) -> pd.DataFrame:
    result = pd.DataFrame(index=frame.index)
    mapping = {
        "temp": "temp_05_08_mean",
        "humidity": "humidity_05_08_mean",
        "wind": "wind_05_08_mean",
        "cloud": "cloud_05_08_mean",
        "rain": "rain_05_08_mean",
    }
    for target, source in mapping.items():
        result[target] = frame[source].astype(float)
        result[f"prev_{target}"] = result[target].shift(1)
    continuous = frame["date"].diff().dt.days.eq(1)
    for column in ["prev_temp", "prev_humidity", "prev_wind", "prev_cloud", "prev_rain"]:
        result.loc[~continuous, column] = np.nan
    result["temp_prev_diff"] = result["prev_temp"] - result["temp"]
    return result[OLD_FEATURES]


def old_probability(features: pd.DataFrame) -> np.ndarray:
    fog_model = joblib.load(FOG_MODEL)
    castle_model = joblib.load(CASTLE_MODEL)
    fog = fog_model.predict_proba(features)[:, 1]
    castle = castle_model.predict_proba(features)[:, 1]
    payload = joblib.load(CALIBRATOR)
    calibrator = payload.get("model") if isinstance(payload, dict) else payload
    calibration_features = pd.DataFrame(
        {"fog_probability": fog, "castle_probability": castle, "fog_castle_product": fog * castle}
    )
    return calibrator.predict_proba(calibration_features)[:, 1]


def new_model() -> lgb.LGBMClassifier:
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
        "brier": float(brier_score_loss(actual, probability)),
        "ap": float(average_precision_score(actual, probability)),
        "auc": float(roc_auc_score(actual, probability)),
        "max_probability": float(probability.max()),
    }
    for count in (5, 10, 15):
        top = np.argsort(probability)[-count:]
        result[f"top_{count}"] = int(actual.iloc[top].sum())
    return result


def print_summary(result: dict) -> None:
    print(
        f"{result['name']}: Brier={result['brier']:.4f} / AP={result['ap']:.3f} / "
        f"AUC={result['auc']:.3f} / 最大={result['max_probability']:.1%}"
    )
    print(
        f"  上位5日={result['top_5']}/5、上位10日={result['top_10']}/10、"
        f"上位15日={result['top_15']}/15"
    )


def main() -> None:
    frame = load_frame()
    train = frame[frame["date"] <= TRAIN_END]
    tune = frame[frame["date"].between(TUNE_START, TUNE_END)]
    test = frame[frame["date"].between(TEST_START, TEST_END)]
    print(
        f"学習 {len(train)}日・出現{int(train.castle_visible.sum())}日 / "
        f"調整 {len(tune)}日・出現{int(tune.castle_visible.sum())}日 / "
        f"最終検証 {len(test)}日・出現{int(test.castle_visible.sum())}日"
    )

    candidate = new_model()
    candidate.fit(train[SCIENTIFIC_FEATURES], train["castle_visible"])
    candidate_tune = candidate.predict_proba(tune[SCIENTIFIC_FEATURES])[:, 1]
    candidate_test = candidate.predict_proba(test[SCIENTIFIC_FEATURES])[:, 1]
    old_test = old_probability(old_feature_frame(frame).loc[test.index])

    print("\n調整期間（基準を決めず、過学習がないかを見る参考）")
    print_summary(summary("新AI候補", candidate_tune, tune["castle_visible"]))
    print("\n最終検証（2025年9月以降。学習には未使用）")
    old_result = summary("従来AI", old_test, test["castle_visible"])
    candidate_result = summary("新AI候補", candidate_test, test["castle_visible"])
    print_summary(old_result)
    print_summary(candidate_result)
    winner = "新AI候補" if candidate_result["ap"] > old_result["ap"] else "従来AI"
    print(f"\n順位付け指標APでの優位: {winner}")
    print(json.dumps({"old": old_result, "candidate": candidate_result}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
