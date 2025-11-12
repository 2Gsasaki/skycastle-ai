# 🧰 SkyCastle AI ― 開発手順書（CodeX対応）
## 03_Development_Guide_CodeX.md

---

## 1. 文書概要

**目的：**  
本書は「SkyCastle AI（越前大野・天空の城出現予測AI）」を  
CodeX や ChatGPT＋VSCode 環境で開発・運用するための実装ガイドである。  
AI開発支援ツールを活用して、仕様書・設計書に基づいたスクリプトを段階的に生成する。

**関連文書：**
- `docs/01_Specification_SkyCastle.md`（要件定義書）
- `docs/02_Technical_Design_SkyCastle.md`（技術設計書）

**作成日：** 2025-10-29  
**作成者：** SkyCastle Dev Team  
**監修：** ChatGPT（GPT-5）

---

## 2. 開発環境準備

### 2.1 Dockerベースの開発

- プロジェクトは外付けHDD上に配置し、Docker コンテナ内で開発・実行する。  
- ホストには Docker Desktop（または互換ツール）と `docker compose` のみをインストールし、Python ライブラリはすべてコンテナ内に導入する。  
- ローカルで `venv` を作成したりライブラリを直接インストールする必要はない。

### 2.2 コンテナの初期セットアップ

```bash
docker compose build
```

※ `requirements.txt` はリポジトリに含めておき、`Dockerfile` の `pip install -r requirements.txt` で依存関係を導入する。Mac 側の Python には触れない。

推奨ライブラリ一覧（requirements.txt に記載）

| ライブラリ名 | 何をするもの？ | 使う場面 |
|--------------|----------------|-----------|
| pandas | 表（CSVなど）の読み書き・計算が得意なツール | 気象データや履歴ファイルを扱うとき |
| numpy | 数学の基本計算を高速にこなすツール | 露点計算などの数式処理 |
| lightgbm | 決定木ベースの機械学習ライブラリ | 霧発生／天空の城成立の予測モデル |
| scikit-learn | 学習データの分割や評価を助けるツール | モデル学習や評価の補助 |
| streamlit | Webダッシュボードを簡単に作れるツール | 予測結果を表示する画面 |
| fastapi | API（外部から呼べる窓口）を作るツール | 予測結果を他システムに返すとき |
| uvicorn | FastAPI を動かすためのサーバー | API を起動するとき |
| requests | Web API からデータを取ってくる道具 | Open-Meteo から天気データを取得する |
| python-dotenv | `.env` から設定情報を読み込む道具 | 設定値や秘密情報を環境変数で管理するとき |
| joblib | 学習したモデルを保存・読み込みする道具 | LightGBM モデルをファイル化するとき |
| opencv-python（任意） | 画像処理ライブラリ | 将来の霧・天空の城画像解析 |
| yagmail（任意） | Gmail でメール送信を楽にしてくれる道具 | 将来のメール通知機能 |

### 2.3 ディレクトリ構成（外付けHDD内）

```text
skycastle-ai/
 ├── docs/
 │    ├── 01_Specification_SkyCastle.md
 │    ├── 02_Technical_Design_SkyCastle.md
 │    └── 03_Development_Guide_CodeX.md
 ├── data/
 │    ├── weather.csv
 │    ├── history.csv
 │    ├── feed.json
 │    └── fog_result.json
 ├── model/
 │    ├── skycastle_fog.pkl
 │    └── skycastle_castle.pkl
 ├── main.py
 ├── fetch_weather.py
 ├── score_fog.py
 ├── train_model.py
 ├── predict_model.py
 ├── api_server.py
 ├── dashboard.py
 ├── requirements.txt
 ├── .env
 ├── README_SkyCastle_CodeX.md
 └── logs/
      └── execution.log
```
※ 将来拡張として `mailer.py`（メール通知）や `vision_fogdetector.py`（画像解析）を追加予定。
※ 既存のMarkdownドキュメント（仕様書・設計書・開発ガイド）は `docs/` フォルダにまとめて配置する。

