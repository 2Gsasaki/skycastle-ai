#!/usr/bin/env python3
"""
data/weather.csv を読み込み、露点温度と霧・天空の城スコアを計算して data/feed.json に出力する。
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Dict

WEATHER_CSV = Path("data/weather.csv")
FEED_JSON = Path("data/feed.json")


def read_weather() -> Dict[str, float]:
    """weather.csv から最新の1行を辞書で読み込む。"""
    if not WEATHER_CSV.exists():
        raise FileNotFoundError(f"{WEATHER_CSV} が見つかりません。先に fetch_weather.py を実行してください。")

    with WEATHER_CSV.open("r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
        if not rows:
            raise ValueError(f"{WEATHER_CSV} にデータがありません。")
        row = rows[-1]
    return {
        "date": row["date"],
        "temp": float(row["temp"]),
        "humidity": float(row["humidity"]),
        "wind": float(row["wind"]),
        "cloud": float(row["cloud"]),
        "rain": float(row["rain"]),
    }


def calc_dew_point(temp_c: float, humidity: float) -> float:
    """気温(℃)と相対湿度(%)から露点温度(℃)を求める（Magnus式）。"""
    if not (0.0 < humidity <= 100.0):
        raise ValueError("湿度は0より大きく100以下である必要があります。")
    a = 17.625
    b = 243.04
    alpha = math.log(humidity / 100.0) + (a * temp_c) / (b + temp_c)
    return (b * alpha) / (a - alpha)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def calc_scores(temp: float, dew_point: float, wind: float, cloud: float, rain: float) -> Dict[str, float]:
    """霧スコアと天空の城スコアを計算する."""
    dew_spread = temp - dew_point  # 気温と露点の差（小さいほど霧が出やすい）

    # 霧スコア：露点差・風速・降水量などを減点方式で評価
    fog_score = 100.0
    fog_score -= clamp(dew_spread * 12.0, 0, 60)  # 露点差が5℃なら約60点減
    fog_score -= clamp(max(wind - 1.5, 0) * 10.0, 0, 25)  # 風速1.5m/sを超えると減点
    fog_score -= clamp(rain * 5.0, 0, 10)  # 降水量は霧の発生を邪魔すると仮定
    fog_score = clamp(fog_score, 0, 100)

    # 天空の城スコア：霧スコアをベースに、雲量が多すぎても少なすぎても減点
    castle_score = fog_score
    if cloud < 40:
        castle_score -= (40 - cloud) * 0.6  # 雲が少ないと城が浮かばない
    elif cloud > 90:
        castle_score -= (cloud - 90) * 0.8  # 雲が厚すぎると視界不良
    castle_score -= clamp(max(dew_spread - 2.0, 0) * 8.0, 0, 20)  # 露点差が広がると減点
    castle_score = clamp(castle_score, 0, 100)

    return {
        "fog_score": round(fog_score, 1),
        "castle_score": round(castle_score, 1),
        "dew_point": round(dew_point, 2),
        "dew_spread": round(dew_spread, 2),
    }


def write_feed(date: str, scores: Dict[str, float]) -> None:
    """data/feed.json に結果を保存する。"""
    FEED_JSON.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "date": date,
        **scores,
    }
    with FEED_JSON.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"Saved scores to {FEED_JSON}")


def main() -> None:
    weather = read_weather()
    dew_point = calc_dew_point(weather["temp"], weather["humidity"])
    scores = calc_scores(
        temp=weather["temp"],
        dew_point=dew_point,
        wind=weather["wind"],
        cloud=weather["cloud"],
        rain=weather["rain"],
    )
    write_feed(weather["date"], scores)


if __name__ == "__main__":
    main()
