#!/usr/bin/env python3
"""
新規新書データからRSSフィードを生成するスクリプト
"""
import json
import os
from datetime import datetime
from feedgen.feed import FeedGenerator
from dateutil import parser as date_parser
from typing import Dict, List

# 定数
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
DOCS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs")
NEW_RECORDS_FILE = os.path.join(DATA_DIR, "new_shinsho_records.json")
FEED_FILE = os.path.join(DOCS_DIR, "index.xml")
SITE_URL = "https://analekt.github.io/shinsho"  # GitHubユーザー名に置き換える
FEED_HISTORY_FILE = os.path.join(DATA_DIR, "feed_history.json")
MAX_FEED_ENTRIES = 50  # フィードに保持する最大エントリー数


def format_authors(authors: List[Dict]) -> str:
    """
    著者情報をフォーマット
    """
    if not authors:
        return "著者不明"
    
    author_strings = []
    for author in authors:
        name = author.get("name", "")
        role = author.get("role", "")
        
        # 役割コードを日本語に変換（主要なもののみ）
        role_map = {
            "A01": "著",
            "A02": "編",
            "A03": "監修",
            "B01": "訳",
            "B06": "翻訳"
        }
        role_text = role_map.get(role, "")
        
        if role_text:
            author_strings.append(f"{name}（{role_text}）")
        else:
            author_strings.append(name)
    
    return "、".join(author_strings)


def create_description(book: Dict) -> str:
    """
    RSS用の詳細な説明文を生成
    """
    parts = []
    
    # タイトル・サブタイトル
    title = book.get("title", "")
    subtitle = book.get("subtitle", "")
    if subtitle:
        parts.append(f"【書名】{title} - {subtitle}")
    else:
        parts.append(f"【書名】{title}")
    
    # シリーズ・レーベル
    collection = book.get("collection", "")
    if collection:
        parts.append(f"【シリーズ】{collection}")
    
    # 著者
    authors = book.get("authors", [])
    author_text = format_authors(authors)
    parts.append(f"【著者】{author_text}")
    
    # 著者略歴（最初の著者のみ）
    if authors and authors[0].get("bio"):
        bio = authors[0].get("bio", "").strip()
        if bio:
            parts.append(f"【著者略歴】{bio}")
    
    # 出版社
    imprint = book.get("imprint", "")
    publisher = book.get("publisher", "")
    if imprint and publisher and imprint != publisher:
        parts.append(f"【出版社】{imprint}（発売: {publisher}）")
    elif imprint or publisher:
        parts.append(f"【出版社】{imprint or publisher}")
    
    # 出版日
    pub_date = book.get("publishing_date", "")
    if pub_date:
        try:
            # YYYYMMDDフォーマットをYYYY年MM月DD日に変換
            if len(pub_date) == 8:
                formatted_date = f"{pub_date[:4]}年{pub_date[4:6]}月{pub_date[6:]}日"
                parts.append(f"【出版日】{formatted_date}")
            else:
                parts.append(f"【出版日】{pub_date}")
        except:
            parts.append(f"【出版日】{pub_date}")
    
    # ISBN
    parts.append(f"【ISBN】{book.get('isbn', '')}")
    
    return "\n".join(parts)


def load_feed_history() -> List[Dict]:
    """
    フィード履歴を読み込む
    """
    if os.path.exists(FEED_HISTORY_FILE):
        with open(FEED_HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_feed_history(entries: List[Dict]):
    """
    フィード履歴を保存
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(FEED_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)


def generate_feed():
    """
    RSSフィードを生成
    """
    # 新規レコードを読み込む
    if not os.path.exists(NEW_RECORDS_FILE):
        print("新規レコードファイルが見つかりません")
        return
    
    with open(NEW_RECORDS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    new_records = data.get("records", [])
    timestamp = data.get("timestamp", datetime.now().isoformat())
    
    print(f"新規レコード数: {len(new_records)}")
    
    # フィード履歴を読み込む
    feed_history = load_feed_history()
    print(f"既存のフィード履歴: {len(feed_history)}件")
    
    # 新規レコードを履歴に追加（最新のものを先頭に）
    for book in new_records:
        # 重複チェック
        if not any(entry.get("isbn") == book.get("isbn") for entry in feed_history):
            feed_history.insert(0, book)
    
    # 最大エントリー数を制限
    feed_history = feed_history[:MAX_FEED_ENTRIES]
    
    # フィード履歴を保存
    save_feed_history(feed_history)
    
    # フィードジェネレーターを作成
    fg = FeedGenerator()
    fg.id(f"{SITE_URL}/index.xml")
    fg.title("新書新刊情報 - openBD")
    fg.author({"name": "openBD新書フィード", "email": "noreply@example.com"})
    fg.link(href=SITE_URL, rel="alternate")
    fg.link(href=f"{SITE_URL}/index.xml", rel="self")
    fg.subtitle("openBD APIから取得した新書の新刊情報を配信します")
    fg.language("ja")
    fg.lastBuildDate(timestamp)
    
    # フィード履歴からエントリーを生成
    for book in feed_history:
        fe = fg.add_entry()
        
        # ID（ISBN）
        isbn = book.get("isbn", "")
        fe.id(f"{SITE_URL}/books/{isbn}")
        
        # タイトル
        title = book.get("title", "")
        subtitle = book.get("subtitle", "")
        if subtitle:
            fe.title(f"{title} - {subtitle}")
        else:
            fe.title(title)
        
        # リンク（openBDの書籍ページは存在しないため、ISBNで検索できるリンクを生成）
        fe.link(href=f"https://www.hanmoto.com/bd/isbn/{isbn}")
        
        # 著者
        authors = book.get("authors", [])
        author_text = format_authors(authors)
        if author_text:
            fe.author({"name": author_text})
        
        # 説明
        description = create_description(book)
        fe.description(description)
        
        # 公開日時
        fetched_at = book.get("fetched_at", timestamp)
        try:
            pub_datetime = date_parser.parse(fetched_at)
            fe.published(pub_datetime)
        except:
            fe.published(datetime.now())
        
        # カテゴリー（新書）
        fe.category(term="新書", label="新書")
        
        # シリーズ名があればカテゴリーに追加
        collection = book.get("collection", "")
        if collection:
            fe.category(term=collection, label=collection)
    
    # フィードを保存
    os.makedirs(DOCS_DIR, exist_ok=True)
    fg.rss_file(FEED_FILE, pretty=True)
    print(f"RSSフィードを生成しました: {FEED_FILE}")
    print(f"フィードのエントリー数: {len(feed_history)}")


def main():
    """
    メイン処理
    """
    print("RSSフィード生成を開始します...")
    generate_feed()
    print("完了しました")


if __name__ == "__main__":
    main() 