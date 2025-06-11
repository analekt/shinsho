#!/usr/bin/env python3
"""
openBD APIから新書データを取得し、新規登録を検出するスクリプト
"""
import json
import os
import requests
import argparse
from datetime import datetime
from typing import Dict, List, Set, Optional

# 定数
API_BASE_URL = "https://api.openbd.jp/v1"
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
RECORDS_FILE = os.path.join(DATA_DIR, "shinsho_records.json")
NEW_RECORDS_FILE = os.path.join(DATA_DIR, "new_shinsho_records.json")
BATCH_SIZE = 1000  # APIの最大リクエスト数


def is_shinsho(book_data: Dict, debug_mode: bool = False) -> bool:
    """
    書籍が新書かどうかを判定する
    Collectionフィールドのタイトルに「新書」が含まれるかを確認
    """
    if not book_data or "onix" not in book_data:
        return False
    
    onix = book_data.get("onix", {})
    descriptive_detail = onix.get("DescriptiveDetail", {})
    
    # Collection情報を確認
    collection = descriptive_detail.get("Collection", {})
    if collection:
        title_detail = collection.get("TitleDetail", {})
        if title_detail:
            title_elements = title_detail.get("TitleElement", [])
            
            # TitleElementが配列でない場合は単一要素として扱う
            if not isinstance(title_elements, list):
                title_elements = [title_elements]
            
            for element in title_elements:
                if isinstance(element, dict):
                    title_text = element.get("TitleText", {})
                    if isinstance(title_text, dict):
                        content = title_text.get("content", "")
                    else:
                        content = title_text
                    
                    # 「新書」が含まれているかチェック
                    if isinstance(content, str) and "新書" in content:
                        if debug_mode:
                            print(f"新書を検出: {content}")
                        return True
    
    # summaryフィールドのseriesも確認（バックアップ）
    summary = book_data.get("summary", {})
    if summary:
        series = summary.get("series", "")
        if isinstance(series, str) and "新書" in series:
            if debug_mode:
                print(f"新書を検出 (summary.series): {series}")
            return True
    
    # デバッグモードの場合、情報を出力
    if debug_mode:
        isbn = book_data.get("onix", {}).get("RecordReference", "")
        title = ""
        
        # タイトル情報を取得
        title_detail = descriptive_detail.get("TitleDetail", {})
        if title_detail:
            title_element = title_detail.get("TitleElement", {})
            if title_element:
                if isinstance(title_element, dict):
                    title_text = title_element.get("TitleText", {})
                    if isinstance(title_text, dict):
                        title = title_text.get("content", "")
                    else:
                        title = title_text
        
        # Collectionの情報を出力
        if collection:
            coll_title_detail = collection.get("TitleDetail", {})
            if coll_title_detail:
                coll_title_elements = coll_title_detail.get("TitleElement", [])
                if not isinstance(coll_title_elements, list):
                    coll_title_elements = [coll_title_elements]
                
                coll_titles = []
                for element in coll_title_elements:
                    if isinstance(element, dict):
                        coll_title_text = element.get("TitleText", {})
                        if isinstance(coll_title_text, dict):
                            coll_content = coll_title_text.get("content", "")
                        else:
                            coll_content = coll_title_text
                        coll_titles.append(coll_content)
                
                if coll_titles:
                    print(f"検出されなかった書籍: ISBN={isbn}, タイトル={title}, Collection={coll_titles}")
        
        # summary.seriesの情報も出力
        if summary and summary.get("series"):
            print(f"検出されなかった書籍: ISBN={isbn}, タイトル={title}, Series={summary.get('series')}")
    
    return False


def get_all_isbns() -> List[str]:
    """
    openBD APIのカバレッジ情報から全ISBNリストを取得
    """
    print("全ISBNリストを取得中...")
    response = requests.get(f"{API_BASE_URL}/coverage")
    response.raise_for_status()
    
    isbn_list = response.json()
    print(f"総ISBN数: {len(isbn_list)}")
    return isbn_list