### 2.4 コンテナ内でのコマンド実行
- すべてのスクリプト実行・テストは `docker compose run --rm dashboard python xxx.py` のように、`dashboard` イメージを使って行う。  
  例：`docker compose run --rm dashboard python fetch_weather.py`
- Streamlit や API を立ち上げるときは `docker compose up dashboard` を利用（`Ctrl+C` で停止）。  
- スケジューラを常駐させるときは `docker compose up scheduler` を利用し、停止は `docker compose stop scheduler`。

4. 開発ステップとAIプロンプト例
各ステップは CodeX にコピーペーストして送信すれば
自動的に必要なPythonスクリプトを生成できるようになっている。

🧩 ステップ 1：天気データ取得スクリプト（fetch_weather.py）
目的：
Open-Meteo APIから翌朝（5〜8時）の気象データを取得し、平均化して data/weather.csv に保存。

CodeXへの指示：

「Open-Meteo APIを使って越前大野（35.98,136.49）の5〜8時の気温・湿度・風速・雲量・降水量を取得し、平均化して weather.csv に保存するPythonコードを書いて。」

出力ファイル：
fetch_weather.py

想定出力CSV：

```csv
date,temp,humidity,wind,cloud,rain
2025-10-30,7.2,93,0.8,25,0.5
```
実行コマンド例：
```bash
docker compose run --rm dashboard python fetch_weather.py
```

🗓️ 拡張：16日間早朝予報バッチ（fetch_forecast_window.py）
目的：
Open-Meteo の同APIから今日を含む最大16日分の 5〜8時平均値をまとめて取得し、観光向けコンテンツなどで扱いやすい JSON (`data/forecast_window.json`) に保存する。

CodeXへの指示：

「Open-Meteo の hourly 予報を使って今日から最大16日分の 5〜8時平均を計算し、日付ごとの気温・湿度・風速・雲量・降水量を JSON リストで保存する fetch_forecast_window.py を作って。既存パイプラインに影響を与えない独立スクリプトにして、取得日数は引数で調整できるように。」

出力ファイル：
fetch_forecast_window.py

出力例（data/forecast_window.json）：

```json
[
  {
    "date": "2025-11-07",
    "temp": 9.1,
    "humidity": 85.3,
    "wind": 1.9,
    "cloud": 42.0,
    "rain": 0.0
  },
  {
    "date": "2025-11-08",
    "temp": 8.7,
    "humidity": 88.6,
    "wind": 2.2,
    "cloud": 55.4,
    "rain": 0.1
  }
]
```
実行コマンド例：
```bash
docker compose run --rm dashboard python fetch_forecast_window.py --days 16
```
補足：生成される JSON は dashboard/main.py の既存フローには触れず、静的ページや観光客向け公開サイトの素材として利用する。

🧠 拡張：16日分バッチ推論（predict_forecast_window.py）
目的：
`forecast_window.json` の気象値を既存 LightGBM モデル＋キャリブレーターで一括推論し、観光向けに使いやすい 16 日分の確率一覧 (`data/forecast_predictions.json`) を生成する。

CodeXへの指示：

「fetch_forecast_window.py が出力する forecast_window.json を読み込み、既存の skycastle_fog / skycastle_castle モデルとイベントキャリブレーターを使って各日の fog_probability・castle_probability・castle_event_probability を計算し、JSON リストとして保存する predict_forecast_window.py を作って。history.csv の最新行を参照してラグ特徴を補完し、日ごとの event 判定も付けること。」

出力ファイル：
predict_forecast_window.py

出力例（data/forecast_predictions.json）：

```json
{
  "generated_at": "2025-11-07T06:30:12+09:00",
  "predictions": [
    {
      "date": "2025-11-07",
      "temp": 9.1,
      "humidity": 85.3,
      "wind": 1.9,
      "cloud": 42.0,
      "rain": 0.0,
      "fog_probability": 0.78,
      "castle_probability": 0.61,
      "castle_event_probability": 0.55,
      "event": "Castle"
    }
  ]
}
```
実行コマンド例：
```bash
docker compose run --rm dashboard python predict_forecast_window.py
```
補足：出力は観光客向けサイトやサマリーメールなどで直接利用できる JSON とし、history.csv や feed.json には書き戻さない。
備考：history.csv に実測済みの行が存在する日付は、その値（気温・湿度・確率など）で上書きしてから保存するため、ダッシュボードの最新結果と観光向け JSON が一致する。`generated_at` には推論完了時刻（JST）が入り、フロントエンドで「最終更新（推論生成）」として利用される。

