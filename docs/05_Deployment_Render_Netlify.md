# Render ＋ Netlify 無料構成 手順書

IT リテラシーに自信がなくても順番に進められるよう、やることを 1 つずつ整理しています。  
ゴール：Render 無料枠でバックエンド（定期バッチ＋ダッシュボード）を動かし、Netlify で `public/forecast.html` を公開する。

---

## 0. 事前準備

1. **GitHub リポジトリを用意**：このプロジェクト（`skycastle-ai`）を GitHub 上に Push しておく。無料枠でもプライベートで OK。  
2. **Render アカウント作成**：<https://render.com/> にアクセスし、GitHub と連携しておく。  
3. **Netlify アカウント作成**：<https://www.netlify.com/> にアクセスし、GitHub 連携を有効化。

---

## 1. Netlify で静的サイトを公開

1. Netlify ダッシュボードで「Add new site」→「Import an existing project」。  
2. GitHub から `skycastle-ai` リポジトリを選択。  
3. Build コマンド：`npm run build` などは不要なので空欄。Publish ディレクトリを `public` に設定。  
4. デプロイ完了後、サイト URL（例: `https://your-site.netlify.app`）を控えておく。  
   - この URL で `public/forecast.html` が公開され、後で JSON を読み込める状態になる。

---

## 2. Render で Web Service（ダッシュボード用）を作成

1. Render ダッシュボード →「New +」→「Web Service」。  
2. リポジトリに `skycastle-ai` を選び、**Free プラン**を選択。  
3. Build Command：`pip install -r requirements.txt`（初回ビルド時）  
4. Start Command：`streamlit run dashboard.py --server.port $PORT --server.address 0.0.0.0`  
5. デプロイ後、URL（例: `https://skycastle-dashboard.onrender.com`）を控える。  
   - 誰かがアクセスすると起動し、SkyCastle AI ダッシュボードで観測ログを入力できる。  
   - 無料枠は 15 分アクセスが無いとスリープする点に注意。

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
