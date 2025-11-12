# Netlify ＋ GitHub Actions 無料構成 手順書

IT リテラシーに自信がなくても順番に進められるよう、やることを 1 つずつ整理しています。  
ゴール：GitHub Actions の無料ランナーで定期バッチを動かし、Netlify で `public/forecast.html` を公開する。Web ダッシュボード（観測ログ入力用）は必要に応じて別途ホストする。

> **開発中の注意**  
> この手順書は現在も更新中です。ジョブ構成や公開先（Netlify/GitHub Pages）は今後変更される可能性があります。最新のフローは README も併せて確認してください。

---

## 0. 事前準備

1. **GitHub リポジトリを用意**：このプロジェクト（`skycastle-ai`）を GitHub 上に Push しておく。無料枠でもプライベートで OK。  
   1. ターミナルで `cd /Volumes/IODATA/skycastle-ai` → `git init`。  
   2. `.gitignore` を作成し、`.DS_Store` や `data/*.csv`、`logs/` など追跡不要なファイルを記述。  
   3. Sourcetree の「既存のローカルリポジトリを追加」でこのフォルダを登録。  
   4. GitHub で Private リポジトリ（例：`skycastle-ai`）を README なしで作成。  
   5. Sourcetree の「リポジトリ設定 → リモート」で Name=`origin`、URL=GitHub の HTTPS URL を設定。  
   6. Sourcetree で `Initial commit` を作り、ローカル `main` ブランチを選択して `origin/main` へ Push。
2. **Netlify アカウント作成**：<https://www.netlify.com/> にアクセスし、GitHub 連携を有効化。  
3. **GitHub Actions の準備**：リポジトリの Settings → Secrets and variables → Actions に Netlify の Deploy Hook URL（`NETLIFY_BUILD_HOOK_URL` など）を登録する。

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
6. 公開 URL 例：`https://skycastle-ai.netlify.app/forecast.html`。`public/data/forecast_predictions.json` を配置し、後述の GitHub Actions で更新 → Netlify Deploy Hook を叩いて最新化する運用にする。

---

## 2. GitHub Actions で定期バッチを自動化

`.github/workflows/skycastle-auto.yml` を作成し、JST 11/14/17/20 時に `main.py` と 14 日予報の更新を行う。さらに毎日 0:00 JST に 14 日予報だけを更新するジョブを追加する。

```yaml
name: SkyCastle Daily Automation

on:
  schedule:
    - cron: "5 2 * * *"   # JST 11:05
    - cron: "5 5 * * *"   # JST 14:05
    - cron: "5 8 * * *"   # JST 17:05
    - cron: "5 11 * * *"  # JST 20:05
    - cron: "0 15 * * *"  # JST 00:00
  workflow_dispatch:

jobs:
  daily-run:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -r requirements.txt
      - name: Determine JST date
        id: dates
        run: |
          echo "today_jst=$(TZ=Asia/Tokyo date +%F)" >> "$GITHUB_OUTPUT"
          echo "timestamp=$(TZ=Asia/Tokyo date -Iseconds)" >> "$GITHUB_OUTPUT"
      - name: Archive today's observation
        run: python main.py --date "${{ steps.dates.outputs.today_jst }}"
      - name: Run forecast pipeline
        run: python main.py
      - name: Refresh 14-day window
        run: |
          python fetch_forecast_window.py --days 14
          python predict_forecast_window.py
      - name: Copy JSON for Netlify
        run: |
          mkdir -p public/data
          cp data/forecast_predictions.json public/data/forecast_predictions.json
      - name: Commit & push
        run: |
          if git status --short | grep -qv '^??'; then
            git config user.name "github-actions[bot]"
            git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
            git add -A
            git commit -m "chore: automated update at ${{ steps.dates.outputs.timestamp }}"
            git push
          else
            echo "Nothing to commit."
          fi
      - name: Trigger Netlify deploy
        if: secrets.NETLIFY_BUILD_HOOK_URL != ''
        run: curl -X POST "${{ secrets.NETLIFY_BUILD_HOOK_URL }}"

  midnight-forecast:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    if: github.event_name == 'workflow_dispatch' || github.event.schedule == '0 15 * * *'
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -r requirements.txt
      - run: python fetch_forecast_window.py --days 14
      - run: |
          python predict_forecast_window.py
          mkdir -p public/data
          cp data/forecast_predictions.json public/data/forecast_predictions.json
      - name: Commit & push
        run: |
          if git status --short | grep -qv '^??'; then
            git config user.name "github-actions[bot]"
            git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
            git add -A
            git commit -m "chore: midnight forecast refresh"
            git push
          else
            echo "Nothing to commit."
          fi
      - name: Trigger Netlify deploy
        if: secrets.NETLIFY_BUILD_HOOK_URL != ''
        run: curl -X POST "${{ secrets.NETLIFY_BUILD_HOOK_URL }}"
```

これで GitHub Actions の無料ランナーが cron 代わりになり、Docker や Render のジョブを使わずに自動更新できる。

---

## 3. Netlify を自動更新（Deploy Hook）

