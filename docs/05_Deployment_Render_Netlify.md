# Render ＋ Netlify 無料構成 手順書

IT リテラシーに自信がなくても順番に進められるよう、やることを 1 つずつ整理しています。  
ゴール：Render 無料枠でバックエンド（定期バッチ＋ダッシュボード）を動かし、Netlify で `public/forecast.html` を公開する。

---

## 0. 事前準備

1. **GitHub リポジトリを用意**：このプロジェクト（`skycastle-ai`）を GitHub 上に Push しておく。無料枠でもプライベートで OK。  
   1. ターミナルで `cd /Volumes/IODATA/skycastle-ai` → `git init`。  
   2. `.gitignore` を作成し、`.DS_Store` や `data/*.csv`、`logs/` など追跡不要なファイルを記述。  
   3. Sourcetree の「既存のローカルリポジトリを追加」でこのフォルダを登録。  
   4. GitHub で Private リポジトリ（例：`skycastle-ai`）を README なしで作成。  
   5. Sourcetree の「リポジトリ設定 → リモート」で Name=`origin`、URL=GitHub の HTTPS URL を設定。  
   6. Sourcetree で `Initial commit` を作り、ローカル `main` ブランチを選択して `origin/main` へ Push。
2. **Render アカウント作成**：<https://render.com/> にアクセスし、GitHub と連携しておく。  
3. **Netlify アカウント作成**：<https://www.netlify.com/> にアクセスし、GitHub 連携を有効化。

---

## 1. Netlify （ネットリファイ）で静的サイトを公開

1. Netlify に GitHub（2Gsasaki） アカウントでログインし、「Netlify Auth にメールアドレス読み取りを許可」する。  
2. ダッシュボードで「Add new site」→「Import an existing project」。  
3. GitHub から `skycastle-ai` リポジトリを選択（Netlify アプリの対象リポジトリに `skycastle-ai` を追加するのを忘れずに）。  
4. Build 設定は `Branch: main / Build command: 空欄 / Publish directory: public` で一旦デプロイ。 
「Deploy（デプロイ）」は、開発したアプリやサイトを利用者がアクセスできる環境へ配置して動かせる状態にすることです。
開発 → テスト → Deploy → 公開、という流れで使われ、Netlify の場合は「GitHub からコードを取り込み、ビルドしてネット上で公開する作業」を指しています。 
5. Python 依存のビルドを避けるため、リポジトリ直下に `netlify.toml` を作成して以下を記述：
   ```toml
   [build]
     base = "public"
     command = ""
     publish = "."
   ```
   コミット＆プッシュすると Netlify が再デプロイし、静的サイトとして成功する。  
6. 公開 URL 例：`https://skycastle-ai.netlify.app/forecast.html`。`public/data/forecast_predictions.json` を配置し、Render ジョブで更新 → Netlify Deploy Hook を叩いて最新化する運用にする。

---

## 2. Render で Web Service（ダッシュボード用）を作成

1. <https://render.com/> にアクセスし、GitHub でログイン → Workspace（例：Secondgate Team）を作成。  
2. 「New +」→「Web Service」→ 言語 `Python 3` を選択。  
3. Repository: `skycastle-ai`、Branch: `main`、Root Directory: 空欄（リポジトリ直下）。  
4. **Build Command**：`pip install -r requirements.txt`  
5. **Start Command**：`streamlit run dashboard.py --server.port $PORT --server.address 0.0.0.0`  
6. Instance Type は `Free` を選択（スリープ有り）。Environment Variables は未設定で OK。  
7. 「Deploy Web Service」を押し、完了後に表示される URL（例: `https://skycastle-dashboard.onrender.com`）を控える。アクセス時に自動起動し、ダッシュボードで観測ログを入力できる。

---

## 3. Render の Scheduled Jobs を設定（cron 代わり）

Render では Job ごとにコマンドとスケジュールを登録する。

### 3-1. 日中 4 回（11:00 / 14:00 / 17:00 / 20:00 JST）

各時間に以下の Job を作成（UTC で設定する必要があるので JST→UTC を変換：11時JST=02時UTC など）。

- コマンド：`python main.py`
- 目的：最新気象を取得 → スコア算出 → AI 予測 → `feed.json`/`history.csv` 更新 → Netlify 用 JSON も更新される

Render Job の設定例：

| JST | UTC (Render入力) | コマンド |
|-----|------------------|----------|
| 11:00 | 02:00 | `python main.py` |
| 14:00 | 05:00 | `python main.py` |
| 17:00 | 08:00 | `python main.py` |
| 20:00 | 11:00 | `python main.py` |

### 3-2. 日付切り替え時（00:00 JST）

1 日 1 回、翌日以降 14 日分の予報 JSON を生成。

- UTC 時刻：15:00 (前日の UTC)  
- コマンド：`bash -c "python fetch_forecast_window.py --days 14 && python predict_forecast_window.py"`

---

## 4. Netlify を自動更新（Deploy Hook）

Render の Job が JSON を書き換えたら、Netlify に「サイト再ビルド」を依頼する。

1. Netlify の Site Settings → Build & Deploy → Build hooks →「Add build hook」。  
   - Hook 名例：`update-forecast`  
   - Branch：`main`  
   - 発行された URL をコピー。
2. Render Job のコマンド末尾に curl を追加：  
   ```
   bash -c "python main.py && curl -X POST https://api.netlify.com/build_hooks/HOOK_ID"
   ```
   0 時ジョブにも同様に Hook を呼び出す。
3. これで Job 成功 → Netlify が `public/` を再配信 → `forecast.html` が最新 JSON を読む流れが自動化される。

---

## 5. 運用メモ

- **観測ログは手動**：雲海が見えたら Render Web Service（ダッシュボード）にアクセスし、観測ログを入力。  
- **無料枠の注意**：月 750 時間は 1 か月 31 日換算で常時稼働約 24 時間分。Scheduled Job は短時間なので問題なし。Web Service はアクセス時のみ稼働する構成にしておくと安心。  
- **トラブル時**：Render のログや Netlify Deploy log を確認。必要に応じて `main.py --date YYYY-MM-DD` をローカルで実行し、GitHub に成果物を Push → Netlify/Render に再デプロイ。

---

この順番で進めれば、無料枠のまま「自動で JSON が更新され、Netlify の `public/forecast.html` が最新を表示する」仕組みが構築できます。
