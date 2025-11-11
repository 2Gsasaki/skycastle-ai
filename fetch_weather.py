#!/usr/bin/env python3
"""
任意の日付（指定しない場合は翌日）の 5:00〜8:00 の気象データを取得して
data/weather.csv に保存する。
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
from pathlib import Path

import requests
from zoneinfo import ZoneInfo

LATITUDE = 35.98
LONGITUDE = 136.49
OUTPUT_CSV = Path("data/weather.csv")

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"


TZ = ZoneInfo("Asia/Tokyo")


def fetch_weather(target_date: dt.date, use_archive: bool) -> dict:
    """Open-Meteo から target_date の気象データ（hourly）を取得して返す。"""
    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "hourly": "temperature_2m,relativehumidity_2m,windspeed_10m,cloudcover,precipitation",
        "start_date": target_date.isoformat(),
        "end_date": target_date.isoformat(),
        "timezone": "Asia/Tokyo",
    }
    base_url = ARCHIVE_URL if use_archive else FORECAST_URL
    resp = requests.get(base_url, params=params, timeout=30)

    if use_archive and resp.status_code == 400:
        # Archive API は当日データの確定版が未公開だと 400 を返すため、予報 API へフォールバックする。
        print(
            f"Archive API unavailable for {target_date.isoformat()}; falling back to forecast.",
            flush=True,
        )
        resp = requests.get(FORECAST_URL, params=params, timeout=30)

    resp.raise_for_status()
    return resp.json()


def average_morning(weather_json: dict) -> dict:
    """5:00〜8:00 の平均値を計算して辞書で返す。"""
    hourly = weather_json["hourly"]
    target_hours = {5, 6, 7, 8}

    indices = []
    for idx, ts in enumerate(hourly["time"]):
        timestamp = dt.datetime.fromisoformat(ts)
        if timestamp.hour in target_hours:
            indices.append(idx)

    if not indices:
        raise ValueError("対象時間帯のデータが見つかりません。")

    tomorrow_date = dt.datetime.fromisoformat(hourly["time"][indices[0]]).date().isoformat()

    def mean(values):
        values = list(values)
        if not values:
            raise ValueError("平均を計算する値がありません。")
        return sum(values) / len(values)

    return {
        "date": tomorrow_date,
        "temp": mean(hourly["temperature_2m"][i] for i in indices),
        "humidity": mean(hourly["relativehumidity_2m"][i] for i in indices),
        "wind": mean(hourly["windspeed_10m"][i] for i in indices),
        "cloud": mean(hourly["cloudcover"][i] for i in indices),
        "rain": mean(hourly["precipitation"][i] for i in indices),
    }


def save_csv(row: dict) -> None:
    """data/weather.csv に平均値を保存する（ヘッダ付きで1行）。"""
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["date", "temp", "humidity", "wind", "cloud", "rain"]
        )
        writer.writeheader()
        writer.writerow(row)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="指定日（または翌日）の 5:00〜8:00 の気象データを取得して保存します。"
    )
    parser.add_argument(
        "--date",
        help="取得したい日付（YYYY-MM-DD）。未指定の場合は翌日を取得。",
    )
    parser.add_argument(
        "--use-archive",
        action="store_true",
        help="Archive API を強制的に使用して取得する。",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    local_today = dt.datetime.now(TZ).date()
    if args.date:
        target_date = dt.date.fromisoformat(args.date)
        use_archive = args.use_archive or target_date < local_today
    else:
        target_date = local_today + dt.timedelta(days=1)
        use_archive = args.use_archive

    weather_json = fetch_weather(target_date, use_archive)
    averages = average_morning(weather_json)
    save_csv(averages)
    print(f"Saved weather averages for {averages['date']} to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
