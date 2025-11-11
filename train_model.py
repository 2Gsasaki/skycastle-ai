#!/usr/bin/env python3
"""
history.csv を使って霧発生モデルと天空の城成立モデルの2本を学習し、
それぞれ model/skycastle_fog.pkl、model/skycastle_castle.pkl に保存する。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List

import joblib
import lightgbm as lgb
import pandas as pd

HISTORY_CSV = Path("data/history.csv")
MODEL_DIR = Path("model")
FOG_MODEL_PATH = MODEL_DIR / "skycastle_fog.pkl"
CASTLE_MODEL_PATH = MODEL_DIR / "skycastle_castle.pkl"
EVENT_CALIBRATOR_PATH = MODEL_DIR / "skycastle_event_calibrator.pkl"
BASE_FEATURE_COLUMNS: List[str] = ["temp", "humidity", "wind", "cloud", "rain"]
LAG_FEATURE_COLUMNS: List[str] = [
    "prev_temp",
    "prev_humidity",
    "prev_wind",
    "prev_cloud",
    "prev_rain",
    "temp_prev_diff",
]
FEATURE_COLUMNS: List[str] = BASE_FEATURE_COLUMNS + LAG_FEATURE_COLUMNS


def load_history() -> pd.DataFrame:
    if not HISTORY_CSV.exists():
        raise FileNotFoundError(f"{HISTORY_CSV} が存在しません。観測データを追加してください。")

    df = pd.read_csv(HISTORY_CSV)
    if df.empty:
        raise ValueError(f"{HISTORY_CSV} にデータ行がありません。")

    missing_cols = [col for col in BASE_FEATURE_COLUMNS + ["fog_observed", "castle_visible"] if col not in df.columns]
    if missing_cols:
        raise ValueError(f"{HISTORY_CSV} に必要な列が足りません: {missing_cols}")

    df = df.dropna(subset=BASE_FEATURE_COLUMNS + ["fog_observed", "castle_visible"])
    if df.empty:
        raise ValueError("必要な列に欠損値があり、学習可能な行がありません。")

    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date")

    for col in BASE_FEATURE_COLUMNS:
        df[f"prev_{col}"] = df[col].shift(1)
    df["temp_prev_diff"] = df["prev_temp"] - df["temp"]

    df = df.dropna(subset=LAG_FEATURE_COLUMNS)
    if df.empty:
        raise ValueError("前日分の特徴量が作成できず、学習データが残りませんでした。")

    # 整数ラベルに揃える
    df["fog_observed"] = df["fog_observed"].astype(int)
    df["castle_visible"] = df["castle_visible"].astype(int)
    return df


def train_model(features: pd.DataFrame, target: pd.Series, model_path: Path):
    if target.nunique() < 2:
        raise ValueError(f"ラベルに2種類以上の値が必要です（{model_path.name}）。データを追加してください。")

    model = lgb.LGBMClassifier(
        objective="binary",
        n_estimators=200,
        num_leaves=31,
        learning_rate=0.05,
        subsample=0.9,
        colsample_bytree=0.9,
        random_state=42,
    )
    model.fit(features, target)
    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, model_path)
    print(f"Saved model to {model_path}")
    return model


def build_calibrator_features(fog_prob: pd.Series, castle_prob: pd.Series) -> pd.DataFrame:
    features = pd.DataFrame(
        {
            "fog_probability": fog_prob,
            "castle_probability": castle_prob,
            "fog_castle_product": fog_prob * castle_prob,
        }
    )
    return features


def train_event_calibrator(
    df: pd.DataFrame,
    fog_model,
    castle_model,
) -> None:
    from sklearn.linear_model import LogisticRegression

    event_target = ((df["fog_observed"] == 1) & (df["castle_visible"] == 1)).astype(int)
    if event_target.nunique() < 2:
        if EVENT_CALIBRATOR_PATH.exists():
            EVENT_CALIBRATOR_PATH.unlink()
            print("Removed existing event calibrator because of insufficient positive samples.")
        print("Skipping event calibrator training: need both positive and negative samples.")
        return

    fog_prob = pd.Series(fog_model.predict_proba(df[FEATURE_COLUMNS])[:, 1], index=df.index)
    castle_prob = pd.Series(castle_model.predict_proba(df[FEATURE_COLUMNS])[:, 1], index=df.index)
    calibrator_features = build_calibrator_features(fog_prob, castle_prob)

    calibrator = LogisticRegression(max_iter=1000)
    calibrator.fit(calibrator_features, event_target)
    payload = {
        "model": calibrator,
        "feature_names": list(calibrator_features.columns),
    }
    EVENT_CALIBRATOR_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(payload, EVENT_CALIBRATOR_PATH)
    print(f"Saved event calibrator to {EVENT_CALIBRATOR_PATH}")


def update_history_event_probability(
    fog_model,
    castle_model,
) -> None:
    if not HISTORY_CSV.exists():
        return

    try:
        history_raw = pd.read_csv(HISTORY_CSV)
    except Exception as exc:  # pragma: no cover - defensive
        print(f"Skip history backfill: failed to read history.csv ({exc})")
        return

    if history_raw.empty:
        return

    sortable = history_raw.copy()
    sortable["date"] = pd.to_datetime(sortable["date"], errors="coerce")
    sortable = sortable.sort_values("date")

    for col in BASE_FEATURE_COLUMNS:
        sortable[f"prev_{col}"] = sortable[col].shift(1)
    sortable["temp_prev_diff"] = sortable["prev_temp"] - sortable["temp"]

    feature_mask = sortable[FEATURE_COLUMNS].notna().all(axis=1)
    if not feature_mask.any():
        history_raw["castle_event_probability"] = pd.NA
        history_raw.to_csv(HISTORY_CSV, index=False)
        return

    feature_df = sortable.loc[feature_mask, FEATURE_COLUMNS].astype(float)
    fog_prob = pd.Series(fog_model.predict_proba(feature_df)[:, 1], index=feature_df.index)
    castle_prob = pd.Series(castle_model.predict_proba(feature_df)[:, 1], index=feature_df.index)

    if EVENT_CALIBRATOR_PATH.exists():
        payload = joblib.load(EVENT_CALIBRATOR_PATH)
        calibrator = payload["model"]
        feature_names = payload["feature_names"]
        calibrator_features = build_calibrator_features(fog_prob, castle_prob)[feature_names]
        event_prob = calibrator.predict_proba(calibrator_features)[:, 1]
    else:
        event_prob = (fog_prob * castle_prob).to_numpy()

    history_raw["castle_event_probability"] = pd.Series(pd.NA, index=history_raw.index, dtype="Float64")
    history_raw.loc[feature_mask, "castle_event_probability"] = event_prob
    history_raw.to_csv(HISTORY_CSV, index=False)
    print("Updated history.csv with castle_event_probability")


def main() -> None:
    df = load_history()
    X = df[FEATURE_COLUMNS]

    # 霧発生モデル
    fog_model = train_model(X, df["fog_observed"], FOG_MODEL_PATH)

    # 天空の城モデル（霧が発生したデータを優先）
    castle_df = df[df["fog_observed"] == 1]
    if len(castle_df) >= 2 and castle_df["castle_visible"].nunique() >= 2:
        castle_model = train_model(castle_df[FEATURE_COLUMNS], castle_df["castle_visible"], CASTLE_MODEL_PATH)
    else:
        # 霧データが十分でなければ全データで学習
        print("霧発生時のデータが不足しているため、全データで城モデルを学習します。")
        castle_model = train_model(X, df["castle_visible"], CASTLE_MODEL_PATH)

    train_event_calibrator(df, fog_model, castle_model)
    update_history_event_probability(fog_model, castle_model)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[Error] {exc}", file=sys.stderr)
        sys.exit(1)