🌄 公開用 16日予報ページ（public/forecast.html）
目的：
`forecast_predictions.json` を読み込み、観光客向けに天空の城出現確率をカード形式で表示する静的HTMLを提供する。ランキング化されたカードで Castle チャンスを視覚化し、気温・湿度などの指標も併記する。

CodeXへの指示：

「public/forecast.html を作成して、data/forecast_predictions.json を fetch し、天空の城出現率が高い順にカードを表示するページを作って。城イベントは強調表示し、値が存在しないときはエラーメッセージを出すように。」

出力ファイル：
public/forecast.html

利用方法：
ブラウザで `public/forecast.html` を開くだけで、最新の `forecast_predictions.json` を参照してUIを描画。ブラウザの制限により `file://` で直接開くと読み込めないため、プロジェクトルートで `python3 -m http.server`（または環境に応じて `python -m http.server`）を実行し、`http://localhost:8000/public/forecast.html` のように HTTP 経由でアクセスする。ホスティング時は同階層（または相対パス）に JSON を配置する。`generated_at` が含まれる JSON ではその時刻を「最終更新（推論生成）」として表示し、旧形式（配列のみ）の JSON でも従来どおり描画できる。
備考：`fetch_forecast_window.py` が `weathercode` を保存するため、再実行すると予報カード上に天気アイコン（快晴・曇り・雨 など）が表示されます。
🧮 ステップ 2：露点・スコア算出スクリプト（score_fog.py）
目的：
気温と湿度から露点を計算し、露点差・風速・雲量・降水量を用いて「霧スコア（0〜100）」と「天空の城スコア（0〜100）」を算出。

CodeXへの指示：

「weather.csv を読み込み、露点温度を計算して露点差(T−Td)・風速・雲量・降水量を加味した霧スコアと天空の城スコアを算出し、結果を feed.json に出力するPythonコードを書いて。」

出力ファイル：
score_fog.py

出力例（feed.json）：

```json
{"date": "2025-10-30", "fog_score": 88, "castle_score": 74}
```
実行コマンド例：
```bash
docker compose run --rm dashboard python score_fog.py
```
🤖 ステップ 3：AI学習スクリプト（train_model.py）
目的：
過去の天気データ（history.csv）を用いて、霧発生モデル（FogModel）と天空の城成立モデル（CastleModel）の2本を LightGBM で学習し、さらに両モデルの出力を組み合わせた「天空の城出現率（総合）」キャリブレーターを学習する。

CodeXへの指示：

「history.csv のデータから fog_observed・castle_visible をラベルにして、霧発生モデルと城成立モデルの2本の LightGBM を学習し、model/skycastle_fog.pkl と model/skycastle_castle.pkl に保存するPythonコードを書いて。さらに両モデルの予測確率を特徴量にしたロジスティック回帰で Castle イベントの総合出現率を学習し、model/skycastle_event_calibrator.pkl に保存し、history.csv の `castle_event_probability` をバックフィルする処理も追加して。」

出力ファイル：
train_model.py

学習データ例：

```csv
date,temp,humidity,wind,cloud,rain,fog_observed,castle_visible
2025-10-25,6.9,94,0.8,30,1.0,1,1
2025-10-26,9.3,82,2.1,10,0.0,0,0
```
実行コマンド例：
```bash
docker compose run --rm dashboard python train_model.py
```
補足：ポジティブサンプル（霧=1 かつ 城=1の日）が不足している場合はキャリブレーターが削除され、推論時は霧・城の確率積をフォールバックとして使用する。
🔮 ステップ 4：AI推論スクリプト（predict_model.py）
目的：
学習済みの霧発生モデル・城成立モデルを読み込み、当日の気象データから翌朝の霧発生確率と城成立確率を推論し、キャリブレーターで総合出現率を算出してイベント判定を付与する。

