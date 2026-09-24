#!/usr/bin/env python3
"""
Streamlit ダッシュボード:
  - feed.json から予測確率をメトリクス表示
  - 観測ログ入力フォーム（霧・城の実績更新）
"""

from __future__ import annotations

import json
import datetime as dt
from pathlib import Path
from typing import List
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

FEED_JSON = Path("data/feed.json")
HISTORY_CSV = Path("data/history.csv")
WEATHER_CSV = Path("data/weather.csv")
FEATURE_COLUMNS: List[str] = ["temp", "humidity", "wind", "cloud", "rain"]


@st.cache_data(show_spinner=False)
def load_feed(cache_key: float):
    if not FEED_JSON.exists():
        return None
    with FEED_JSON.open("r", encoding="utf-8") as f:
        return json.load(f)


@st.cache_data(show_spinner=False)
def load_history(csv_path: str, last_modified: float):
    csv_path = Path(csv_path)
    if not csv_path.exists():
        return pd.DataFrame(columns=["date", *FEATURE_COLUMNS, "fog_observed", "castle_visible"])
    df = pd.read_csv(csv_path)
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date")
    return df


def save_history(df: pd.DataFrame) -> None:
    df = df.copy()
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")
    df.to_csv(HISTORY_CSV, index=False)
    st.cache_data.clear()


def render_metrics(feed_data):
    today = dt.datetime.now(ZoneInfo("Asia/Tokyo")).date()
    if feed_data and feed_data.get("date"):
        target_date = dt.date.fromisoformat(feed_data["date"])
        if target_date == today:
            title = "今日の予測"
        elif target_date == today + dt.timedelta(days=1):
            title = "明日の予測"
        else:
            title = f"{target_date.strftime('%Y-%m-%d')} の予測"
        date_label = target_date.isoformat()
    else:
        title = "予測"
        date_label = "N/A"

    st.subheader(title)
    st.caption(f"対象日: {date_label}")

    def to_percent_text(value) -> str:
        try:
            return f"{float(value) * 100:.0f}%"
        except (TypeError, ValueError):
            return "N/A"

    cols = st.columns(4)
    if feed_data:
        cols[0].metric("霧発生確率", to_percent_text(feed_data.get("fog_probability")))
        cols[1].metric("天空の城成立確率", to_percent_text(feed_data.get("castle_probability")))
        cols[2].metric("天空の城出現率（総合）", to_percent_text(feed_data.get("castle_event_probability")))
        cols[3].metric("判定", feed_data.get("event", "None"))
    else:
        cols[0].metric("霧発生確率", "N/A")
        cols[1].metric("天空の城成立確率", "N/A")
        cols[2].metric("天空の城出現率（総合）", "N/A")
        cols[3].metric("判定", "N/A")


