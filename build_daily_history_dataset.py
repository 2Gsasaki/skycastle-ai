#!/usr/bin/env python3
"""2017年9月以降の全日について、天空の城ラベルと過去天気をまとめる。"""

from __future__ import annotations

import argparse
import datetime as dt
import math
import time
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests

import build_hourly_features as hourly


START_DATE = dt.date(2017, 9, 1)
DEFAULT_OUTPUT = Path("data/analysis/daily_history_2017_2026.csv")
TZ = ZoneInfo("Asia/Tokyo")


def load_positive_dates(history_path: Path, end_date: dt.date) -> set[dt.date]:
    frame = pd.read_csv(history_path)
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    positive = frame[frame["castle_visible"].eq(1)].dropna(subset=["date"])
    return {
        value.date()
        for value in positive["date"]
        if START_DATE <= value.date() <= end_date
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


def append_records(path: Path, records: list[dict], columns: list[str] | None) -> None:
    """既存行の小数表記を変えず、新しい日だけを末尾へ追加する。"""
    if not records:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(records).sort_values("date")
    if columns:
        frame = frame.reindex(columns=columns)
    frame.to_csv(path, mode="a", header=not path.exists() or not path.stat().st_size, index=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="2017年以降の全日分析データを作ります。")
    parser.add_argument("--history", type=Path, default=hourly.DEFAULT_HISTORY_CSV)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--end-date",
        type=dt.date.fromisoformat,
        default=dt.datetime.now(TZ).date(),
        help="追加する最終日（初期値は日本時間の当日）",
    )
    args = parser.parse_args()
    end_date = args.end_date
    if end_date < START_DATE:
        raise ValueError(f"終了日は{START_DATE}以降にしてください。")

    positive_dates = load_positive_dates(args.history, end_date)
    records: dict[str, dict] = {}
    existing_columns: list[str] | None = None
    if args.output.exists() and args.output.stat().st_size:
        existing = pd.read_csv(args.output)
        existing_columns = list(existing.columns)
        records = {str(row["date"]): row.to_dict() for _, row in existing.iterrows()}
    added_records: list[dict] = []

    for year in range(START_DATE.year, end_date.year + 1):
        year_start = max(START_DATE, dt.date(year, 1, 1))
        year_end = min(end_date, dt.date(year, 12, 31))
        expected = pd.date_range(year_start, year_end, freq="D")
        missing = [value.date() for value in expected if value.date().isoformat() not in records]
        if not missing:
            print(f"Skip {year}: already saved")
            continue
        fetch_start = min(missing) - dt.timedelta(days=1)
        fetch_end = max(missing)
        print(f"Fetching {year}: {fetch_start} ～ {fetch_end}")
        source = fetch_with_retry(fetch_start, fetch_end)
        for target_date in missing:
            record = build_record(target_date, source, positive_dates)
            records[target_date.isoformat()] = record
            added_records.append(record)
        print(f"Prepared through {year}: {len(records)} rows")

    if existing_columns is None:
        save(args.output, records)
    else:
        append_records(args.output, added_records, existing_columns)
    print(f"Completed: {len(records)} rows / positives={sum(row['castle_visible'] for row in records.values())}")


if __name__ == "__main__":
    main()
