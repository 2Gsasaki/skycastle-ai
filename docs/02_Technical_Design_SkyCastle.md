# 🏯 SkyCastle AI ― 越前大野・天空の城出現予測プロジェクト  
## 技術設計書（Technical Design Specification）

---

## 1. 概要

**文書目的：**  
本書は、SkyCastle AI プロジェクトにおけるシステム構成・技術仕様・データ設計・AIモデル構成・通信フローなどの詳細を定義する。

**前提文書：**  
- `01_Specification_SkyCastle.md`（要件定義書）

**作成日：** 2025-10-29  
**最終更新日：** 2026-09-24
**作成者：** SkyCastle Dev Team  
**監修：** ChatGPT（GPT-5）

---

## 1.1 現在の本番構成（2026年9月24日）

本番の公開経路はGitHub ActionsとGitHub Pagesである。Streamlit、FastAPI、Docker内スケジューラ、旧FogModel／CastleModelの説明は、初期設計・管理用・将来拡張として残す。

```text
Open-Meteo時間別予報
  → fetch_forecast_window.py（明日から14日分）
  → predict_forecast_window.py（互換データ生成）
  → predict_scientific_castle_window.py（天空の城を直接予測）
  → data/forecast_predictions.json
  → public/data/forecast_predictions.json
  → public/forecast.html
```

公開用直接予測AIの主な入力は次の16項目である。

- 前夜18～23時の雨量
- 深夜0～1時の雨量
- 午前2～4時の最低気温と前夜からの低下量
- 午前5～6時の湿度・風・雲・雨・露点差
- 午前6～8時の雲・雨・風
- 午前6時までに雨が止んでからの時間
- 月、年周期のsin・cos

AI出力の`castle_event_probability`を公開画面では「AI予測値」と呼ぶ。期待指数はAI推定値を過去実績に沿って0～100へ変換し、月別出現率から求めた上限を適用した5刻みの数値である。基準点は0%=0、3%=20、8%=50、20%=80、50%以上=100。`expectation_upper_percent`は同じ季節内での参考順位であり、期待指数の計算には使わない。

過去ログは次の流れで作成する。

```text
data/history.csv
  ＋ data/analysis/daily_history_2017_2026.csv
  → build_history_expectations.py
  → public/data/history_expectations.json
  → public/history.html
```

振り返り予測は各月より前のデータだけで学習する。対象日の実際の時間別気象を入力するため、当時公開された予報値の再現ではない。`build_daily_history_dataset.py`は毎日、未取得日だけを分析CSVへ追加する。

GitHub ActionsはPython 3.11を使い、`actions/checkout@v5`、`actions/setup-python@v6`、`peaceiris/actions-gh-pages@v4`でNode.js 24対応とする。

---

## 2. 初期設計のシステム全体構成図

┌─────────────────────────────┐
│ SkyCastle AI System Overview │
└─────────────────────────────┘
│
▼
┌─────────────────────────────┐
│ ① Open-Meteo API（気象データ取得） │
│ └─ 気温・湿度・風速・雲量・降水量 │
└─────────────────────────────┘
│ JSON
▼
┌─────────────────────────────┐
│ ② Data Processor (Python) │
│ └─ 露点計算・スコア化 │
│ └─ weather.csv／feed.json 出力 │
└─────────────────────────────┘
│
▼
┌─────────────────────────────┐
│ ③ AI Model (LightGBM) │
│ └─ 学習：過去データ（history.csv） │
│ └─ 推論：翌朝データ（feed.json） │
│ └─ モデル保存：skycastle_fog.pkl／skycastle_castle.pkl │
└─────────────────────────────┘
│
▼
┌─────────────────────────────┐
│ ④ Visualization & Console (Streamlit) │
│ └─ 出現確率・グラフ表示／手動更新 │
│ └─ 観測ログ入力・編集（history.csv更新） │
└─────────────────────────────┘
│
▼
┌─────────────────────────────┐
│ ⑤ Scheduler (Python) │
│ └─ 営業日16:00に main.py 実行 │
│ └─ Dockerコンテナ起動時に常駐 │
└─────────────────────────────┘
│
▼
┌─────────────────────────────┐
│ ⑥ Fog Detector (OpenCV + CNN) │
│ └─ YouTubeライブ映像解析（将来拡張） │
│ └─ fog_result.json出力 │
└─────────────────────────────┘

---

## 3. 使用技術一覧

