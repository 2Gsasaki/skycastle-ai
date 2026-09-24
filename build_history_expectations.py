#!/usr/bin/env python3
"""過去ログ用に、未来の正解を使わない振り返り期待指数を作る。"""

from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

import evaluate_scientific_candidate as candidate


HISTORY_PATH = Path("data/history.csv")
OUTPUT_PATH = Path("public/data/history_expectations.json")
LOG_START_DATE = pd.Timestamp("2025-10-27")
TZ = ZoneInfo("Asia/Tokyo")


def monthly_score_caps(history: pd.DataFrame) -> dict[int, int]:
    """最も出現率が高い月を100として、月ごとの指数上限を作る。"""
    rates = history.groupby(history["date"].dt.month)["castle_visible"].mean()
    peak_rate = float(rates.max()) if not rates.empty else 0.0
    if peak_rate <= 0:
        return {month: 0 for month in range(1, 13)}
    return {
        month: int(min(100, max(0, round((float(rates.get(month, 0)) / peak_rate * 100) / 5) * 5)))
        for month in range(1, 13)
    }


def ai_probability_score(probability: float) -> int:
    """AI推定値を、過去実績で決めた基準点に沿って0～100へ変換する。"""
    points = [(0.0, 0), (0.03, 20), (0.08, 50), (0.20, 80), (0.50, 100)]
    if probability >= points[-1][0]:
        return 100
    for (lower_probability, lower_score), (upper_probability, upper_score) in zip(points, points[1:]):
        if probability <= upper_probability:
            ratio = (probability - lower_probability) / (upper_probability - lower_probability)
            score = lower_score + ratio * (upper_score - lower_score)
            return int(min(100, max(0, round(score / 5) * 5)))
    return 100


def expectation_score(
    probability: float,
    reference: pd.Series,
    baseline: float,
    month_cap: int,
) -> tuple[int, int | None]:
    score = min(ai_probability_score(probability), month_cap)
    if probability < baseline:
        return score, None
    rank = float((reference <= probability).mean() * 100)
    return score, int(max(1, round(100 - rank)))


def retrospective_predictions(weather: pd.DataFrame) -> dict[str, dict]:
    targets = weather[weather["date"] >= LOG_START_DATE].copy()
    targets["month_start"] = targets["date"].dt.to_period("M").dt.to_timestamp()
    results: dict[str, dict] = {}

    for month_start, month_rows in targets.groupby("month_start", sort=True):
        train = weather[weather["date"] < month_start].copy()
        if train.empty or train["castle_visible"].nunique() < 2:
            continue
        model = candidate.new_model()
        model.fit(train[candidate.SCIENTIFIC_FEATURES], train["castle_visible"])

        train_probability = model.predict_proba(train[candidate.SCIENTIFIC_FEATURES])[:, 1]
        scored_train = pd.DataFrame(
            {"date": train["date"].to_numpy(), "probability": train_probability}
        )
        recent_start = month_start - pd.Timedelta(days=365)
        recent = train[train["date"] >= recent_start]
        baseline = float(recent["castle_visible"].mean()) if not recent.empty else float(train["castle_visible"].mean())
        month_caps = monthly_score_caps(train)

        probabilities = model.predict_proba(month_rows[candidate.SCIENTIFIC_FEATURES])[:, 1]
        for (_, row), probability in zip(month_rows.iterrows(), probabilities):
            month = int(row["date"].month)
            autumn_winter = month in [9, 10, 11, 12, 1, 2]
            reference_months = scored_train["date"].dt.month.isin(
                [9, 10, 11, 12, 1, 2] if autumn_winter else [3, 4, 5, 6, 7, 8]
            )
            reference = scored_train.loc[reference_months, "probability"]
            month_cap = month_caps[month]
            score, upper_percent = expectation_score(float(probability), reference, baseline, month_cap)
            results[row["date"].date().isoformat()] = {
                "retrospective_probability": round(float(probability), 4),
                "retrospective_expectation_score": score,
                "retrospective_upper_percent": upper_percent,
                "retrospective_baseline_probability": round(baseline, 4),
                "retrospective_reference_season": "秋冬" if autumn_winter else "春夏",
                "retrospective_month_score_cap": month_cap,
                "scientific_features": {
                    key: round(float(row[key]), 3) for key in candidate.SCIENTIFIC_FEATURES
                },
            }
    return results


def clean_value(value):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if isinstance(value, np.generic):
        return value.item()
    return value


def main() -> None:
    weather = candidate.load_frame()
    retrospective = retrospective_predictions(weather)

    history = pd.read_csv(HISTORY_PATH)
    history["date"] = pd.to_datetime(history["date"], errors="coerce")
    today = pd.Timestamp(dt.datetime.now(TZ).date())
    history = history[
        history["date"].between(LOG_START_DATE, today, inclusive="both")
    ].copy()
    history = history.sort_values("date").drop_duplicates("date", keep="last")

    rows = []
    for _, source in history.iterrows():
        date = source["date"].date().isoformat()
        row = {key: clean_value(value) for key, value in source.items() if key != "date"}
        row["date"] = date
        row.update(retrospective.get(date, {}))
        rows.append(row)

    payload = {
        "generated_at": dt.datetime.now(TZ).isoformat(),
        "method": "past_only_model_with_observed_weather",
        "note": "その月より前の記録で学習し、当日の実際の気象条件で振り返った参考値です。",
        "rows": rows,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    scored = sum("retrospective_expectation_score" in row for row in rows)
    print(f"Saved {len(rows)} history rows ({scored} scored) to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
