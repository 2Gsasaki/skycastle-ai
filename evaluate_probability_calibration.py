"""新AIの生の確率を、過去実績に合わせて補正できるか確認する。

公開用の予測値は変更しない。各月について、それより前の記録だけで
LightGBMを学習して生の確率を作り、過去の期間で補正器を学習する。
2025年9月以降は補正器の選択に使わない最終確認期間である。
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss

import evaluate_scientific_candidate as candidate


CALIBRATION_START = pd.Timestamp("2021-09-01")
CALIBRATION_END = pd.Timestamp("2025-08-31")
TEST_START = pd.Timestamp("2025-09-01")
TEST_END = pd.Timestamp("2026-09-17")
FORECAST_PATH = Path("data/forecast_predictions.json")


def logit(probability: np.ndarray) -> np.ndarray:
    safe = np.clip(np.asarray(probability, dtype=float), 0.0001, 0.9999)
    return np.log(safe / (1.0 - safe)).reshape(-1, 1)


def monthly_past_only_predictions(frame: pd.DataFrame) -> pd.DataFrame:
    """各月を、その月より前だけで学習したモデルで予測する。"""
    target = frame[frame["date"] >= CALIBRATION_START].copy()
    target["month_start"] = target["date"].dt.to_period("M").dt.to_timestamp()
    rows = []
    for month_start, month_rows in target.groupby("month_start", sort=True):
        train = frame[frame["date"] < month_start]
        model = candidate.new_model()
        model.fit(train[candidate.SCIENTIFIC_FEATURES], train["castle_visible"])
        predicted = month_rows[["date", "castle_visible"]].copy()
        predicted["raw_probability"] = model.predict_proba(
            month_rows[candidate.SCIENTIFIC_FEATURES]
        )[:, 1]
        rows.append(predicted)
    return pd.concat(rows, ignore_index=True)


def load_current_forecast() -> pd.DataFrame:
    with FORECAST_PATH.open("r", encoding="utf-8") as stream:
        payload = json.load(stream)
    rows = payload["predictions"] if isinstance(payload, dict) else payload
    frame = pd.DataFrame(rows)
    features = pd.DataFrame(frame["scientific_features"].tolist())
    return pd.concat([frame[["date", "castle_event_probability"]], features], axis=1)


def main() -> None:
    history = candidate.load_frame()
    rolling = monthly_past_only_predictions(history)
    calibration = rolling[rolling["date"].between(CALIBRATION_START, CALIBRATION_END)].copy()
    test = rolling[rolling["date"].between(TEST_START, TEST_END)].copy()

    calibrator = LogisticRegression(C=1.0, max_iter=1000, random_state=42)
    calibrator.fit(logit(calibration["raw_probability"]), calibration["castle_visible"])
    test["calibrated_probability"] = calibrator.predict_proba(
        logit(test["raw_probability"])
    )[:, 1]

    print(
        f"補正器の学習: {len(calibration)}日 / 天空の城{int(calibration.castle_visible.sum())}日"
    )
    print(f"最終検証: {len(test)}日 / 天空の城{int(test.castle_visible.sum())}日")
    print(
        "生のAI: "
        f"平均{test.raw_probability.mean():.1%} / Brier={brier_score_loss(test.castle_visible, test.raw_probability):.4f}"
    )
    print(
        "補正後: "
        f"平均{test.calibrated_probability.mean():.1%} / Brier={brier_score_loss(test.castle_visible, test.calibrated_probability):.4f}"
    )

    test["band"] = pd.cut(
        test["calibrated_probability"] * 100,
        [-0.1, 1, 5, 10, 20, 50, 100.1],
        labels=["0～1%", "1～5%", "5～10%", "10～20%", "20～50%", "50%以上"],
    )
    print("\n補正後の確率帯（最終検証）")
    print(
        test.groupby("band", observed=False)
        .agg(days=("castle_visible", "size"), castles=("castle_visible", "sum"),
             displayed=("calibrated_probability", lambda value: f"{value.mean():.1%}"))
        .assign(actual=lambda value: (value["castles"] / value["days"]).map(lambda rate: f"{rate:.1%}"))
        .to_string()
    )

    current = load_current_forecast()
    current["calibrated_probability"] = calibrator.predict_proba(
        logit(current["castle_event_probability"])
    )[:, 1]
    print("\n現在の予報の試算")
    print(
        current[["date", "castle_event_probability", "calibrated_probability"]]
        .rename(columns={"castle_event_probability": "生のAI", "calibrated_probability": "補正後"})
        .to_string(index=False, formatters={"生のAI": "{:.1%}".format, "補正後": "{:.1%}".format})
    )


if __name__ == "__main__":
    main()
