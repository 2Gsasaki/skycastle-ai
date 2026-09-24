#!/usr/bin/env python3
"""夜間の科学条件を使い、天空の城を直接予測する新AI。"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd

import evaluate_scientific_candidate as candidate


FORECAST_PATH = Path("data/forecast_window.json")
OUTPUT_PATH = Path("data/forecast_predictions.json")


def load_predictions() -> tuple[dict, list[dict]]:
    with OUTPUT_PATH.open("r", encoding="utf-8") as stream:
        payload = json.load(stream)
    predictions = payload if isinstance(payload, list) else payload.get("predictions", [])
    if not predictions:
        raise ValueError("予報データがありません。")
    return payload, predictions


def load_science_features() -> dict[str, dict]:
    with FORECAST_PATH.open("r", encoding="utf-8") as stream:
        rows = json.load(stream)
    result = {}
    for row in rows:
        features = row.get("science_features")
        if not isinstance(features, dict):
            raise ValueError(f"{row.get('date')}の夜間気象データがありません。")
        result[str(row["date"])] = features
    return result


def add_calendar(frame: pd.DataFrame) -> pd.DataFrame:
    dates = pd.to_datetime(frame["date"], errors="raise")
    frame = frame.copy()
    frame["month"] = dates.dt.month
    day = dates.dt.dayofyear
    frame["day_of_year_sin"] = day.map(lambda value: math.sin(2 * math.pi * value / 365.25))
    frame["day_of_year_cos"] = day.map(lambda value: math.cos(2 * math.pi * value / 365.25))
    return frame


def expectation_reference(history: pd.DataFrame, model) -> tuple[dict[str, pd.Series], float]:
    """確率ではない、季節内での条件の良さを示す順位用の基準を作る。"""
    scored = history[["date"]].copy()
    scored["probability"] = model.predict_proba(history[candidate.SCIENTIFIC_FEATURES])[:, 1]
    months = scored["date"].dt.month
    references = {
        "秋冬": scored.loc[months.isin([9, 10, 11, 12, 1, 2]), "probability"],
        "春夏": scored.loc[months.isin([3, 4, 5, 6, 7, 8]), "probability"],
    }
    recent_start = history["date"].max() - pd.Timedelta(days=364)
    recent = history[history["date"] > recent_start]
    recent_baseline = float(recent["castle_visible"].mean())
    return references, recent_baseline


def expectation_for_date(
    probability: float,
    month: int,
    references: dict[str, pd.Series],
    recent_baseline: float,
) -> tuple[int, int | None, str]:
    label = "秋冬" if month in [9, 10, 11, 12, 1, 2] else "春夏"
    reference = references[label]
    rank = float((reference <= probability).mean() * 100)
    if probability < recent_baseline:
        # 平均出現率を下回る日は、季節内順位だけで中程度以上に見せない。
        score = int(min(20, max(0, round((20 * probability / recent_baseline) / 5) * 5)))
        return score, None, label
    score = int(min(100, max(0, round(rank / 5) * 5)))
    upper_percent = int(max(1, round(100 - rank)))
    return score, upper_percent, label


def main() -> None:
    payload, predictions = load_predictions()
    science_by_date = load_science_features()
    frame = pd.DataFrame(
        [{"date": item["date"], **science_by_date[item["date"]]} for item in predictions]
    )
    frame = add_calendar(frame)
    if frame[candidate.SCIENTIFIC_FEATURES].isna().any().any():
        raise ValueError("新AIの入力に空欄があります。")

    history = candidate.load_frame()
    train = history[history["date"] <= history["date"].max()]
    model = candidate.new_model()
    model.fit(train[candidate.SCIENTIFIC_FEATURES], train["castle_visible"])
    probabilities = model.predict_proba(frame[candidate.SCIENTIFIC_FEATURES])[:, 1]
    references, recent_baseline = expectation_reference(history, model)

    for item, features, probability in zip(predictions, frame.to_dict("records"), probabilities):
        expectation_score, expectation_upper_percent, expectation_season = expectation_for_date(
            float(probability), int(features["month"]), references, recent_baseline
        )
        item["legacy_fog_probability"] = item.get("fog_probability")
        item["legacy_castle_probability"] = item.get("castle_probability")
        item["legacy_castle_event_probability"] = item.get("castle_event_probability")
        item["castle_event_probability"] = round(float(probability), 4)
        item["probability_source"] = "scientific_castle_lightgbm"
        item["probability_source_label"] = "夜間気象・季節・過去実績AI"
        item["expectation_score"] = expectation_score
        item["expectation_upper_percent"] = expectation_upper_percent
        item["expectation_reference_season"] = expectation_season
        item["recent_baseline_probability"] = round(recent_baseline, 4)
        item["scientific_features"] = {
            key: round(float(features[key]), 3)
            for key in candidate.SCIENTIFIC_FEATURES
            if key in features
        }
        item.pop("fog_probability", None)
        item.pop("castle_probability", None)
        item["event"] = "Castle" if probability >= 0.2 else "None"

    with OUTPUT_PATH.open("w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
    print(f"Updated {len(predictions)} days with scientific castle AI.")


if __name__ == "__main__":
    main()
