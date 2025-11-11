#!/usr/bin/env python3
"""Open-Meteo API から最大16日分の早朝気象データを取得して保存する。"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List

import requests
from zoneinfo import ZoneInfo

LATITUDE = 35.98
LONGITUDE = 136.49
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

TZ = ZoneInfo("Asia/Tokyo")
DEFAULT_DAYS = 16
OUTPUT_PATH = Path("data/forecast_window.json")


@dataclass
class MorningAverage:
    date: str
    temp: float
    humidity: float
    wind: float
    cloud: float
    rain: float
    weathercode: int | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="越前大野の早朝気象データを最大16日分まとめて取得し、平均値をJSONで保存します。"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=DEFAULT_DAYS,
        help="取得日数（1〜16）。デフォルトは16日分。",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT_PATH,
        help="保存先パス（JSON）。デフォルトは data/forecast_window.json。",
    )
    return parser.parse_args()


def fetch_hourly_forecast(days: int) -> dict:
    today = dt.datetime.now(TZ).date()
    # Open-Meteo forecast API is inclusive of both start and end dates. To fetch
    # `days` records starting today, subtract 1 day from the end date.
    end_date = today + dt.timedelta(days=days - 1)
    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "hourly": "temperature_2m,relativehumidity_2m,windspeed_10m,cloudcover,precipitation,weathercode",
        "start_date": today.isoformat(),
        "end_date": end_date.isoformat(),
        "timezone": "Asia/Tokyo",
    }
    resp = requests.get(FORECAST_URL, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def select_indices_for_hours(times: Iterable[str], target_hours: set[int]) -> dict[str, List[int]]:
    grouped: dict[str, List[int]] = {}
    for idx, ts in enumerate(times):
        try:
            timestamp = dt.datetime.fromisoformat(ts)
        except ValueError:
            continue
        if timestamp.hour not in target_hours:
            continue
        grouped.setdefault(timestamp.date().isoformat(), []).append(idx)
    return grouped


def compute_morning_average(hourly: dict, day_indices: List[int]) -> MorningAverage:
    def mean(series):
        values = [series[i] for i in day_indices]
        if not values:
            raise ValueError("対象時間帯のデータが空です。")
        return sum(values) / len(values)

    date = dt.datetime.fromisoformat(hourly["time"][day_indices[0]]).date().isoformat()
    weathercode = None
    if "weathercode" in hourly:
        codes = [hourly["weathercode"][i] for i in day_indices]
        weathercode = max(set(codes), key=codes.count) if codes else None

    return MorningAverage(
        date=date,
        temp=mean(hourly["temperature_2m"]),
        humidity=mean(hourly["relativehumidity_2m"]),
        wind=mean(hourly["windspeed_10m"]),
        cloud=mean(hourly["cloudcover"]),
        rain=mean(hourly["precipitation"]),
        weathercode=int(weathercode) if weathercode is not None else None,
    )


def aggregate_mornings(weather_json: dict, days: int) -> List[MorningAverage]:
    hourly = weather_json["hourly"]
    grouped_indices = select_indices_for_hours(hourly["time"], {5, 6, 7, 8})
    results: List[MorningAverage] = []
    for date in sorted(grouped_indices.keys())[:days]:
        indices = grouped_indices[date]
        results.append(compute_morning_average(hourly, indices))
    if not results:
        raise ValueError("対象日数の平均値を計算できませんでした。")
    return results


def serialize_results(averages: List[MorningAverage]) -> list[dict]:
    return [avg.__dict__ for avg in averages]


def save_json(payload: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"Saved {len(payload)} entries to {output_path}")


def main() -> None:
    args = parse_args()
    if args.days < 1 or args.days > 16:
        raise SystemExit("--days は 1〜16 の範囲で指定してください。")

    forecast_json = fetch_hourly_forecast(args.days)
    averages = aggregate_mornings(forecast_json, args.days)
    payload = serialize_results(averages)
    save_json(payload, args.output)


if __name__ == "__main__":
    main()
