#!/usr/bin/env python3
"""毎晩の予報窓を保存し、日数別の精度検証に使う。"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo


TZ = ZoneInfo("Asia/Tokyo")
DEFAULT_FORECAST_WINDOW = Path("data/forecast_window.json")
DEFAULT_OUTPUT = Path("data/forecast_window_verification.csv")
FIELDNAMES = [
    "issued_at",
    "issued_date",
    "target_date",
    "lead_days",
    "temp",
    "humidity",
    "wind",
    "cloud",
    "rain",
    "weathercode",
]


def parse_issued_at(value: str | None) -> dt.datetime:
    if not value:
        return dt.datetime.now(TZ)
    parsed = dt.datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=TZ)
    return parsed.astimezone(TZ)


def build_records(entries: Iterable[dict], issued_at: dt.datetime) -> list[dict]:
    issued_date = issued_at.date()
    records = []
    for entry in entries:
        target_date = dt.date.fromisoformat(str(entry["date"]))
        lead_days = (target_date - issued_date).days
        # 今日の早朝は予測・検証の対象外。明日以降だけを残す。
        if lead_days < 1:
            continue
        records.append(
            {
                "issued_at": issued_at.isoformat(),
                "issued_date": issued_date.isoformat(),
                "target_date": target_date.isoformat(),
                "lead_days": lead_days,
                "temp": entry.get("temp"),
                "humidity": entry.get("humidity"),
                "wind": entry.get("wind"),
                "cloud": entry.get("cloud"),
                "rain": entry.get("rain"),
                "weathercode": entry.get("weathercode"),
            }
        )
    return records


def existing_keys(path: Path) -> set[tuple[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return set()
    with path.open("r", encoding="utf-8", newline="") as stream:
        return {
            (row.get("issued_date", ""), row.get("target_date", ""))
            for row in csv.DictReader(stream)
        }


def append_records(path: Path, records: list[dict]) -> int:
    saved = 0
    keys = existing_keys(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists() or path.stat().st_size == 0
    with path.open("a", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDNAMES)
        if write_header:
            writer.writeheader()
        for record in records:
            key = (record["issued_date"], record["target_date"])
            if key in keys:
                continue
            writer.writerow(record)
            keys.add(key)
            saved += 1
    return saved


def main() -> None:
    parser = argparse.ArgumentParser(description="毎晩の将来予報を検証用に保存します。")
    parser.add_argument("--issued-at", help="予報作成時刻（ISO 8601）")
    parser.add_argument("--forecast-window", type=Path, default=DEFAULT_FORECAST_WINDOW)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--dry-run", action="store_true", help="保存せず件数だけ確認する")
    args = parser.parse_args()

    with args.forecast_window.open("r", encoding="utf-8") as stream:
        entries = json.load(stream)
    if not isinstance(entries, list):
        raise ValueError("forecast_window.json は配列である必要があります。")
    issued_at = parse_issued_at(args.issued_at)
    records = build_records(entries, issued_at)
    if args.dry_run:
        print(
            f"Dry run: {len(records)} future forecasts "
            f"({records[0]['target_date']}..{records[-1]['target_date']})"
            if records
            else "Dry run: future forecastsなし"
        )
        return
    saved = append_records(args.output, records)
    print(f"Saved {saved}/{len(records)} future forecasts to {args.output}")


if __name__ == "__main__":
    main()