| 分類 | 技術／ライブラリ | バージョン | 用途 |
|------|-------------------|-------------|------|
| 言語 | Python | 3.11+ | 全処理 |
| API | Open-Meteo | 最新 | 気象データ取得 |
| データ処理 | Pandas | 2.x | CSV・JSON操作 |
| AIモデル | LightGBM | 4.x | 雲海出現確率予測 |
| AI補助 | Scikit-learn | 1.5+ | 学習・評価・分割 |
| 画像解析 | OpenCV | 4.9+ | ライブ映像霧判定 |
| ニューラルネット | Keras（TensorFlow） | 2.15+ | CNNモデル構築 |
| Web表示 | Streamlit | 1.39+ | ダッシュボード |
| API | FastAPI | 0.115+ | RESTエンドポイント提供 |
| 通知 | （将来拡張）SMTP／SNS API | メール・SNS通知 |
| 保存形式 | CSV／JSON／SQLite | - | ローカル永続化 |
| 自動化 | APScheduler／schedule | - | コンテナ常駐スケジューラ |

---

## 4. データ構造設計

### 4.1 気象データ（`weather.csv`）

Open-Meteo の hourly API から 05:00／06:00／07:00／08:00 の値を取得し、平均値を算出して格納する。

| カラム名 | 型 | 説明 |
|-----------|----|------|
| date | date | データ日付 |
| temp | float | 平均気温（℃） |
| humidity | float | 平均湿度（％） |
| wind | float | 平均風速（m/s） |
| cloud | float | 平均雲量（％） |
| rain | float | 前日降水量合計（mm） |

---

### 4.2 履歴データ（`history.csv`）

| カラム名 | 型 | 説明 |
|-----------|----|------|
| date | date | 実施日 |
| temp | float | 平均気温 |
| humidity | float | 平均湿度 |
| wind | float | 風速 |
| cloud | float | 雲量 |
| rain | float | 降水量 |
| fog_probability | float | 霧発生確率（AI出力） |
| castle_probability | float | 天空の城成立確率（AI出力） |
| event_prediction | str | 予測イベント（None/FogOnly/Castle） |
| fog_observed | int | 実際に霧が発生したか（0/1） |
| castle_visible | int | 天空の城が確認できたか（0/1） |
| note | str | 観測メモ（任意） |

---

### 4.3 出力データ（`feed.json`）

```json
{
  "date": "2025-10-29",
  "fog_probability": 0.78,
  "castle_probability": 0.61,
  "event": "Castle",
  "fog_score": 85,
  "castle_score": 72,
  "updated_at": "2025-10-28T20:11:05+09:00"
}
```
4.4 画像解析結果（fog_result.json）
```json
{
  "timestamp": "2025-10-29T06:00:00",
  "fog_detected": true,
  "castle_visible": false,
  "confidence": {
    "fog": 0.91,
    "castle": 0.42
  }
}
```
5. AIモデル設計
5.1 モデル構成
- FogModel：LightGBM Classifier。入力は気温・湿度・露点差・風速・雲量・降水量など。出力は霧発生確率（0〜1）。
- CastleModel：LightGBM Classifier。FogModel の出力確率・気象指標・前日との差分などを入力に、天空の城成立確率（0〜1）を推定。
- 両モデルとも `history.csv` の実績（`fog_observed`、`castle_visible`）をラベルに用いる。CastleModel は霧が観測されたデータを主に学習し、霧無しケースはダウンサンプリングする。
- モデル保存先は `model/skycastle_fog.pkl` および `model/skycastle_castle.pkl` を想定。

5.2 ハイパーパラメータ例
```python
params_fog = {
    "objective": "binary",
    "num_leaves": 31,
    "learning_rate": 0.05,
    "n_estimators": 200,
    "max_depth": -1,
    "subsample": 0.9,
    "colsample_bytree": 0.9
}

params_castle = {
    "objective": "binary",
    "num_leaves": 63,
    "learning_rate": 0.04,
    "n_estimators": 240,
    "max_depth": -1,
    "subsample": 0.85,
    "colsample_bytree": 0.85
}
```

5.3 特徴量重要度（例）
| モデル | 特徴量 | 重要度（相対値） |
|--------|----------|------------------|
| FogModel | 露点差（T - Td） | 0.32 |
| FogModel | 湿度 | 0.27 |
| FogModel | 風速 | 0.18 |
| FogModel | 雲量 | 0.13 |
| FogModel | 降水量 | 0.07 |
| CastleModel | 湿度 | 0.22 |
| CastleModel | FogModel出力 | 0.21 |
| CastleModel | 風速 | 0.18 |
| CastleModel | 日の出時刻差 | 0.16 |
| CastleModel | 雲量 | 0.11 |

