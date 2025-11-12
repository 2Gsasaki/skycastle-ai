# SkyCastle AI

天空の城（越前大野）の雲海・天空出現を予測する自動化パイプラインです。  
GitHub Actions で気象データを取得・学習済みモデルで推論し、`public/forecast.html` から公開用 JSON を参照します。

## Current Status (WIP)

- **現在開発中／仕様変更中**：機能やディレクトリ構成が頻繁に変わる可能性があります。  
- **動作の安定性は未保証**：GitHub Actions、Netlify/GitHub Pages などの連携を調整中です。  
- 公開サイト・API のレスポンス形式も予告なく変わる場合があります。

## Getting Started

セットアップやデプロイ手順は `docs/` 以下（特に `docs/05_Deployment_Actions_Netlify.md`）にまとめています。  
ローカル実行や自動ジョブの詳細は順次更新予定です。

## License & Contributions

ライセンスは後日整理予定です。  
現在は社内検証フェーズのため、外部からの Issue／Pull Request は受け付けていません（詳細は `CONTRIBUTING.md` を参照）。