CodeXへの指示：

「train_model.py で保存した2本の LightGBM モデルを読み込み、weather.csv を入力して霧発生確率と城成立確率を計算し、キャリブレーターで天空の城出現率（総合）を推定した上で、feed.json に fog_probability・castle_probability・castle_event_probability・event を追記するPythonコードを書いて。」

出力ファイル：
predict_model.py

出力例：

```json
{"date":"2025-10-30","fog_score":88,"castle_score":74,"fog_probability":0.81,"castle_probability":0.58,"castle_event_probability":0.64,"event":"Castle"}
```
実行コマンド例：
```bash
docker compose run --rm dashboard python predict_model.py
```
📈 ステップ 5：Streamlitダッシュボード（dashboard.py）
目的：
AI予測結果（feed.json）・履歴（history.csv）を表示し、霧と天空の城の2指標に加えて総合出現率の推移を可視化。さらに、管理者が1画面で観測ログを追記・編集できるフォームを組み込む（画像解析は将来拡張時に `fog_result.json` を参照）。

CodeXへの指示：

「Streamlitで feed.json の fog_probability・castle_probability・castle_event_probability をメトリクス表示し、 history.csv の推移グラフと観測ログ編集フォーム（st.form＋st.data_editor）を1ページに配置した dashboard.py を作成して。history.csv の `castle_event_probability` を折れ線グラフに追加し、テーブル編集画面にも同列を表示して。」

出力ファイル：
dashboard.py

起動コマンド：

```bash
docker compose up dashboard
```

観測ログフォームの実装例：

```python
with st.form("observation_form", clear_on_submit=True):
    target_date = st.date_input("観測日")
    fog_flag = st.toggle("霧が発生した", value=True)
    castle_flag = st.toggle("天空の城が見えた", value=True)
    note = st.text_input("メモ", "")
    submitted = st.form_submit_button("保存")

if submitted:
    df = pd.read_csv("data/history.csv")
    df.loc[df["date"] == str(target_date), ["fog_observed", "castle_visible", "note"]] = [
        int(fog_flag),
        int(castle_flag),
        note,
    ]
    if str(target_date) not in df["date"].values:
        df = pd.concat([df, pd.DataFrame([{
            "date": target_date,
            "fog_observed": int(fog_flag),
            "castle_visible": int(castle_flag),
            "note": note,
        }])])
    df.to_csv("data/history.csv", index=False)
    st.success("観測ログを保存しました")
```

手動更新ボタンの実装例：

```python
import subprocess

if st.button("最新予報を再計算", type="primary"):
    try:
        subprocess.run(["python", "main.py"], check=True)
        st.success("予報を更新しました")
        st.experimental_rerun()
    except subprocess.CalledProcessError as exc:
        st.error(f"更新に失敗しました: {exc}")
```
🌐 ステップ 6：APIサーバー構築（api_server.py）
目的：
他システムから参照できるREST APIを提供。

CodeXへの指示：

「FastAPIを使って /api/predict/tomorrow で feed.json（fog_probability・castle_probability・event など）を返し、/api/fog で fog_result.json を提供するAPIを作成して。uvicornで実行できるように。」

出力ファイル：
api_server.py

起動コマンド：

```bash
docker compose run --rm dashboard uvicorn api_server:app --reload --host 0.0.0.0 --port 8000
```
🪄 ステップ 7：統合スクリプト（main.py）
目的：
全処理（データ取得→スコア算出→二段推論→履歴更新）を順に実行。

CodeXへの指示：

「fetch_weather, score_fog, predict_model を順番に実行し、結果を history.csv に追記してログを残す main.py を作成して。」

出力ファイル：
main.py

実行例：