5.4 学習・推論処理フロー

```text
[Train]
history.csv → ラベル分割 → 前処理 → FogModel.fit()／CastleModel.fit() → model/skycastle_fog.pkl・model/skycastle_castle.pkl

[Predict]
weather.csv → 前処理 → FogModel.predict_proba() → CastleModel.predict_proba() → feed.json
```
6. 画像解析構成（Fog Detection / Castle Visibility）
6.1 概要
入力：YouTubeライブ映像 or 定期キャプチャ画像

処理：OpenCVで前処理（HSV変換・ぼやけ度計算）後、CNN による霧発生・城浮上の二値判定

出力：`fog_detected`（0/1）、`castle_visible`（0/1）および信頼度スコア。結果は `fog_result.json` として保存され、`history.csv` の実績ラベル更新にも利用。

6.2 OpenCV前処理例
```python
import cv2
import numpy as np

img = cv2.imread("castle_frame.jpg")
hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
h, s, v = cv2.split(hsv)

s_mean = np.mean(s)
v_std = np.std(v)

fog = (s_mean < 40) and (v_std < 25)
castle_visible = (fog and v_std > 20) or (not fog and v_std > 35)
```

6.3 CNN構成（Keras）
| 層 | 種別 | パラメータ |
|----|------|------------|
| 1 | Conv2D | 32 filters, 3×3, relu |
| 2 | MaxPooling2D | 2×2 |
| 3 | Conv2D | 64 filters, 3×3, relu |
| 4 | Flatten | - |
| 5 | Dense | 64, relu |
| 6 | Output | 2, softmax（fog / castle） |

6.4 モデル入出力例
```python
input_shape = (128, 128, 3)
outputs = {
    "fog_detected": 0 or 1,
    "castle_visible": 0 or 1
}
```
7. API・通信設計
7.1 FastAPIエンドポイント
メソッド	パス	概要	出力
GET	/api/predict/tomorrow	最新予測を取得	feed.json内容
GET	/api/history	過去履歴を取得	history.csv内容
GET	/api/fog	霧検出結果を取得	fog_result.json内容

7.2 レスポンス例
```json
{
  "date": "2025-10-29",
  "fog_probability": 0.78,
  "castle_probability": 0.61,
  "event": "Castle",
  "fog_detected": true,
  "castle_visible": true
}
```
8. ダッシュボード構成（Streamlit）
8.1 表示内容
要素	内容
メインタイトル	🌤️ 天空の城 出現予測ダッシュボード
メトリクス表示	霧発生確率・天空の城成立確率（％）＋イベント判定
折れ線グラフ	過去7日間の霧／城確率推移
霧検出結果	画像＋判定結果表示（将来拡張）
手動実行	「最新予報を再計算」ボタンで `main.py` を即時実行
フッター	データ提供元・更新時刻

8.2 コード例
```python
import streamlit as st
import pandas as pd
import json

st.title("🌤️ 天空の城 出現予測")

with open("data/feed.json") as f:
    data = json.load(f)
col1, col2 = st.columns(2)
col1.metric("霧発生確率", f"{data['fog_probability']*100:.0f}%", data["event"])
col2.metric("天空の城成立確率", f"{data['castle_probability']*100:.0f}%", "")

df = pd.read_csv("data/history.csv")
st.line_chart(df.set_index("date")[["fog_probability", "castle_probability"]])
```

8.3 観測ログ入力UI（サンプル）
- 日付・霧発生有無・天空の城可視性・メモを1画面で入力
- `st.form`＋`st.toggle`＋`st.data_editor` を使用し、保存ボタンで `history.csv` を即時更新
- 入力完了後は最新ステータスと未入力日のリストを表示して抜け漏れを防止

```python
with st.form("observation_form", clear_on_submit=True):
    target_date = st.date_input("観測日")
    fog_flag = st.toggle("霧が発生した", value=True)
    castle_flag = st.toggle("天空の城が見えた", value=True)
    note = st.text_input("メモ", "")
    submitted = st.form_submit_button("保存")

if submitted:
    new_row = {
        "date": target_date,
        "fog_observed": int(fog_flag),
        "castle_visible": int(castle_flag),
        "note": note,
    }
    df = pd.read_csv("data/history.csv")
    df = pd.concat([df, pd.DataFrame([new_row])]).drop_duplicates(subset=["date"], keep="last")
    df.to_csv("data/history.csv", index=False)
    st.success("観測ログを更新しました")
```

