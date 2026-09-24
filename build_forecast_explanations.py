#!/usr/bin/env python3
"""14日予報に、似た過去100日の参考実績を追加する。"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd


DEFAULT_FORECAST = Path("data/forecast_predictions.json")
DEFAULT_DAILY_HISTORY = Path("data/analysis/daily_history_2017_2026.csv")
DEFAULT_OBSERVATIONS = Path("data/history.csv")
NEIGHBOR_COUNT = 100

REFERENCE_COLUMNS = [
    "temp_05_08_mean",
    "humidity_05_08_mean",
    "wind_05_08_mean",
    "cloud_05_08_mean",
    "rain_05_08_mean",
    "day_of_year_sin",
    "day_of_year_cos",
]


def calendar_values(date: pd.Timestamp) -> tuple[float, float]:
    day_of_year = date.dayofyear
    return (
        math.sin(2.0 * math.pi * day_of_year / 365.25),
        math.cos(2.0 * math.pi * day_of_year / 365.25),
    )


def load_reference(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    for column in [*REFERENCE_COLUMNS, "castle_visible"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame.dropna(subset=["date", "castle_visible", *REFERENCE_COLUMNS]).copy()


def load_fog_only_dates(path: Path) -> set[str]:
    frame = pd.read_csv(path)
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    fog = pd.to_numeric(frame.get("fog_observed"), errors="coerce").eq(1)
    castle = pd.to_numeric(frame.get("castle_visible"), errors="coerce").eq(1)
    return {
        value.date().isoformat()
        for value in frame.loc[fog & ~castle, "date"].dropna()
    }


def target_values(item: dict) -> np.ndarray:
    target_date = pd.Timestamp(item["date"])
    season_sin, season_cos = calendar_values(target_date)
    return np.array(
        [
            float(item["temp"]),
            float(item["humidity"]),
            float(item["wind"]),
            float(item["cloud"]),
            float(item["rain"]),
            season_sin,
            season_cos,
        ],
        dtype=float,
    )


def find_analogs(
    item: dict,
    reference: pd.DataFrame,
    fog_only_dates: set[str],
    neighbor_count: int = NEIGHBOR_COUNT,
) -> dict | None:
    target_date = pd.Timestamp(item["date"])
    candidates = reference[reference["date"] < target_date].copy()
    if candidates.empty:
        return None

    count = min(neighbor_count, len(candidates))
    values = candidates[REFERENCE_COLUMNS].to_numpy(dtype=float)
    means = values.mean(axis=0)
    scales = values.std(axis=0)
    scales[scales == 0] = 1.0
    distances = np.linalg.norm((values - target_values(item)) / scales, axis=1)
    nearest_positions = np.argsort(distances)[:count]
    nearest = candidates.iloc[nearest_positions].copy()
    nearest["distance"] = distances[nearest_positions]

    castle_rows = nearest[nearest["castle_visible"].eq(1)].sort_values("distance")
    nearest_dates = nearest["date"].dt.date.astype(str)
    fog_only_count = sum(value in fog_only_dates for value in nearest_dates)
    return {
        "similar_day_count": int(count),
        "castle_day_count": int(castle_rows["castle_visible"].sum()),
        "fog_only_recorded_count": int(fog_only_count),
        "closest_castle_dates": [
            value.date().isoformat() for value in castle_rows["date"].head(5)
        ],
        "reference_start": nearest["date"].min().date().isoformat(),
        "reference_end": nearest["date"].max().date().isoformat(),
    }


def add_explanations(
    forecast_path: Path,
    daily_history_path: Path,
    observations_path: Path,
) -> dict:
    with forecast_path.open("r", encoding="utf-8") as stream:
        payload = json.load(stream)
    predictions = payload if isinstance(payload, list) else payload.get("predictions", [])
    reference = load_reference(daily_history_path)
    fog_only_dates = load_fog_only_dates(observations_path)

    for item in predictions:
        item["analog_context"] = find_analogs(item, reference, fog_only_dates)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="予報JSONに類似日の参考実績を追加します。")
    parser.add_argument("--forecast", type=Path, default=DEFAULT_FORECAST)
    parser.add_argument("--daily-history", type=Path, default=DEFAULT_DAILY_HISTORY)
    parser.add_argument("--observations", type=Path, default=DEFAULT_OBSERVATIONS)
    args = parser.parse_args()

    payload = add_explanations(args.forecast, args.daily_history, args.observations)
    with args.forecast.open("w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
    predictions = payload if isinstance(payload, list) else payload.get("predictions", [])
    print(f"Added analog explanations to {len(predictions)} forecast days: {args.forecast}")


if __name__ == "__main__":
    main()