```bash
docker compose run --rm dashboard python main.py
```
⏱️ ステップ 8：スケジューラ（scheduler.py）
目的：
コンテナ起動中に平日16:00へ自動で `main.py` を実行し、必要に応じてダッシュボードやAPIを並列起動する。

CodeXへの指示：

「APScheduler を使って平日16:00に main.py を実行する scheduler.py を作成して。Docker内で常駐できるように無限ループで待機し、ログ出力も残すように。」

出力ファイル：
scheduler.py

実行例（ローカルテスト）：

```bash
docker compose up scheduler
```

📬 将来拡張ステップ（任意）
- mailer.py：SMTPやSNS APIを利用して予報結果を自動通知
- vision_fogdetector.py：OpenCV＋CNNで霧／天空の城を自動判定し `fog_result.json` を生成
- main.py／dashboard.py／scheduler.py にフックを追加して、上記機能と連携できるようにする

5. 自動実行設定（スケジューリング）
- ローカル実行：`python scheduler.py` を起動すると APScheduler が平日16:00に `main.py` を呼び出す。終了は `Ctrl+C`。
- Docker運用：`docker compose up -d` で `scheduler` サービスを常駐起動。停止は `docker compose stop scheduler`。
- ログ：`logs/scheduler.log` に実行結果を追記し、失敗時は画面とログで確認する。

6. エラーログ管理
すべてのスクリプトはログを logs/execution.log に追記。スケジューラは logs/scheduler.log を追加で利用。

7. テスト手順
項目	方法	成功条件
API通信テスト	fetch_weather.py 単体実行	weather.csv が生成される
露点計算テスト	score_fog.py 実行	feed.json に fog_score / castle_score が出力される
AI推論テスト	predict_model.py 実行	fog_probability / castle_probability が0〜1の範囲で出力される
ダッシュボード確認	streamlit run dashboard.py	グラフが正しく表示される
スケジューラ確認	python scheduler.py	ジョブ登録ログと main.py 実行ログが出力される

（将来拡張）
画像判定テスト	vision_fogdetector.py 実行	fog_result.json に fog_detected / castle_visible が更新される
メール送信テスト	mailer.py 実行	指定アドレスに通知が届く

8. 今後の拡張ステップ（上級開発）
ステップ	内容
9	メール通知機能を追加（mailer.py＋SMTP/SNS）
10	Fog DetectorにCNN学習機能を追加（vision_fogdetector.py）
11	StreamlitとAPIを統合しWeb配信（Render/AWS）
12	自動再学習ジョブを追加（APScheduler + train_model）
13	SNS自動投稿機能を追加（X API連携）

9. ファイル生成履歴（確認用）
ステップ	ファイル	状態	備考
1	fetch_weather.py	✅ 完了	API取得
2	score_fog.py	✅ 完了	スコア計算
3	train_model.py	✅ 完了	モデル学習
4	predict_model.py	✅ 完了	推論
5	dashboard.py	✅ 完了	Web可視化（手動更新・観測入力）
6	api_server.py	✅ 完了	REST提供
7	main.py	✅ 完了	全体統合
8	scheduler.py	✅ 完了	自動実行

（将来拡張）
- mailer.py（メール通知）
- vision_fogdetector.py（画像解析）

10. 開発ヒント（CodeX利用時）
1ステップ＝1プロンプト が基本。

1回の生成結果を必ずローカルに保存して確認。

CodeXに「次に何を作る？」と聞かせると自動で前後関係を補完可能。

修正時は # update: コメントを明示してプロンプト送信。

StreamlitやFastAPIのポート競合に注意（8501と8000を併用）。

11. 管理情報
項目	内容
文書名	SkyCastle AI 開発手順書（CodeX対応）
バージョン	v1.0
作成者	SkyCastle Dev Team
作成日	2025-10-29
監修	ChatGPT（GPT-5）
関連文書	docs/01_Specification_SkyCastle.md／docs/02_Technical_Design_SkyCastle.md

📘 この開発手順書は、SkyCastle AI を段階的に整備するための開発メモです。内容は随時更新されるため、最新情報はリポジトリ全体のドキュメントを併せて参照してください。