8.4 手動データ取得トリガー
- `st.button("最新予報を再計算")` を押下時に `subprocess.run(["python", "main.py"], check=True)` などでパイプラインを実行
- 実行結果メッセージやエラーログをダッシュボードに表示し、完了後に `feed.json`／`history.csv` を再読込して反映

```python
if st.button("最新予報を再計算", type="primary"):
    try:
        subprocess.run(["python", "main.py"], check=True)
        st.success("予報を更新しました")
        st.experimental_rerun()
    except subprocess.CalledProcessError as exc:
        st.error(f"更新に失敗しました: {exc}")
```
9. 環境設計
9.1 Docker実行環境（標準）
項目	設定
ホストOS	macOS（外付けHDD上のワークスペース）
コンテナベースイメージ	python:3.11-slim
依存導入	`pip install -r requirements.txt`（コンテナ内）
永続化	`.:/app` をマウントし data/・model/ をホスト側に保持
自動実行	`scheduler.py` を常駐させて平日16:00に main.py を起動

9.2 ローカル実行（任意）
項目	設定
OS	macOS / Windows 10+ / Linux
Python	3.11+
メモリ	4GB以上推奨
ライブラリ管理	仮想環境＋requirements.txt（必要に応じて）
自動実行	APScheduler を組み込んだ `scheduler.py` を直接起動

9.3 Docker構成ファイル
Dockerfile

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY . /app
RUN pip install -r requirements.txt
EXPOSE 8000 8501
CMD ["bash", "entrypoint.sh"]
```

`entrypoint.sh` では `scheduler.py`（APScheduler 常駐）と `uvicorn`／`streamlit` を並列起動する。

docker-compose.yml

```yaml
version: "3"
services:
  dashboard:
    build: .
    command: ["streamlit", "run", "dashboard.py", "--server.port=8501", "--server.address=0.0.0.0"]
    ports:
      - "8501:8501"
    volumes:
      - .:/app
    restart: unless-stopped
  scheduler:
    build: .
    command: ["python", "scheduler.py"]
    environment:
      - TZ=Asia/Tokyo
    volumes:
      - .:/app
    restart: unless-stopped
```
entrypoint.sh（例）

```bash
#!/bin/bash
set -e

python scheduler.py &
uvicorn api_server:app --host 0.0.0.0 --port 8000 &
streamlit run dashboard.py --server.port=8501 --server.address=0.0.0.0
wait
```
10. 運用・保守設計
項目	内容
スケジュール実行	営業日16:00に scheduler.py が main.py を起動
モデル更新	月1回再学習（history.csv使用）
ログ保存	出力結果・エラー履歴（通知は将来拡張）
バックアップ	model/・data/・backups/ を定期バックアップ
モニタリング	スケジューラログ・ダッシュボード操作ログ
バージョン管理	GitHub（リポジトリ名：skycastle-ai）

11. セキュリティ・ライセンス
項目	内容
メール情報	.envに暗号化保存
外部API	HTTPS通信（Open-Meteo）
ライブラリライセンス	MIT／BSD 3-Clause／Apache 2.0
データ	非個人情報のみ（気象データ）
公開条件	教育・観光・研究用途のオープン利用可

12. 今後の技術拡張
区分	概要
モデル強化	CNN／LSTMによる時系列予測
クラウド展開	AWS Lambda／Render／Cloud Run 対応
IoT連携	気温・湿度センサーとの実測比較
自動投稿	SNS API連携（X, Instagram）
多地点化	勝山・白山など周辺展開

13. 管理情報
項目	内容
文書名	SkyCastle AI 技術設計書
バージョン	v2.0
作成日	2025-10-29
最終更新日	2026-09-24
作成者	SkyCastle Dev Team
監修	ChatGPT（GPT-5）
関連文書	docs/01_Specification_SkyCastle.md / docs/03_Development_Guide_CodeX.md

📘 本書は SkyCastle AI システムの技術設計書ドラフトです。内容は変更される可能性があり、引用・転用はプロジェクト関係者の合意を得た場合のみ許可します。
