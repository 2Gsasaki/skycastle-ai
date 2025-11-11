#!/usr/bin/env python3
"""
weather.csv と学習済みモデルを使って霧発生確率・天空の城成立確率を推論し、
feed.json に fog_probability / castle_probability / event を追記する。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional

import joblib
import pandas as pd

WEATHER_CSV = Path("data/weather.csv")
FEED_JSON = Path("data/feed.json")
HISTORY_CSV = Path("data/history.csv")
FOG_MODEL_PATH = Path("model/skycastle_fog.pkl")
CASTLE_MODEL_PATH = Path("model/skycastle_castle.pkl")
EVENT_CALIBRATOR_PATH = Path("model/skycastle_event_calibrator.pkl")
BASE_FEATURE_COLUMNS = ["temp", "humidity", "wind", "cloud", "rain"]
LAG_FEATURE_COLUMNS = [
    "prev_temp",
    "prev_humidity",
    "prev_wind",
    "prev_cloud",
    "prev_rain",
    "temp_prev_diff",
]
FEATURE_COLUMNS = BASE_FEATURE_COLUMNS + LAG_FEATURE_COLUMNS
CALIBRATOR_FEATURE_COLUMNS = [
    "fog_probability",
    "castle_probability",
    "fog_castle_product",
]


def load_weather() -> Dict[str, float]:
    if not WEATHER_CSV.exists():
        raise FileNotFoundError(f"{WEATHER_CSV} が見つかりません。fetch_weather.py を先に実行してください。")
    df = pd.read_csv(WEATHER_CSV)
    if df.empty:
        raise ValueError(f"{WEATHER_CSV} にデータがありません。")
    row = df.iloc[-1]
    return {col: row[col] for col in ["date", *BASE_FEATURE_COLUMNS]}


def load_previous_features(current_date: str):
    if not HISTORY_CSV.exists():
        return None

    history_df = pd.read_csv(HISTORY_CSV)
    if history_df.empty:
        return None

    history_df = history_df.dropna(subset=BASE_FEATURE_COLUMNS, how="all")
    history_df["date"] = pd.to_datetime(history_df["date"], errors="coerce")
    history_df = history_df.dropna(subset=["date"]).sort_values("date")

    target_dt = pd.to_datetime(current_date)
    prev_rows = history_df[history_df["date"] < target_dt]
    if prev_rows.empty:
        return None

    prev = prev_rows.iloc[-1]

    try:
        return {
            "prev_temp": float(prev["temp"]),
            "prev_humidity": float(prev["humidity"]),
            "prev_wind": float(prev["wind"]),
            "prev_cloud": float(prev["cloud"]),
            "prev_rain": float(prev["rain"]),
        }
    except (TypeError, ValueError):
        return None


def build_feature_frame(weather: Dict[str, float]) -> pd.DataFrame:
    features = {col: float(weather[col]) for col in BASE_FEATURE_COLUMNS}
    lag_features = load_previous_features(str(weather["date"]))
    if lag_features is None:
        features.update(
            {
                "prev_temp": float("nan"),
                "prev_humidity": float("nan"),
                "prev_wind": float("nan"),
                "prev_cloud": float("nan"),
                "prev_rain": float("nan"),
            }
        )
        features["temp_prev_diff"] = float("nan")
    else:
        features.update(lag_features)
        features["temp_prev_diff"] = features["prev_temp"] - features["temp"]
    return pd.DataFrame([[features[col] for col in FEATURE_COLUMNS]], columns=FEATURE_COLUMNS)


def load_models():
    if not FOG_MODEL_PATH.exists() or not CASTLE_MODEL_PATH.exists():
        raise FileNotFoundError("学習済みモデルが見つかりません。train_model.py を先に実行してください。")
    fog_model = joblib.load(FOG_MODEL_PATH)
    castle_model = joblib.load(CASTLE_MODEL_PATH)
    return fog_model, castle_model


def build_calibrator_features(fog_prob: float, castle_prob: float) -> pd.DataFrame:
    return pd.DataFrame(
        [[fog_prob, castle_prob, fog_prob * castle_prob]],
        columns=CALIBRATOR_FEATURE_COLUMNS,
    )


def load_calibrator():
    if not EVENT_CALIBRATOR_PATH.exists():
        return None
    payload = joblib.load(EVENT_CALIBRATOR_PATH)
    model = payload.get("model")
    feature_names = payload.get("feature_names", CALIBRATOR_FEATURE_COLUMNS)
    return model, feature_names


def compute_event_probability(fog_prob: float, castle_prob: float) -> float:
    calibrator = load_calibrator()
    if calibrator is None:
        return fog_prob * castle_prob

    model, feature_names = calibrator
    features = build_calibrator_features(fog_prob, castle_prob)[feature_names]
    try:
        return float(model.predict_proba(features)[0, 1])
    except Exception:
        # 予期しない失敗時はフォールバックで積に戻す
        return fog_prob * castle_prob


def predict_probabilities(features: pd.DataFrame):
    fog_model, castle_model = load_models()
    fog_prob = float(fog_model.predict_proba(features)[0, 1])
    castle_prob = float(castle_model.predict_proba(features)[0, 1])
    return fog_prob, castle_prob


def determine_event(fog_prob: float, castle_prob: float, event_prob: Optional[float] = None) -> str:
    if event_prob is not None:
        if event_prob >= 0.5:
            return "Castle"
        if fog_prob >= 0.5:
            return "FogOnly"
        return "None"

    if fog_prob >= 0.7 and castle_prob >= 0.6:
        return "Castle"
    if fog_prob >= 0.5:
        return "FogOnly"
    return "None"


def update_feed(date: str, fog_prob: float, castle_prob: float, event_prob: float) -> None:
    payload = {
        "date": date,
        "fog_probability": round(fog_prob, 3),
        "castle_probability": round(castle_prob, 3),
        "castle_event_probability": round(event_prob, 3),
        "event": determine_event(fog_prob, castle_prob, event_prob),
    }
    if FEED_JSON.exists():
        with FEED_JSON.open("r", encoding="utf-8") as f:
            existing = json.load(f)
        existing.update(payload)
        payload = existing

    with FEED_JSON.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"Updated {FEED_JSON}")


def main() -> None:
    weather = load_weather()
    features = build_feature_frame(weather)

    fog_prob, castle_prob = predict_probabilities(features)
    event_prob = compute_event_probability(fog_prob, castle_prob)
    update_feed(weather["date"], fog_prob, castle_prob, event_prob)


if __name__ == "__main__":
    main()
