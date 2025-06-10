# openBD 新書RSSフィード

openBD APIを使用して、新しく登録された新書の情報を検出し、RSSフィードとして配信するシステムです。

## 概要

このプロジェクトは以下の機能を提供します：

- openBD APIから新書（日本図書コードの2桁目が「2」）のデータを自動取得
- 新規登録された新書を検出し、RSSフィードを生成
- 毎日午前4時（JST）に自動更新
- GitHub Pagesでフィードを公開

## セットアップ方法

### 1. リポジトリのフォーク

このリポジトリをフォークして、自分のGitHubアカウントにコピーしてください。

### 2. GitHub Pagesの有効化

1. フォークしたリポジトリの設定（Settings）を開く
2. 「Pages」セクションに移動
3. 「Source」を「Deploy from a branch」に設定
4. 「Branch」を「gh-pages」に設定
5. 保存

### 3. 初回実行

リポジトリをフォークすると、GitHub Actionsが自動的に実行されます。初回実行には時間がかかる場合があります（全新書データの取得のため）。

### 4. RSSフィードのURL

セットアップが完了すると、以下のURLでRSSフィードにアクセスできます：

```
https://YOUR_USERNAME.github.io/opendb-shinsho-feed/feed.xml
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
- `data/shinsho_records.json` - 既存の新書レコード（差分検出用）
- `docs/feed.xml` - 生成されたRSSフィード

### RSSフィードの内容

各エントリーには以下の情報が含まれます：

- 書名・サブタイトル
- シリーズ名/レーベル名
- 著者名・役割
- 著者略歴
- 出版社情報（発行元・発売元）
- 出版日
- ISBN

## カスタマイズ

### 更新頻度の変更

`.github/workflows/update-feed.yml`の`cron`設定を変更することで、更新頻度を調整できます。

### フィード内容の変更

`scripts/generate_rss.py`の`create_description`関数を編集することで、RSSフィードに含める情報をカスタマイズできます。

## 注意事項

- 初回実行時は全新書データを取得するため、処理に時間がかかります（最大6時間）
- GitHub Actionsの無料枠には制限があります（月2000分）
- openBD APIの利用は本の販促・紹介目的に限定されています

## ライセンス

このプロジェクトはMITライセンスで公開されています。

## 謝辞

- [openBD](https://openbd.jp/) - 書誌情報・書影の提供
- [カーリル](https://calil.jp/) - APIシステムの開発
- [版元ドットコム](https://www.hanmoto.com/) - 書誌情報の収集 