def render_observation_form(history_df: pd.DataFrame):
    st.subheader("出現した日だけ記録")

    history_df = history_df.copy()
    if not history_df.empty:
        history_df["date"] = pd.to_datetime(history_df["date"])
    if "note" not in history_df.columns:
        history_df["note"] = ""

    selected_date = st.date_input(
        "観測日",
        value=dt.datetime.now(ZoneInfo("Asia/Tokyo")).date(),
        key="obs_date_input",
    )
    date_value = pd.to_datetime(selected_date)
    existing_row = history_df[history_df["date"] == date_value] if not history_df.empty else pd.DataFrame()
    note_value = ""
    if not existing_row.empty:
        row = existing_row.iloc[0]
        castle_value = pd.to_numeric(row.get("castle_visible", 0), errors="coerce")
        fog_value = pd.to_numeric(row.get("fog_observed", 0), errors="coerce")
        note_value = row.get("note", "")
        if pd.isna(note_value):
            note_value = ""
        if not pd.isna(castle_value) and int(castle_value) == 1:
            current_status = "🏰 天空の城"
        elif not pd.isna(fog_value) and int(fog_value) == 1:
            current_status = "🌫️ 霧だけ"
        else:
            current_status = "不出現"
        st.caption(f"現在の記録: {current_status}")

    st.info("天空の城も霧も出なかった日は、何も入力しなくて大丈夫です。不出現として扱います。")
    note = st.text_input("メモ（任意）", value=str(note_value), key=f"obs_note_{selected_date}")
    castle_col, fog_col = st.columns(2)
    castle_clicked = castle_col.button("🏰 天空の城が出た", type="primary", use_container_width=True)
    fog_clicked = fog_col.button("🌫️ 霧だけ出た", use_container_width=True)

    if castle_clicked or fog_clicked:
        history_df = history_df.copy()
        fog_flag = 1
        castle_flag = int(castle_clicked)

        if (history_df["date"] == date_value).any():
            history_df.loc[history_df["date"] == date_value, ["fog_observed", "castle_visible", "note"]] = [
                fog_flag,
                castle_flag,
                note,
            ]
        else:
            new_row = {
                "date": date_value,
                "temp": pd.NA,
                "humidity": pd.NA,
                "wind": pd.NA,
                "cloud": pd.NA,
                "rain": pd.NA,
                "fog_observed": fog_flag,
                "castle_visible": castle_flag,
                "note": note,
            }
            history_df = pd.concat([history_df, pd.DataFrame([new_row])], ignore_index=True)

        save_history(history_df)
        saved_label = "天空の城" if castle_clicked else "霧だけ"
        st.success(f"{selected_date} を「{saved_label}」として保存しました")
        st.rerun()

    st.caption("下の表で直接編集できます（編集後に「保存」ボタンを押してください）。")
    storage_columns = list(history_df.columns)
    editable_df = history_df.copy()
    if "date" in editable_df.columns:
        editable_df["date"] = pd.to_datetime(editable_df["date"], errors="coerce")
        editable_df = editable_df.sort_values("date", ascending=False).reset_index(drop=True)
        editable_df["date"] = editable_df["date"].dt.date
    if "date" in editable_df.columns and "event" in editable_df.columns:
        display_columns = ["date", "event"] + [
            column for column in editable_df.columns if column not in {"date", "event"}
        ]
        editable_df = editable_df[display_columns]
    numeric_columns = [
        "temp",
        "humidity",
        "wind",
        "cloud",
        "rain",
        "fog_probability",
        "castle_probability",
        "castle_event_probability",
        "fog_score",
        "castle_score",
        "dew_point",
        "dew_spread",
    ]
    for col in numeric_columns:
        if col in editable_df.columns:
            editable_df[col] = pd.to_numeric(editable_df[col], errors="coerce")
    if "event" in editable_df.columns:
        editable_df["event"] = editable_df["event"].astype("string").fillna("")
    if "note" in editable_df.columns:
        editable_df["note"] = editable_df["note"].fillna("").astype("string")
    column_config = {
        "date": st.column_config.DateColumn(
            "date",
            help="観測日・予測日を YYYY-MM-DD 形式で表示します。"
        ),
        "temp": st.column_config.NumberColumn(
            "temp",
            help="平均気温（℃）です。"
        ),
        "humidity": st.column_config.NumberColumn(
            "humidity",
            help="平均湿度（％）です。"
        ),
        "wind": st.column_config.NumberColumn(
            "wind",
            help="平均風速（m/s）です。"
        ),
        "cloud": st.column_config.NumberColumn(
            "cloud",
            help="平均雲量（％）です。"
        ),
        "rain": st.column_config.NumberColumn(
            "rain",
            help="降水量（mm）です。"
        ),
        "fog_observed": st.column_config.NumberColumn(
            "fog_observed",
            help="実際に霧が発生したか（1: 霧あり／0: 霧なし）。"
        ),
        "castle_visible": st.column_config.NumberColumn(
            "castle_visible",
            help="天空の城が見えたか（1: 見えた／0: 見えなかった）。"
        ),
        "note": st.column_config.TextColumn(
            "note",
            help="観測メモ（テキスト）を保存します。"
        ),
        "dew_point": st.column_config.NumberColumn(
            "dew_point",
            help="気温と湿度から計算した露点温度（℃）です。"
        ),
        "dew_spread": st.column_config.NumberColumn(
            "dew_spread",
            help="気温 − 露点温度。値が小さいほど霧が発生しやすくなります。"
        ),
        "event": st.column_config.TextColumn(
            "event",
            help="予測判定（Castle: 城成立, FogOnly: 霧のみ, None: 発生無し）"
        ),
        "fog_probability": st.column_config.NumberColumn(
            "fog_probability",
            help="霧発生確率（0〜1）。"
        ),
        "castle_probability": st.column_config.NumberColumn(
            "castle_probability",
            help="天空の城成立確率（0〜1）。"
        ),
        "castle_event_probability": st.column_config.NumberColumn(
            "castle_event_probability",
            help="霧と城の条件をまとめた総合出現率（0〜1）。"
        ),
        "fog_score": st.column_config.NumberColumn(
            "fog_score",
            help="ルールベーススコア（0〜100）。霧が出やすい条件ほど高くなります。"
        ),
        "castle_score": st.column_config.NumberColumn(
            "castle_score",
            help="ルールベースで算出した城成立スコア（0〜100）。"
        ),
        "updated_at": st.column_config.TextColumn(
            "updated_at",
            help="最終更新日時（JST）。main.py 実行時に記録されます。"
        ),
    }
    edited = st.data_editor(
        editable_df,
        num_rows="dynamic",
        column_config=column_config,
    )

    if st.button("テーブルの変更を保存", type="primary"):
        edited["date"] = pd.to_datetime(edited["date"])
        edited = edited.sort_values("date").reset_index(drop=True)
        save_columns = [column for column in storage_columns if column in edited.columns]
        save_columns += [column for column in edited.columns if column not in storage_columns]
        edited = edited[save_columns]
        save_history(edited)
        st.success("history.csv を更新しました")
        st.rerun()


def main():
    st.set_page_config(page_title="SkyCastle AI ダッシュボード", layout="wide")
    st.title("🌤️ SkyCastle AI ダッシュボード")

    feed_mtime = FEED_JSON.stat().st_mtime if FEED_JSON.exists() else 0.0
    history_mtime = HISTORY_CSV.stat().st_mtime if HISTORY_CSV.exists() else 0.0

    feed_data = load_feed(feed_mtime)
    history_df = load_history(str(HISTORY_CSV), history_mtime)

    render_metrics(feed_data)
    render_observation_form(history_df)


if __name__ == "__main__":
    main()
