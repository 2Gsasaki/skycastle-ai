#!/usr/bin/env python3
"""22:30 JSTの翌日予報を、精度検証用CSVに保存する。"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
from pathlib import Path
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

import predict_forecast_window as forecast_predictor


TZ = ZoneInfo("Asia/Tokyo")
DEFAULT_FORECAST_WINDOW_JSON = Path("data/forecast_window.json")
DEFAULT_OUTPUT_CSV = Path("data/forecast_verification.csv")
FIELDNAMES = [
    "issued_at",
    "target_date",
    "temp",
    "humidity",
    "wind",
    "cloud",
    "rain",
    "weathercode",
    "fog_probability",
    "castle_probability",
    "castle_event_probability",
    "event",
]


def parse_issued_at(value: Optional[str]) -> dt.datetime:
    if not value:
        return dt.datetime.now(TZ)

    try:
        parsed = dt.datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"予報作成日時が不正です: {value}") from exc

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=TZ)
    return parsed.astimezone(TZ)


def create_official_predictions(path: Path) -> List[dict]:
    entries = forecast_predictor.load_forecast_entries(path)
    return forecast_predictor.run_prediction(entries, use_history_override=False)


def select_prediction(predictions: List[dict], target_date: str) -> dict:
    for prediction in predictions:
        if str(prediction.get("date")) == target_date:
            return prediction
    raise ValueError(f"{target_date} の予報が見つかりません。")


def build_record(prediction: dict, issued_at: dt.datetime, target_date: str) -> Dict[str, object]:
    return {
        "issued_at": issued_at.isoformat(),
        "target_date": target_date,
        "temp": prediction.get("temp"),
        "humidity": prediction.get("humidity"),
        "wind": prediction.get("wind"),
        "cloud": prediction.get("cloud"),
        "rain": prediction.get("rain"),
        "weathercode": prediction.get("weathercode"),
        "fog_probability": prediction.get("fog_probability"),
        "castle_probability": prediction.get("castle_probability"),
        "castle_event_probability": prediction.get("castle_event_probability"),
        "event": prediction.get("event"),
    }


def target_already_saved(path: Path, target_date: str) -> bool:
    if not path.exists() or path.stat().st_size == 0:
        return False
    with path.open("r", encoding="utf-8", newline="") as f:
        return any(row.get("target_date") == target_date for row in csv.DictReader(f))


def append_record(path: Path, record: Dict[str, object]) -> bool:
    if target_already_saved(path, str(record["target_date"])):
        print(f"Already saved: target_date={record['target_date']} (no overwrite)")
        return False

    path.parent.mkdir(parents=True, exist_ok=True)
    needs_header = not path.exists() or path.stat().st_size == 0
    with path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if needs_header:
            writer.writeheader()
        writer.writerow(record)
    print(f"Saved official forecast: target_date={record['target_date']} issued_at={record['issued_at']}")
    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="前日22:30の翌日予報を検証用CSVに保存します。")
    parser.add_argument("--issued-at", help="予報作成日時（ISO 8601。未指定なら現在時刻）")
    parser.add_argument("--forecast-window", type=Path, default=DEFAULT_FORECAST_WINDOW_JSON)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_CSV)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    issued_at = parse_issued_at(args.issued_at)
    target_date = (issued_at.date() + dt.timedelta(days=1)).isoformat()
    predictions = create_official_predictions(args.forecast_window)
    prediction = select_prediction(predictions, target_date)
    record = build_record(prediction, issued_at, target_date)
    append_record(args.output, record)


if __name__ == "__main__":
    main()
