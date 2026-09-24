#!/usr/bin/env python3
"""Open-Meteoの過去時間別データから、検証用特徴量を作成する。"""

from __future__ import annotations

import argparse
import datetime as dt
import math
from pathlib import Path
from typing import Dict, Iterable, List

import pandas as pd
import requests


ARCHIVE_API_URL = "https://archive-api.open-meteo.com/v1/archive"
LATITUDE = 35.98
LONGITUDE = 136.49
TIMEZONE = "Asia/Tokyo"
DEFAULT_HISTORY_CSV = Path("data/history.csv")
DEFAULT_OUTPUT_CSV = Path("data/analysis/hourly_features.csv")
HOURLY_VARIABLES = [
    "temperature_2m",
    "relative_humidity_2m",
    "precipitation",
    "weather_code",
    "visibility",
    "cloud_cover",
    "wind_speed_10m",
]


def observed_dates(path: Path, end_date: dt.date) -> List[dt.date]:
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])
    if "updated_at" in df.columns:
        updated_dates = pd.to_datetime(df["updated_at"].astype(str).str[:10], errors="coerce")
        df = df[updated_dates.isna() | (updated_dates >= df["date"])]
    dates = sorted({value.date() for value in df["date"] if value.date() <= end_date})
    return dates


def fetch_hourly(start_date: dt.date, end_date: dt.date) -> pd.DataFrame:
    response = requests.get(
        ARCHIVE_API_URL,
        params={
            "latitude": LATITUDE,
            "longitude": LONGITUDE,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "hourly": ",".join(HOURLY_VARIABLES),
            "timezone": TIMEZONE,
            "wind_speed_unit": "kmh",
        },
        timeout=120,
    )
    response.raise_for_status()
    payload = response.json()
    hourly = payload.get("hourly")
    if not isinstance(hourly, dict) or "time" not in hourly:
        raise ValueError(f"時間別データがありません: {payload.get('reason', 'unknown error')}")
    frame = pd.DataFrame(hourly)
    frame["time"] = pd.to_datetime(frame["time"], errors="coerce")
    return frame.dropna(subset=["time"]).set_index("time").sort_index()


def mean_value(frame: pd.DataFrame, column: str) -> float:
    values = pd.to_numeric(frame[column], errors="coerce").dropna()
    return float(values.mean()) if not values.empty else float("nan")


def sum_value(frame: pd.DataFrame, column: str) -> float:
    values = pd.to_numeric(frame[column], errors="coerce").dropna()
    return float(values.sum()) if not values.empty else float("nan")


def min_value(frame: pd.DataFrame, column: str) -> float:
    values = pd.to_numeric(frame[column], errors="coerce").dropna()
    return float(values.min()) if not values.empty else float("nan")


def count_weather_codes(frame: pd.DataFrame, codes: set[int]) -> int:
    values = pd.to_numeric(frame["weather_code"], errors="coerce").dropna().astype(int)
    return int(values.isin(codes).sum())


def dew_point(temp_c: float, humidity: float) -> float:
    if math.isnan(temp_c) or math.isnan(humidity) or humidity <= 0:
        return float("nan")
    a = 17.625
    b = 243.04
    alpha = math.log(humidity / 100.0) + (a * temp_c) / (b + temp_c)
    return (b * alpha) / (a - alpha)


def hours_since_last_rain(frame: pd.DataFrame, reference: pd.Timestamp) -> float:
    rain = pd.to_numeric(frame["precipitation"], errors="coerce")
    rainy = frame[(rain > 0) & (frame.index <= reference)]
    if rainy.empty:
        return 24.0
    hours = (reference - rainy.index[-1]).total_seconds() / 3600.0
    return float(min(max(hours, 0.0), 24.0))


