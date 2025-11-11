#!/usr/bin/env python3
"""
Streamlit ダッシュボード:
  - feed.json から予測確率をメトリクス表示
  - history.csv から過去推移グラフを描画
  - 観測ログ入力フォーム（霧・城の実績更新）
  - 手動で最新予報を再計算するボタン
"""

from __future__ import annotations

import json
import datetime as dt
import subprocess
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


def render_history_chart(history_df: pd.DataFrame):
    st.subheader("過去推移グラフ")
    if history_df.empty:
        st.info("history.csv にデータがありません。観測ログを追加してください。")
        return
    chart_df = history_df[["date", "fog_observed", "castle_visible"]].set_index("date")
    chart_df = chart_df.rename(columns={"fog_observed": "Fog Observed", "castle_visible": "Castle Visible"})
    st.line_chart(chart_df)

    if "castle_event_probability" in history_df.columns:
        prob_df = history_df[["date", "castle_event_probability"]].dropna(subset=["castle_event_probability"])
        if not prob_df.empty:
            prob_series = (
                pd.to_numeric(prob_df.set_index("date")["castle_event_probability"], errors="coerce") * 100.0
            )
            prob_series = prob_series.rename("Castle Event Probability (%)")
            st.line_chart(prob_series)


def render_observation_form(history_df: pd.DataFrame):
    st.subheader("観測ログ入力／編集")

    history_df = history_df.copy()
    if not history_df.empty:
        history_df["date"] = pd.to_datetime(history_df["date"])

    if "note" not in history_df.columns:
        history_df["note"] = ""

    prev_selected_date = st.session_state.get("obs_selected_date")
    selected_date = st.date_input(
        "観測日",
        value=prev_selected_date or dt.date.today(),
        key="obs_date_input",
    )

    date_changed = prev_selected_date != selected_date
    st.session_state["obs_selected_date"] = selected_date

    if date_changed:
        Path("logs").mkdir(parents=True, exist_ok=True)
        with Path("logs/dashboard_events.log").open("a", encoding="utf-8") as f:
            f.write(
                f"{dt.datetime.now(ZoneInfo('Asia/Tokyo')).isoformat()} - observation_date changed "
                f"from {prev_selected_date} to {selected_date}\n"
            )
        st.sidebar.info(f"観測日を {selected_date} に切り替えました（ログ出力済み）")

        existing_row = (
            history_df[history_df["date"] == pd.to_datetime(selected_date)]
            if not history_df.empty
            else pd.DataFrame()
        )
        if not existing_row.empty:
            row = existing_row.iloc[0]
            fog_val = bool(row["fog_observed"])
            castle_val = bool(row["castle_visible"])
            note_val = row.get("note", "")
            if pd.isna(note_val):
                note_val = ""
        else:
            fog_val = False
            castle_val = False
            note_val = ""

        st.session_state["obs_fog_value"] = fog_val
        st.session_state["obs_castle_value"] = castle_val
        st.session_state["obs_note_value"] = note_val
    else:
        # 初期化されていない場合のみデフォルト値を入れる
        st.session_state.setdefault("obs_fog_value", False)
        st.session_state.setdefault("obs_castle_value", False)
        st.session_state.setdefault("obs_note_value", "")

    fog_flag = st.checkbox("霧が発生した", key="obs_fog_value")
    castle_flag = st.checkbox("天空の城が見えた", key="obs_castle_value")
    note = st.text_input("メモ（任意）", key="obs_note_value")
    save_clicked = st.button("保存", key="obs_save_button")

    if save_clicked:
        history_df = history_df.copy()
        date_str = pd.to_datetime(st.session_state["obs_selected_date"])

        if (history_df["date"] == date_str).any():
            history_df.loc[history_df["date"] == date_str, ["fog_observed", "castle_visible", "note"]] = [
                int(fog_flag),
                int(castle_flag),
                note,
            ]
        else:
            new_row = {
                "date": date_str,
                "temp": history_df["temp"].mean() if "temp" in history_df.columns and not history_df.empty else 0,
                "humidity": history_df["humidity"].mean() if "humidity" in history_df.columns and not history_df.empty else 0,
                "wind": history_df["wind"].mean() if "wind" in history_df.columns and not history_df.empty else 0,
                "cloud": history_df["cloud"].mean() if "cloud" in history_df.columns and not history_df.empty else 0,
                "rain": history_df["rain"].mean() if "rain" in history_df.columns and not history_df.empty else 0,
                "fog_observed": int(fog_flag),
                "castle_visible": int(castle_flag),
                "note": note,
            }
            history_df = pd.concat([history_df, pd.DataFrame([new_row])], ignore_index=True)

        save_history(history_df)
        st.success("観測ログを保存しました")
        st.session_state["obs_last_synced_date"] = None
        st.rerun()

    st.caption("下の表で直接編集できます（編集後に「保存」ボタンを押してください）。")
    editable_df = history_df.copy()
    editable_df["date"] = editable_df["date"].dt.date
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
        save_history(edited)
        st.success("history.csv を更新しました")
        st.rerun()


def render_manual_run_buttons():
    st.subheader("手動実行")
    col1, col2 = st.columns(2)

    if col1.button("最新予報を再計算", type="primary"):
        try:
            subprocess.run(["python", "main.py"], check=True)
            st.success("予報を更新しました")
            st.rerun()
        except subprocess.CalledProcessError as exc:
            st.error(f"更新に失敗しました: {exc}")

    with col2.form("manual_fetch_form"):
        manual_date = st.date_input("過去データを取得する日付", key="manual_date")
        fetch_btn = st.form_submit_button("指定日の気象データを取得（Archive API）")

    if fetch_btn:
        try:
            subprocess.run(["python", "main.py", "--date", manual_date.isoformat()], check=True)
            st.success(
                f"{manual_date.isoformat()} の気象データを取得し、予報と history.csv を更新しました。"
            )
            st.rerun()
        except subprocess.CalledProcessError as exc:
            st.error(f"過去データの取得に失敗しました: {exc}")


def main():
    st.set_page_config(page_title="SkyCastle AI ダッシュボード", layout="wide")
    st.title("🌤️ SkyCastle AI ダッシュボード")

    feed_mtime = FEED_JSON.stat().st_mtime if FEED_JSON.exists() else 0.0
    history_mtime = HISTORY_CSV.stat().st_mtime if HISTORY_CSV.exists() else 0.0

    feed_data = load_feed(feed_mtime)
    history_df = load_history(str(HISTORY_CSV), history_mtime)

    render_metrics(feed_data)
    render_history_chart(history_df)
    render_observation_form(history_df)
    render_manual_run_buttons()


if __name__ == "__main__":
    main()
