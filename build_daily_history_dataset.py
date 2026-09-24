#!/usr/bin/env python3
"""2017年9月以降の全日について、天空の城ラベルと過去天気をまとめる。"""

from __future__ import annotations

import argparse
import datetime as dt
import math
import time
from pathlib import Path

import pandas as pd
import requests

import build_hourly_features as hourly


START_DATE = dt.date(2017, 9, 1)
END_DATE = dt.date(2026, 9, 17)
DEFAULT_OUTPUT = Path("data/analysis/daily_history_2017_2026.csv")


def load_positive_dates(history_path: Path) -> set[dt.date]:
    frame = pd.read_csv(history_path)
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    positive = frame[frame["castle_visible"].eq(1)].dropna(subset=["date"])
    return {
        value.date()
        for value in positive["date"]
        if START_DATE <= value.date() <= END_DATE
    }


def fetch_with_retry(start_date: dt.date, end_date: dt.date) -> pd.DataFrame:
    last_error: Exception | None = None
    for attempt in range(4):
        try:
            return hourly.fetch_hourly(start_date, end_date)
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            if attempt < 3:
                time.sleep(2**attempt)
    raise RuntimeError(f"{start_date}～{end_date}の取得に失敗しました: {last_error}")


def build_record(target_date: dt.date, source: pd.DataFrame, positive_dates: set[dt.date]) -> dict:
    features = hourly.extract_features(target_date, source)
    day = pd.Timestamp(target_date)
    morning = source.loc[day + pd.Timedelta(hours=5) : day + pd.Timedelta(hours=8)]
    day_of_year = target_date.timetuple().tm_yday
    season_start_year = target_date.year if target_date.month >= 9 else target_date.year - 1
    return {
        **features,
        "temp_05_08_mean": hourly.mean_value(morning, "temperature_2m"),
        "humidity_05_08_mean": hourly.mean_value(morning, "relative_humidity_2m"),
        "wind_05_08_mean": hourly.mean_value(morning, "wind_speed_10m"),
        "cloud_05_08_mean": hourly.mean_value(morning, "cloud_cover"),
        "rain_05_08_mean": hourly.mean_value(morning, "precipitation"),
        "month": target_date.month,
        "day_of_year_sin": math.sin(2.0 * math.pi * day_of_year / 365.25),
        "day_of_year_cos": math.cos(2.0 * math.pi * day_of_year / 365.25),
        "season": f"{season_start_year}-{season_start_year + 1}",
        "castle_visible": int(target_date in positive_dates),
    }


def save(path: Path, records: dict[str, dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(records.values()).sort_values("date").to_csv(path, index=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="2017年以降の全日分析データを作ります。")
    parser.add_argument("--history", type=Path, default=hourly.DEFAULT_HISTORY_CSV)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    positive_dates = load_positive_dates(args.history)
    records: dict[str, dict] = {}
    if args.output.exists() and args.output.stat().st_size:
        existing = pd.read_csv(args.output)
        records = {str(row["date"]): row.to_dict() for _, row in existing.iterrows()}

    for year in range(START_DATE.year, END_DATE.year + 1):
        year_start = max(START_DATE, dt.date(year, 1, 1))
        year_end = min(END_DATE, dt.date(year, 12, 31))
        expected = pd.date_range(year_start, year_end, freq="D")
        if all(value.date().isoformat() in records for value in expected):
            print(f"Skip {year}: already saved")
            continue
        fetch_start = year_start - dt.timedelta(days=1)
        print(f"Fetching {year}: {fetch_start} ～ {year_end}")
        source = fetch_with_retry(fetch_start, year_end)
        for value in expected:
            target_date = value.date()
            records[target_date.isoformat()] = build_record(target_date, source, positive_dates)
        save(args.output, records)
        print(f"Saved through {year}: {len(records)} rows")

    print(f"Completed: {len(records)} rows / positives={sum(row['castle_visible'] for row in records.values())}")


if __name__ == "__main__":
    main()