def extract_features(target_date: dt.date, hourly: pd.DataFrame) -> Dict[str, object]:
    day = pd.Timestamp(target_date)
    previous_day = day - pd.Timedelta(days=1)
    prev_evening = hourly.loc[previous_day + pd.Timedelta(hours=18) : previous_day + pd.Timedelta(hours=23)]
    midnight = hourly.loc[day : day + pd.Timedelta(hours=1)]
    formation = hourly.loc[day + pd.Timedelta(hours=2) : day + pd.Timedelta(hours=4)]
    fog_window = hourly.loc[day + pd.Timedelta(hours=5) : day + pd.Timedelta(hours=6)]
    viewing = hourly.loc[day + pd.Timedelta(hours=6) : day + pd.Timedelta(hours=8)]
    fog_and_viewing = hourly.loc[day + pd.Timedelta(hours=5) : day + pd.Timedelta(hours=8)]
    hour_6 = hourly.loc[day + pd.Timedelta(hours=6) : day + pd.Timedelta(hours=6)]
    hour_8 = hourly.loc[day + pd.Timedelta(hours=8) : day + pd.Timedelta(hours=8)]
    rain_lookback = hourly.loc[day - pd.Timedelta(hours=18) : day + pd.Timedelta(hours=6)]

    formation_temp = pd.to_numeric(formation["temperature_2m"], errors="coerce").dropna()
    min_temp_02_04 = float(formation_temp.min()) if not formation_temp.empty else float("nan")
    prev_evening_temp = mean_value(prev_evening, "temperature_2m")
    temp_drop_to_04 = prev_evening_temp - min_temp_02_04
    fog_temp = mean_value(fog_window, "temperature_2m")
    fog_humidity = mean_value(fog_window, "relative_humidity_2m")
    fog_dew_spread = fog_temp - dew_point(fog_temp, fog_humidity)

    return {
        "date": target_date.isoformat(),
        "prev_18_23_rain_sum": sum_value(prev_evening, "precipitation"),
        "rain_00_01_sum": sum_value(midnight, "precipitation"),
        "min_temp_02_04": min_temp_02_04,
        "temp_drop_to_04": temp_drop_to_04,
        "humidity_05_06_mean": fog_humidity,
        "wind_05_06_mean": mean_value(fog_window, "wind_speed_10m"),
        "cloud_05_06_mean": mean_value(fog_window, "cloud_cover"),
        "rain_05_06_sum": sum_value(fog_window, "precipitation"),
        "dew_spread_05_06": fog_dew_spread,
        "cloud_06_08_mean": mean_value(viewing, "cloud_cover"),
        "rain_06_08_sum": sum_value(viewing, "precipitation"),
        "wind_06_08_mean": mean_value(viewing, "wind_speed_10m"),
        "hours_since_rain_at_06": hours_since_last_rain(rain_lookback, day + pd.Timedelta(hours=6)),
        "visibility_05_06_mean": mean_value(fog_window, "visibility"),
        "visibility_05_06_min": min_value(fog_window, "visibility"),
        "visibility_06_08_mean": mean_value(viewing, "visibility"),
        "visibility_06_08_min": min_value(viewing, "visibility"),
        "visibility_change_06_08": mean_value(hour_8, "visibility") - mean_value(hour_6, "visibility"),
        "fog_code_hours_05_08": count_weather_codes(fog_and_viewing, {45, 48}),
        "rain_code_hours_06_08": count_weather_codes(
            viewing,
            {51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82},
        ),
    }


def group_dates_by_year(dates: Iterable[dt.date]) -> Dict[int, List[dt.date]]:
    grouped: Dict[int, List[dt.date]] = {}
    for value in dates:
        grouped.setdefault(value.year, []).append(value)
    return grouped


def parse_args() -> argparse.Namespace:
    default_end = dt.date.today() - dt.timedelta(days=5)
    parser = argparse.ArgumentParser(description="過去の時間別気象から検証用特徴量を作ります。")
    parser.add_argument("--history", type=Path, default=DEFAULT_HISTORY_CSV)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_CSV)
    parser.add_argument("--end-date", type=dt.date.fromisoformat, default=default_end)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dates = observed_dates(args.history, args.end_date)
    if not dates:
        raise ValueError("対象となる観測日がありません。")

    records: List[Dict[str, object]] = []
    for year, year_dates in sorted(group_dates_by_year(dates).items()):
        start_date = min(year_dates) - dt.timedelta(days=1)
        end_date = max(year_dates)
        print(f"Fetching {year}: {start_date} ～ {end_date}")
        hourly = fetch_hourly(start_date, end_date)
        records.extend(extract_features(target_date, hourly) for target_date in year_dates)

    output = pd.DataFrame(records).sort_values("date")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(args.output, index=False)
    print(f"Saved {len(output)} rows to {args.output}")


if __name__ == "__main__":
    main()
