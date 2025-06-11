# openBD 新書RSSフィード

openBD APIを使用して、新しく登録された新書の情報を検出し、RSSフィードとして配信するシステムです。

## 概要

このプロジェクトは以下の機能を提供します：

- openBD APIから新書のデータを自動取得
- 新規登録された新書を検出し、RSSフィードを生成
- 毎日定刻（デフォルトは午前4時JST）に自動更新
- GitHub Pagesでフィードを静的サイトとして公開

## セットアップ方法

### 1. リポジトリのフォーク

このリポジトリをフォークして、自分のGitHubアカウントにコピーしてください。

### 2. GitHub Pagesの有効化

1. フォークしたリポジトリの設定（Settings）を開く
2. 「Pages」セクションに移動
3. 「Source」を「Deploy from a branch」に設定
4. 「Branch」を「gh-pages」、フォルダを「/(root)」に設定
5. 保存

### 3. 初回実行

リポジトリをフォークして`main`ブランチに何らかのコミットをプッシュすると、GitHub Actionsが自動的に実行されます。

**初回データ取得について:**
- **差分更新（デフォルト）:** 初回実行は高速な差分更新モードで動作します。これにより、直近のデータのみが処理され、すぐにフィードが生成されます。
- **全件スキャン（手動実行）:** openBDに登録されている全ての書籍情報をスキャンし、新書を網羅的にデータベース化するには、手動で全件スキャンをトリガーする必要があります。方法は「全件スキャンの実行方法」を参照してください。

### 4. RSSフィードのURL

セットアップが完了すると、以下のURLでRSSフィードにアクセスできます：

```
https://YOUR_USERNAME.github.io/shinsho/index.xml
```

（YOUR_USERNAMEは自分のGitHubユーザー名に置き換えてください）

## 技術仕様

### 使用技術

- Python 3.10
- openBD API v1
- GitHub Actions（自動化）
- GitHub Pages（ホスティング）

### 主要ファイル

- `scripts/fetch_shinsho.py` - openBD APIから新書データを取得
- `scripts/generate_rss.py` - RSSフィードを生成
- `.github/workflows/update-feed.yml` - 自動実行の設定
- `data/shinsho_records.json` - 取得済みの新書レコード（差分検出用）
- `docs/index.xml` - 生成されたRSSフィード本体
- `docs/index.html` - RSSフィードを紹介するランディングページ

### RSSフィードの内容

各エントリーには以下の情報が含まれます：

- 書名・サブタイトル
- シリーズ名/レーベル名
- 著者名・役割
- 著者略歴
- 出版社情報（発行元・発売元）
- 出版日
- ISBN

## 全件スキャンの実行方法
`data/shinsho_records.json` ファイルをリポジトリから削除して`main`ブランチにコミット・プッシュすると、次回のGitHub Actions実行時に全件スキャンがトリガーされます。処理には数時間かかる場合があります。

```bash
# リポジトリのルートで実行
rm data/shinsho_records.json
git add data/shinsho_records.json
git commit -m "chore: trigger full scan"
git push origin main
```

## カスタマイズ

### 更新頻度の変更
`.github/workflows/update-feed.yml`の`cron`設定を変更することで、更新頻度を調整できます。

### フィード内容の変更
`scripts/generate_rss.py`の`create_description`関数を編集することで、RSSフィードに含める情報をカスタマイズできます。

## 注意事項

- 全件スキャンを実行する場合、処理に時間がかかります（最大6時間）。GitHub Actionsのタイムアウト設定も`360`分（6時間）になっています。
- GitHub Actionsの無料枠には制限があります（月2000分）。
- openBD APIの利用は本の販促・紹介目的に限定されています。

## ライセンス

このプロジェクトはMITライセンスで公開されています。

## 謝辞

- [openBD](https://openbd.jp/) - 書誌情報・書影の提供
- [カーリル](https://calil.jp/) - APIシステムの開発
- [版元ドットコム](https://www.hanmoto.com/) - 書誌情報の収集 