GitHub Actions が JSON を書き換えたら、Netlify に「サイト再ビルド」を依頼する。Secrets に `NETLIFY_BUILD_HOOK_URL` を登録し、上記ワークフローの `Trigger Netlify deploy` ステップで `curl -X POST ...` を呼び出す。これで Actions 成功 → Netlify が `public/` を再配信 → `forecast.html` が最新 JSON を読む流れが自動化される。

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

## 4. 運用メモ

- **観測ログ（Streamlit ダッシュボード）**：Render Free の Web Service で `dashboard.py` を公開して観測ログを入力可能。設定の流れは以下の通り。  
  1. <https://render.com/> で GitHub ログイン → Workspace（例：Secondgate Team）を作成。  
  2. 「New +」→「Web Service」→ 言語 `Python 3` を選択。Repository は `skycastle-ai`、Branch は `main`、Root Directory は空欄。  
  3. Build Command：`pip install -r requirements.txt`、Start Command：`streamlit run dashboard.py --server.port $PORT --server.address 0.0.0.0`。  
  4. Instance Type：`Free`（15分無アクセスでスリープ）。`Deploy Web Service` を押すと URL が発行される。  
  5. ダッシュボードで保存した `data/history.csv` は GitHub に pull/push しておくと Actions／Netlify と整合が取れる。  
- **ローカルで観測ログを更新する手順**  
  1. Sourcetree で `Pull` を実行して GitHub 上の最新 `data/history.csv` を取得する。  
  2. ローカル環境で `streamlit run dashboard.py`（またはエディタ）を使い、霧/天空の実績やメモを編集する。  
  3. 変更後の `history.csv` を保存し、Sourcetree で `Stage` → `Commit` → `Push`。  
  4. GitHub Actions が次のスケジュールで `history.csv` や各 JSON を再計算し、bot が自動的に `main` へ commit/push → Netlify が最新データを配信する。  
- **GitHub Actions の権限**：`contents: write` を付けたので、ブランチ保護ルールがある場合は bot の push を許可する。  
- **Netlify Hook**：Secrets に登録し忘れると自動デプロイされない。必要なら複数 Hook を使い分ける。  
- **トラブル時**：Actions のログと Netlify の Deploy log を確認。手動で `python main.py` を動かしてから push し直せば復旧できる。

---

この順番で進めれば、無料枠のまま「自動で JSON が更新され、Netlify の `public/forecast.html` が最新を表示する」仕組みが構築できます。

---

## 5. GitHub Pages で `public/` をホストする手順（Netlify の代替案）

Netlify の無料枠（1 か月 300 クレジット＝本番デプロイ 20 回）だと、1 日 5 回の自動デプロイで 4 日ほどで枯渇してしまう。そこで GitHub Pages に切り替え、`public/` の中身だけを公開するフローを追加した。以下の手順でセットアップできる。

1. **公開専用ブランチ `gh-pages` を用意（最初の 1 回だけ）**  
   - GitHub のリポジトリ画面 → `<> Code` タブの `main` ブランチ表示 → `View all branches` → `New branch` で `gh-pages` を作成。ベースは `main` のままで OK。  
   - ローカルで触る必要はない。以後は GitHub Actions が `public/` の内容を自動的に `gh-pages` へ上書きするため、普段の開発は `main` だけ扱えばよい。

2. **GitHub Pages を `gh-pages` ブランチに設定**  
   - GitHub → `Settings` → `Pages` → Source を `Deploy from a branch` にし、Branch=`gh-pages`、Folder=`/(root)` を選択 → Save。  
   - これで `https://<user>.github.io/<repo>/` が発行される。`public/forecast.html` や `public/data/forecast_predictions.json` など `public` 配下だけが配信対象になる（ソースコードは非公開）。

3. **GitHub Actions で `public` → `gh-pages` を自動デプロイする**  
   - `.github/workflows/deploy-gh-pages.yml`（リポジトリに追加済み）で以下のように設定している。`main` へ Push されたタイミング、または手動実行で `public/` の中身だけを `gh-pages` へ反映する。
   ```yaml
   name: Deploy public to GitHub Pages

   on:
     push:
       branches: [main]
     workflow_dispatch:

   jobs:
     deploy:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v4
         - name: Copy public -> dist
           run: |
             rm -rf dist
             cp -R public dist
         - name: Deploy to gh-pages
           uses: peaceiris/actions-gh-pages@v3
           with:
             github_token: ${{ secrets.GITHUB_TOKEN }}
             publish_branch: gh-pages
             publish_dir: dist
   ```
   - `public` 以外のソースは `gh-pages` へコピーしないため、公開側からは参照できない。手元で `public/forecast.html` を修正 → `main` に Push → 数十秒後に Pages も更新、という流れになる。

4. **動作確認**  
   - GitHub Actions の `Deploy public to GitHub Pages` が緑色になることを確認。  
   - `https://<user>.github.io/<repo>/forecast.html` へアクセスし、最新の JSON が読み込まれているか確認する。

この構成なら Netlify のクレジット消費を気にせず 1 日 5 回以上の更新を継続できる。
