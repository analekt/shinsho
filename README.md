# OpenBD 新書新刊RSSフィードジェネレーター

## 概要

このプロジェクトは、[OpenBD API](https://openbd.jp/) を利用して、特定のCコード（主に「新書」カテゴリ）に合致する書籍情報を取得し、RSSフィード (`index.xml`) として生成・公開するものです。

GitHub Actions を利用して毎日自動的に実行され、差分更新により効率的に新刊情報を追跡します。

**公開フィードURL:** [https://analekt.github.io/shinsho/index.xml](https://analekt.github.io/shinsho/index.xml)
*(注意: このURLは、`analekt` ユーザーの `shinsho` リポジトリでGitHub Pagesが正しく設定されている場合の例です)*

## 機能

*   毎日定時（デフォルトは午前9時 JST）に自動実行
*   OpenBD API から全ISBNリストを取得
*   前回の実行結果と比較し、新規追加されたISBNのみを抽出（差分更新）
*   新規ISBNに対応する書籍詳細情報を取得
*   指定されたCコード（デフォルト: `02xx` 系、`SubjectSchemeIdentifier=78`）と有効な発売日に基づいて書籍をフィルタリング
*   フィルタリングされた書籍情報（最新 `MAX_FEED_ITEMS` 件）を含むRSS 2.0フィード (`index.xml`) を生成
*   生成されたフィードをGitHub Pagesに自動デプロイ

## 仕組み

1.  **GitHub Actions Workflow (`.github/workflows/generate_feed.yml`)**:
    *   スケジュール (`cron`) または手動 (`workflow_dispatch`) でトリガーされます。
    *   Python環境をセットアップし、必要なライブラリ (`requests`, `feedgen`, `pytz`) をインストールします。
    *   `actions/cache@v4` を使用して、前回のISBNリスト (`isbns_previous.json`) をキャッシュから復元/保存します。
    *   `generate_feed.py` スクリプトを実行します。
    *   `peaceiris/actions-gh-pages@v4` を使用して、生成された `index.xml` を `gh-pages` ブランチにデプロイします。
2.  **Pythonスクリプト (`generate_feed.py`)**:
    *   前回のISBNリストを読み込みます（初回実行時は空）。
    *   OpenBD API (`/v1/coverage`) から最新の全ISBNリストを取得します。
    *   差分（新規追加ISBN）を計算します。
    *   新規ISBNについてのみOpenBD API (`/v1/get`) から書籍詳細を取得します。
    *   詳細情報をCコード (`TARGET_C_CODES` 定数で定義) と発売日でフィルタリングします。
    *   フィルタリング結果を元に `feedgen` ライブラリを使用してRSSフィード (`index.xml`) を生成します。
    *   最新の全ISBNリストを次回比較用に `isbns_previous.json` として保存します。

## セットアップ

1.  このリポジトリをクローンまたはフォークします。
2.  リポジトリ名を `shinsho` に設定します（または任意の名前に変更し、それに合わせてスクリプト内の `feed_link_url` と `FEED_WEBMASTER`、README内のURL例を修正します）。
3.  GitHubリポジトリの **Settings** > **Pages** に移動します。
4.  "Build and deployment" の "Source" で "Deploy from a branch" を選択します。
5.  **Branch** で `gh-pages` を選択し、フォルダは `/ (root)` を選択して **Save** します。
    *(注意: `gh-pages` ブランチは、Actionsが初めて正常に実行され、デプロイが行われた後に作成されます。)*
6.  GitHub Actions が自動的に実行され、フィードが生成・公開されます。Actions タブで実行状況を確認できます。

## カスタマイズ

`generate_feed.py` 内の定数を変更することで、動作をカスタマイズできます。

*   `TARGET_C_CODES`: フィルタリング対象とするCコード（Scheme 78）のセット。
*   `OUTPUT_FILE`: 出力するRSSフィードのファイル名。
*   `FEED_TITLE`, `FEED_DESCRIPTION`, etc.: RSSフィードのヘッダー情報。
*   `MAX_FEED_ITEMS`: フィードに含めるアイテムの最大数。
*   `REQUEST_DELAY`: `/v1/get` APIへのリクエスト間の待機時間（秒）。

## 注意事項

*   **初回実行**: 最初のActions実行では、ISBNリストの比較対象がないため、リストを保存し空のフィードを生成して終了します。実際のフィード内容は2回目の実行以降に生成され始めます。
*   **API負荷**: OpenBD APIの利用規約に従い、過度な負荷をかけないようにしてください。`REQUEST_DELAY` の調整は慎重に行ってください。
*   **データ**: 提供されるデータはOpenBDに依存します。Cコードや発売日の登録状況によっては、期待通りにフィルタリングされない場合があります。

## データソース

このプロジェクトは [openBD](https://openbd.jp/) プロジェクトによって提供される書誌情報を利用しています。

*   [openBD API仕様](https://openbd.jp/spec/)
*   [openBD利用規約](https://openbd.jp/terms/)

## ライセンス

(必要であれば、ここにライセンス情報を記載してください。例: MIT Licenseなど)