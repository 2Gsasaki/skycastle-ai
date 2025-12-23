# GitHub Pages ＋ GitHub Actions 手順書

Netlify 連携を廃止し、GitHub Pages だけで公開する構成です。無料枠で自動更新を回し、`public/forecast.html` を `https://2gsasaki.github.io/skycastle-ai/forecast.html` から配信する前提に書き換えています。

---

## 0. 事前準備

1. GitHub リポジトリ：`skycastle-ai` を GitHub に置く（既存のものを使用）。  
2. GitHub Pages を有効化：Settings → Pages → Source=`Deploy from a branch`、Branch=`gh-pages`、Folder=`/(root)`。  
   - `gh-pages` ブランチが無い場合は空のブランチを作成しておく（最初はActionsが自動で上書き）。  
3. Actions がコミットできるよう、ブランチ保護で bot を許可する（必要なら）。

---

## 1. 公開構成（GitHub Pages）

- 公開物は `public/` 配下のみ。`public/forecast.html` と `public/data/forecast_predictions.json` を配信する。  
- GitHub Pages 用の成果物は、Actions が `public/` の中身を `gh-pages` ブランチに反映して公開する。  
- Netlify 用の設定や Secrets は不要（削除済みで問題なし）。

---

## 2. GitHub Actions のスケジュール（Netlify無し版）

`.github/workflows/skycastle-auto.yml` で以下のスケジュールを運用：

- 0:00 JST（UTC 15:00）：14日予報だけ更新（必ず実行、キャンセルしない）。  
- 11:05 JST（UTC 02:05）：実測が揃う時間に履歴更新＋予報（必ず実行、キャンセルしない）。  
- 予報だけ更新（履歴は触らない）：14:05 / 17:05 / 20:05 / 22:30 / 02:30 / 04:30 JST。重なったら古いジョブをキャンセル。  
- 全ジョブとも Netlify Hook 呼び出しは削除済み。

`concurrency` 設定で重複を防止：
- 0:00 用：`group: skycastle-0000`、`cancel-in-progress: false`  
- 11:05 用：`group: skycastle-1105`、`cancel-in-progress: false`  
- 予報のみ：`group: skycastle-forecast`、`cancel-in-progress: true`

---

## 3. GitHub Pages へのデプロイ

`.github/workflows/deploy-gh-pages.yml` が、`main` への push（または workflow_dispatch）で `public/` を `gh-pages` へ同期し、Pages に公開する。Netlify は一切不要。もし Pages の反映が遅い場合は、手動で `Deployments` から再デプロイを実行する。

---

## 4. 運用メモ（Netlifyからの移行済み）

- Netlify 用の Secrets（`NETLIFY_BUILD_HOOK_URL` など）は不要。登録していても使われない。  
- データ更新・予報生成はこれまで通り Actions が実行し、`public/data/forecast_predictions.json` を更新する。  
- 公開URLは GitHub Pages の `https://2gsasaki.github.io/skycastle-ai/forecast.html`。DocsやREADMEもこの前提に統一。

---

## 5. トラブルシュート

- 0時・11時のジョブが動かない：Actions のスケジュールが有効か、リポジトリ設定で Actions が許可されているか確認。  
- Pages が更新されない：`gh-pages` ブランチが最新か、`deploy-gh-pages.yml` の実行ログを確認。  
- 重複実行の心配：`skycastle-forecast` グループで古いジョブをキャンセルする設定になっている。  
- 公開URLが404：Pages 設定が `gh-pages` ブランチ、`/(root)` になっているか確認。