def get_japanese_isbns(all_isbns: List[str]) -> List[str]:
    """
    日本の書籍のISBNのみをフィルタリング (978-4で始まるもの)
    デバッグモード用
    """
    jp_isbns = [isbn for isbn in all_isbns if isbn.startswith("978-4") or isbn.startswith("9784")]
    print(f"日本の書籍ISBN数: {len(jp_isbns)}")
    return jp_isbns


def fetch_books_batch(isbns: List[str]) -> List[Dict]:
    """
    ISBNのバッチで書籍情報を取得
    """
    isbn_param = ",".join(isbns)
    response = requests.get(f"{API_BASE_URL}/get", params={"isbn": isbn_param})
    response.raise_for_status()
    
    books = response.json()
    # Noneでない書籍のみ返す
    return [book for book in books if book is not None]


def load_existing_records() -> Dict[str, Dict]:
    """
    既存の新書レコードを読み込む
    """
    if os.path.exists(RECORDS_FILE):
        with open(RECORDS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_records(records: Dict[str, Dict]):
    """
    新書レコードを保存
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(RECORDS_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


def save_new_records(new_records: List[Dict]):
    """
    新規追加された新書レコードを保存
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(NEW_RECORDS_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "count": len(new_records),
            "records": new_records
        }, f, ensure_ascii=False, indent=2)


def extract_book_info(book_data: Dict) -> Dict:
    """
    書籍情報から必要な情報を抽出
    """
    onix = book_data.get("onix", {})
    isbn = onix.get("RecordReference", "")
    
    # 出版情報
    publishing_detail = onix.get("PublishingDetail", {})
    imprint = publishing_detail.get("Imprint", {})
    publisher = publishing_detail.get("Publisher", {})
    publishing_date = publishing_detail.get("PublishingDate", {})
    
    # 商品情報
    descriptive_detail = onix.get("DescriptiveDetail", {})
    collection = descriptive_detail.get("Collection", {})
    title_detail = descriptive_detail.get("TitleDetail", {})
    contributors = descriptive_detail.get("Contributor", [])
    
    if not isinstance(contributors, list):
        contributors = [contributors]
    
    # タイトル情報の抽出
    title_element = title_detail.get("TitleElement", {}) if title_detail else {}
    title = title_element.get("TitleText", {}).get("content", "") if isinstance(title_element.get("TitleText"), dict) else title_element.get("TitleText", "")
    subtitle = title_element.get("Subtitle", {}).get("content", "") if isinstance(title_element.get("Subtitle"), dict) else title_element.get("Subtitle", "")
    
    # コレクション情報
    collection_info = None
    if collection:
        collection_title = collection.get("TitleDetail", {})
        if collection_title:
            collection_element = collection_title.get("TitleElement", {})
            collection_name = collection_element.get("TitleText", {}).get("content", "") if isinstance(collection_element.get("TitleText"), dict) else collection_element.get("TitleText", "")
            collection_info = collection_name
    
    # 著者情報
    authors = []
    for contributor in contributors:
        if isinstance(contributor, dict):
            person_name = contributor.get("PersonName", {})
            name = person_name.get("content", "") if isinstance(person_name, dict) else person_name
            role = contributor.get("ContributorRole", "")
            bio = contributor.get("BiographicalNote", {})
            bio_text = bio.get("content", "") if isinstance(bio, dict) else bio
            
            if name:
                authors.append({
                    "name": name,
                    "role": role,
                    "bio": bio_text
                })
    
    return {
        "isbn": isbn,
        "title": title,
        "subtitle": subtitle,
        "collection": collection_info,
        "authors": authors,
        "imprint": imprint.get("ImprintName", ""),
        "publisher": publisher.get("PublisherName", ""),
        "publishing_date": publishing_date.get("Date", ""),
        "fetched_at": datetime.now().isoformat()
    }


