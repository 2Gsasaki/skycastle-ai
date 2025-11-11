#!/usr/bin/env python3
"""
SkyCastle AI パイプライン
  1. fetch_weather.py で翌朝または指定日の気象データを取得
  2. score_fog.py で露点計算とスコア算出
  3. predict_model.py で霧発生／城成立確率を推論
  4. 結果を history.csv に追記し、ログへ記録
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import subprocess
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

HISTORY_CSV = Path("data/history.csv")
FEED_JSON = Path("data/feed.json")
WEATHER_CSV = Path("data/weather.csv")
LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "main.log"


def setup_logger() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("skycastle.main")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
        formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        # Forces JST timestamps in logger
        formatter.converter = lambda *args: dt.datetime.now(ZoneInfo("Asia/Tokyo")).timetuple()
    return logger


def run_script(command: list[str], logger: logging.Logger) -> None:
    logger.info("Running command: %s", " ".join(command))
    subprocess.run(command, check=True)


def append_history(logger: logging.Logger) -> None:
    if not (FEED_JSON.exists() and HISTORY_CSV.exists()):
        logger.warning("feed.json または history.csv が存在しません。履歴追加をスキップします。")
        return

    with FEED_JSON.open("r", encoding="utf-8") as f:
        feed = json.load(f)

    date_str = feed.get("date")
    if not date_str:
        logger.warning("feed.json に date がありません。履歴追加をスキップします。")
        return

    history_df = (
        pd.read_csv(HISTORY_CSV).convert_dtypes()
        if HISTORY_CSV.exists()
        else pd.DataFrame()
    )

    weather_df = pd.read_csv(WEATHER_CSV)
    if weather_df.empty:
        logger.warning("weather.csv が空です。履歴追加をスキップします。")
        return

    latest_weather = weather_df.iloc[-1]

    def to_float(value):
        return float(value) if value is not None else pd.NA

    record = {
        "date": date_str,
        "temp": to_float(latest_weather.get("temp")),
        "humidity": to_float(latest_weather.get("humidity")),
        "wind": to_float(latest_weather.get("wind")),
        "cloud": to_float(latest_weather.get("cloud")),
        "rain": to_float(latest_weather.get("rain")),
        "fog_probability": to_float(feed.get("fog_probability")),
        "castle_probability": to_float(feed.get("castle_probability")),
        "castle_event_probability": to_float(feed.get("castle_event_probability")),
        "fog_score": to_float(feed.get("fog_score")),
        "castle_score": to_float(feed.get("castle_score")),
        "dew_point": to_float(feed.get("dew_point")),
        "dew_spread": to_float(feed.get("dew_spread")),
        "event": feed.get("event", "") or "",
        "updated_at": dt.datetime.now(ZoneInfo("Asia/Tokyo")).isoformat(),
    }

    # history.csv が空の場合は必要な列を整える
    float_cols = {
        "temp",
        "humidity",
        "wind",
        "cloud",
        "rain",
        "fog_probability",
        "castle_probability",
        "fog_score",
        "castle_score",
        "dew_point",
        "dew_spread",
        "castle_event_probability",
    }
    int_cols = {"fog_observed", "castle_visible"}
    string_cols = {"note", "event", "updated_at"}
    required_columns = ["date"] + sorted(float_cols) + sorted(int_cols) + sorted(string_cols)

    dtype_map = {
        **{col: "Float64" for col in float_cols},
        **{col: "Int64" for col in int_cols},
        **{col: "string" for col in string_cols},
        "date": "string",
    }

    if history_df.empty:
        history_df = pd.DataFrame({col: pd.Series(dtype=dtype_map[col]) for col in required_columns})

    # 既存の列がない場合は追加、存在する場合は型を揃える
    for key in required_columns:
        if key not in history_df.columns:
            history_df[key] = pd.Series(dtype=dtype_map[key])
        else:
            history_df[key] = history_df[key].astype(dtype_map[key])

    if (history_df["date"] == record["date"]).any():
        idx = history_df.index[history_df["date"] == record["date"]][0]
        for key, value in record.items():
            history_df.at[idx, key] = value
        action = "updated existing record"
    else:
        new_row = {col: pd.NA for col in history_df.columns}
        new_row.update(
            {
                "fog_observed": 0,
                "castle_visible": 0,
                "note": "",
            }
        )
        new_row.update(record)
        new_row_df = pd.DataFrame.from_records([new_row])
        new_row_df = new_row_df.reindex(columns=history_df.columns)
        history_df = pd.concat([history_df, new_row_df], ignore_index=True)
        action = "appended new record"

    history_df.to_csv(HISTORY_CSV, index=False)
    logger.info("History %s for date %s", action, record["date"])


def main() -> None:
    parser = argparse.ArgumentParser(
        description="SkyCastle AI パイプラインを実行します。"
    )
    parser.add_argument(
        "--date",
        help="取得したい日付（YYYY-MM-DD）。指定しない場合は翌日を取得。",
    )
    args = parser.parse_args()

    logger = setup_logger()

    fetch_cmd = ["python", "fetch_weather.py"]
    if args.date:
        fetch_cmd.extend(["--date", args.date, "--use-archive"])

    run_script(fetch_cmd, logger)
    run_script(["python", "score_fog.py"], logger)
    run_script(["python", "predict_model.py"], logger)

    append_history(logger)
    logger.info("Pipeline completed successfully")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        logger = setup_logger()
        logger.error("Command failed: %s", exc)
        raise
