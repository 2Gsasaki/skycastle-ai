#!/usr/bin/env python3
"""forecast_window.json を読み込み、各日をモデルで推論してまとめて出力する。"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

import joblib
import numpy as np
import pandas as pd
from zoneinfo import ZoneInfo

FORECAST_JSON = Path("data/forecast_window.json")
OUTPUT_JSON = Path("data/forecast_predictions.json")
HISTORY_CSV = Path("data/history.csv")
FOG_MODEL_PATH = Path("model/skycastle_fog.pkl")
CASTLE_MODEL_PATH = Path("model/skycastle_castle.pkl")
EVENT_CALIBRATOR_PATH = Path("model/skycastle_event_calibrator.pkl")
TZ = ZoneInfo("Asia/Tokyo")

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


@dataclass
class ForecastEntry:
    date: str
    temp: float
    humidity: float
    wind: float
    cloud: float
    rain: float
    weathercode: Optional[int] = None


def load_forecast_entries(path: Path) -> List[ForecastEntry]:
    if not path.exists():
        raise FileNotFoundError(f"{path} が見つかりません。先に fetch_forecast_window.py を実行してください。")

    with path.open("r", encoding="utf-8") as f:
        records = json.load(f)

    entries: List[ForecastEntry] = []
    for record in records:
        try:
            entries.append(
                ForecastEntry(
                    date=str(record["date"]),
                    temp=float(record["temp"]),
                    humidity=float(record["humidity"]),
                    wind=float(record["wind"]),
                    cloud=float(record["cloud"]),
                    rain=float(record["rain"]),
                    weathercode=int(record["weathercode"]) if record.get("weathercode") is not None else None,
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"forecast_window.json のレコードが不正です: {record} ({exc})") from exc
    return entries


def load_models():
    if not FOG_MODEL_PATH.exists() or not CASTLE_MODEL_PATH.exists():
        raise FileNotFoundError("学習済みモデルが見つかりません。train_model.py を実行してから再度お試しください。")
    fog_model = joblib.load(FOG_MODEL_PATH)
    castle_model = joblib.load(CASTLE_MODEL_PATH)
    calibrator: Optional[tuple] = None
    if EVENT_CALIBRATOR_PATH.exists():
        payload = joblib.load(EVENT_CALIBRATOR_PATH)
        calibrator = (payload.get("model"), payload.get("feature_names", CALIBRATOR_FEATURE_COLUMNS))
    return fog_model, castle_model, calibrator


def build_feature_frame(entries: Iterable[ForecastEntry]) -> pd.DataFrame:
    df = pd.DataFrame([entry.__dict__ for entry in entries])
    if df.empty:
        raise ValueError("推論対象となる日付がありません。")

    # 既存historyを参照して前日値を推測するため、最新1行を取得
    history_tail = None
    if HISTORY_CSV.exists():
        history_df = pd.read_csv(HISTORY_CSV)
        if not history_df.empty:
            history_df["date"] = pd.to_datetime(history_df["date"], errors="coerce")
            history_df = history_df.dropna(subset=["date"]).sort_values("date")
            history_tail = history_df.iloc[-1]

    lag_sources = []
    prev_values = None
    if history_tail is not None:
        prev_values = {col: float(history_tail.get(col, np.nan)) for col in BASE_FEATURE_COLUMNS}

    for _, row in df.iterrows():
        lag_sources.append(prev_values)
        prev_values = {col: float(row[col]) for col in BASE_FEATURE_COLUMNS}

    lag_df = pd.DataFrame(lag_sources, columns=BASE_FEATURE_COLUMNS)
    lag_df = lag_df.add_prefix("prev_")
    df = pd.concat([df, lag_df], axis=1)
    df["temp_prev_diff"] = df["prev_temp"] - df["temp"]
    return df[FEATURE_COLUMNS]


def compute_event_probability(fog_prob: float, castle_prob: float, calibrator: Optional[tuple]) -> float:
    if not calibrator:
        return fog_prob * castle_prob
    model, feature_names = calibrator
    features = pd.DataFrame([[fog_prob, castle_prob, fog_prob * castle_prob]], columns=CALIBRATOR_FEATURE_COLUMNS)[
        feature_names
    ]
    try:
        return float(model.predict_proba(features)[0, 1])
    except Exception:
        return fog_prob * castle_prob


def determine_event(fog_prob: float, castle_prob: float, event_prob: float) -> str:
    if event_prob >= 0.5:
        return "Castle"
    if fog_prob >= 0.5:
        return "FogOnly"
    return "None"


def build_history_lookup() -> dict[str, pd.Series]:
    if not HISTORY_CSV.exists():
        return {}

    history_df = pd.read_csv(HISTORY_CSV)
    if history_df.empty:
        return {}

    history_df["date"] = pd.to_datetime(history_df["date"], errors="coerce")
    history_df = history_df.dropna(subset=["date"]).sort_values("date")
    history_df = history_df.drop_duplicates(subset=["date"], keep="last")
    return {row["date"].date().isoformat(): row for _, row in history_df.iterrows()}


def safe_float(value, default=None):
    if value is None:
        return default
    if isinstance(value, (int, float)):
        if pd.isna(value):
            return default
        return float(value)
    try:
        converted = float(value)
    except (TypeError, ValueError):
        return default
    return converted


def run_prediction(entries: List[ForecastEntry]) -> List[dict]:
    fog_model, castle_model, calibrator = load_models()
    feature_frame = build_feature_frame(entries)
    history_lookup = build_history_lookup()

    fog_probs = fog_model.predict_proba(feature_frame)[:, 1]
    castle_probs = castle_model.predict_proba(feature_frame)[:, 1]

    results = []
    for entry, fog_prob, castle_prob in zip(entries, fog_probs, castle_probs):
        event_prob = compute_event_probability(float(fog_prob), float(castle_prob), calibrator)
        base_payload = {
            "date": entry.date,
            "temp": round(entry.temp, 2),
            "humidity": round(entry.humidity, 2),
            "wind": round(entry.wind, 2),
            "cloud": round(entry.cloud, 2),
            "rain": round(entry.rain, 2),
            "weathercode": entry.weathercode,
            "fog_probability": round(float(fog_prob), 3),
            "castle_probability": round(float(castle_prob), 3),
            "castle_event_probability": round(event_prob, 3),
            "event": determine_event(float(fog_prob), float(castle_prob), event_prob),
        }

        history_row = history_lookup.get(entry.date)
        if history_row is not None:
            actual_temp = safe_float(history_row.get("temp"), base_payload["temp"])
            actual_humidity = safe_float(history_row.get("humidity"), base_payload["humidity"])
            actual_wind = safe_float(history_row.get("wind"), base_payload["wind"])
            actual_cloud = safe_float(history_row.get("cloud"), base_payload["cloud"])
            actual_rain = safe_float(history_row.get("rain"), base_payload["rain"])

            actual_fog_prob = safe_float(history_row.get("fog_probability"), base_payload["fog_probability"])
            actual_castle_prob = safe_float(history_row.get("castle_probability"), base_payload["castle_probability"])
            actual_event_prob = safe_float(history_row.get("castle_event_probability"), base_payload["castle_event_probability"])

            base_payload.update(
                {
                    "temp": round(actual_temp, 2),
                    "humidity": round(actual_humidity, 2),
                    "wind": round(actual_wind, 2),
                    "cloud": round(actual_cloud, 2),
                    "rain": round(actual_rain, 2),
                    "fog_probability": round(actual_fog_prob, 3),
                    "castle_probability": round(actual_castle_prob, 3),
                    "castle_event_probability": round(actual_event_prob, 3),
                }
            )

            history_event = history_row.get("event")
            if isinstance(history_event, str) and history_event.strip():
                base_payload["event"] = history_event
            else:
                base_payload["event"] = determine_event(actual_fog_prob, actual_castle_prob, actual_event_prob)

        results.append(base_payload)

    return results


def save_results(results: List[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": dt.datetime.now(TZ).isoformat(),
        "predictions": results,
    }
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"Saved predictions ({len(results)} days) to {output_path} (generated_at={payload['generated_at']})")


def main() -> None:
    entries = load_forecast_entries(FORECAST_JSON)
    results = run_prediction(entries)
    save_results(results, OUTPUT_JSON)


if __name__ == "__main__":
    main()
