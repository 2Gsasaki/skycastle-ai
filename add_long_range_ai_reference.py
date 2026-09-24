#!/usr/bin/env python3
"""公開中の従来AIは変えず、新AIの比較用数値だけを14日予報へ加える。"""

from __future__ import annotations

import json
import math
from pathlib import Path

import lightgbm as lgb
import pandas as pd


HISTORY_PATH = Path("data/analysis/daily_history_2017_2026.csv")
FORECAST_PATH = Path("data/forecast_predictions.json")
FEATURES = [
    "temp_05_08_mean",
    "humidity_05_08_mean",
    "wind_05_08_mean",
    "cloud_05_08_mean",
    "rain_05_08_mean",
    "month",
    "day_of_year_sin",
    "day_of_year_cos",
]


def train_model() -> lgb.LGBMClassifier:
    frame = pd.read_csv(HISTORY_PATH, usecols=["castle_visible", *FEATURES])
    frame = frame.dropna(subset=["castle_visible", *FEATURES])
    model = lgb.LGBMClassifier(
        objective="binary",
        n_estimators=150,
        num_leaves=15,
        learning_rate=0.03,
        min_child_samples=20,
        reg_lambda=2.0,
        random_state=42,
        verbosity=-1,
    )
    model.fit(frame[FEATURES], frame["castle_visible"])
    return model


def forecast_features(predictions: list[dict]) -> pd.DataFrame:
    frame = pd.DataFrame(predictions)
    dates = pd.to_datetime(frame["date"], errors="raise")
    frame["temp_05_08_mean"] = pd.to_numeric(frame["temp"], errors="coerce")
    frame["humidity_05_08_mean"] = pd.to_numeric(frame["humidity"], errors="coerce")
    frame["wind_05_08_mean"] = pd.to_numeric(frame["wind"], errors="coerce")
    frame["cloud_05_08_mean"] = pd.to_numeric(frame["cloud"], errors="coerce")
    frame["rain_05_08_mean"] = pd.to_numeric(frame["rain"], errors="coerce")
    frame["month"] = dates.dt.month
    day_of_year = dates.dt.dayofyear
    frame["day_of_year_sin"] = day_of_year.map(lambda value: math.sin(2 * math.pi * value / 365.25))
    frame["day_of_year_cos"] = day_of_year.map(lambda value: math.cos(2 * math.pi * value / 365.25))
    if frame[FEATURES].isna().any().any():
        raise ValueError("新AIの入力に空欄があります。")
    return frame[FEATURES]


def main() -> None:
    with FORECAST_PATH.open("r", encoding="utf-8") as stream:
        payload = json.load(stream)
    predictions = payload if isinstance(payload, list) else payload.get("predictions", [])
    if not predictions:
        raise ValueError("予報データがありません。")
    probabilities = train_model().predict_proba(forecast_features(predictions))[:, 1]
    for prediction, probability in zip(predictions, probabilities):
        prediction["new_ai_reference_probability"] = round(float(probability), 4)
        prediction["new_ai_reference_label"] = "新AIモデル"
    with FORECAST_PATH.open("w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
    print(f"Added new-AI reference values to {len(predictions)} forecast days.")


if __name__ == "__main__":
    main()