def main():
    """
    メイン処理
    """
    # コマンドライン引数の解析
    parser = argparse.ArgumentParser(description='openBD APIから新書データを取得するスクリプト')
    parser.add_argument('--debug', action='store_true', help='デバッグモードを有効にする')
    parser.add_argument('--limit', type=int, default=None, help='処理するISBN数を制限する（デバッグ用）')
    parser.add_argument('--jp-only', action='store_true', help='日本の書籍のみを処理する')
    args = parser.parse_args()
    
    debug_mode = args.debug
    limit = args.limit
    jp_only = args.jp_only
    
    print("新書データ取得処理を開始します...")
    if debug_mode:
        print("デバッグモードが有効です")
    if jp_only:
        print("日本の書籍のみを処理します")
    
    start_time = datetime.now()
    
    # 既存レコードを読み込み
    existing_records = load_existing_records()
    existing_isbns = set(existing_records.keys())
    print(f"既存の新書レコード数: {len(existing_records)}")
    
    # 初回実行かどうかを判定
    is_initial_run = len(existing_records) == 0
    if is_initial_run:
        print("初回実行を検出しました。処理に時間がかかる場合があります。")
    
    # 全ISBNリストを取得
    all_isbns = get_all_isbns()
    
    # 日本の書籍のみに絞り込み
    if jp_only:
        all_isbns = get_japanese_isbns(all_isbns)
    
    # デバッグモードでサンプル数を制限
    if limit:
        print(f"指定された上限({limit}件)までのISBNのみ処理します")
        all_isbns = all_isbns[:limit]
    # 初回実行時は処理を分割（GitHub Actionsのタイムアウト対策）
    elif is_initial_run and len(all_isbns) > 100000:
        print(f"初回実行のため、最初の100,000件のみ処理します。")
        all_isbns = all_isbns[:100000]
    
    # 新しい新書レコード
    new_shinsho_records = []
    updated_records = existing_records.copy()
    
    # バッチ処理
    total_batches = (len(all_isbns) + BATCH_SIZE - 1) // BATCH_SIZE
    processed_count = 0
    shinsho_count = len(existing_records)  # 既存の新書数から開始
    error_count = 0
    
    for i in range(0, len(all_isbns), BATCH_SIZE):
        batch_isbns = all_isbns[i:i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        
        # より詳細な進捗表示
        if batch_num % 5 == 1:  # 5バッチごとに表示
            elapsed = (datetime.now() - start_time).total_seconds()
            rate = processed_count / elapsed if elapsed > 0 else 0
            eta = (len(all_isbns) - processed_count) / rate if rate > 0 else 0
            print(f"\nバッチ {batch_num}/{total_batches} を処理中...")
            print(f"経過時間: {elapsed:.1f}秒, 処理速度: {rate:.1f} ISBN/秒")
            print(f"推定残り時間: {eta/60:.1f}分")
        
        try:
            books = fetch_books_batch(batch_isbns)
            
            for book in books:
                if is_shinsho(book, debug_mode):
                    isbn = book.get("onix", {}).get("RecordReference", "")
                    if isbn and isbn not in existing_isbns:
                        # 新規新書を発見
                        book_info = extract_book_info(book)
                        new_shinsho_records.append(book_info)
                        updated_records[isbn] = book_info
                        existing_isbns.add(isbn)  # 重複防止
                        print(f"新規新書発見: {book_info['title']} (ISBN: {isbn})")
                    if isbn not in existing_isbns:
                        shinsho_count += 1
            
            processed_count += len(batch_isbns)
            
        except Exception as e:
            error_count += 1
            print(f"エラー発生 (バッチ {batch_num}): {str(e)}")
        
        # 50バッチごとに中間保存
        if batch_num % 50 == 0:
            save_records(updated_records)
            save_new_records(new_shinsho_records)
            print(f"中間保存を実行しました（{len(new_shinsho_records)}件）")
    
    # 最終的な結果を保存
    save_records(updated_records)
    save_new_records(new_shinsho_records)
    
    # 処理時間を計算
    elapsed_seconds = (datetime.now() - start_time).total_seconds()
    elapsed_minutes = elapsed_seconds / 60
    
    print("\n処理完了:")
    print(f"- 処理時間: {elapsed_minutes:.1f}分")
    print(f"- 処理したISBN数: {processed_count}")
    print(f"- 新書総数: {shinsho_count}")
    print(f"- 新規新書数: {len(new_shinsho_records)}")
    print(f"- エラー数: {error_count}")
    print("データ保存完了")


if __name__ == "__main__":
    main() 