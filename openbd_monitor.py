#!/usr/bin/env python3
"""
OpenBD Cコード監視スクリプト

Cコードの左から二番目の数字が2の新しい書籍を監視し、RSSフィードを更新します。
"""

import json
import requests
import sqlite3
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import logging
import re
import os

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class OpenBDCCodeMonitor:
    def __init__(self, db_path: str = "openbd_books.db"):
        self.db_path = db_path
        self.api_base = "https://api.openbd.jp/v1"
        self.init_database()
    
    def init_database(self):
        """SQLiteデータベースの初期化"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS monitored_books (
                isbn TEXT PRIMARY KEY,
                title TEXT,
                ccode TEXT,
                publisher TEXT,
                authors TEXT,
                discovered_date TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS processed_isbns (
                isbn TEXT PRIMARY KEY,
                processed_date TEXT,
                has_ccode_match BOOLEAN
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS check_history (
                id INTEGER PRIMARY KEY,
                last_check_date TEXT
            )
        ''')
        conn.commit()
        conn.close()
    
    def is_book_processed(self, isbn: str) -> bool:
        """書籍が既に処理されているかチェック"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT isbn FROM processed_isbns WHERE isbn = ?', (isbn,))
        result = cursor.fetchone()
        conn.close()
        return result is not None
    
    def mark_book_processed(self, isbn: str, has_match: bool):
        """書籍を処理済みとしてマーク"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO processed_isbns 
            (isbn, processed_date, has_ccode_match) 
            VALUES (?, ?, ?)
        ''', (isbn, datetime.now().isoformat(), has_match))
        conn.commit()
        conn.close()
    
    def save_book(self, isbn: str, title: str, ccode: str, publisher: str, authors: str):
        """書籍情報をデータベースに保存"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO monitored_books 
            (isbn, title, ccode, publisher, authors, discovered_date) 
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (isbn, title, ccode, publisher, authors, datetime.now().isoformat()))
        conn.commit()
        conn.close()
    
    def get_coverage_data(self) -> Optional[List[str]]:
        """OpenBD coverage APIから全ISBN一覧を取得"""
        try:
            logger.info("Coverage APIから全ISBN一覧を取得中...")
            response = requests.get(f"{self.api_base}/coverage")
            response.raise_for_status()
            coverage_data = response.json()
            
            if isinstance(coverage_data, list):
                logger.info(f"全{len(coverage_data)}件のISBNを取得")
                return coverage_data
            else:
                logger.error("Coverage APIの応答形式が予期しない形式です")
                return None
                
        except Exception as e:
            logger.error(f"Coverage API取得エラー: {e}")
            return None
    
    def get_last_check_date(self) -> Optional[str]:
        """最後にチェックした日付を取得"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS check_history (
                id INTEGER PRIMARY KEY,
                last_check_date TEXT
            )
        ''')
        cursor.execute('SELECT last_check_date FROM check_history ORDER BY id DESC LIMIT 1')
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None
    
    def update_last_check_date(self):
        """最後のチェック日付を更新"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('INSERT INTO check_history (last_check_date) VALUES (?)', 
                      (datetime.now().isoformat(),))
        conn.commit()
        conn.close()
    
    def filter_new_isbns(self, all_isbns: List[str]) -> List[str]:
        """未処理のISBNのみ返す"""
        if not all_isbns:
            return []
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # バッチでチェック（効率化）
        placeholders = ','.join('?' * len(all_isbns))
        cursor.execute(f'''
            SELECT isbn FROM processed_isbns 
            WHERE isbn IN ({placeholders})
        ''', all_isbns)
        
        processed_isbns = set(row[0] for row in cursor.fetchall())
        conn.close()
        
        new_isbns = [isbn for isbn in all_isbns if isbn not in processed_isbns]
        logger.info(f"全{len(all_isbns)}件中、未処理{len(new_isbns)}件")
        
        return new_isbns
    
    def get_recent_isbns(self) -> List[str]:
        """最近のISBNリストを取得（差分フェッチ対応）"""
        # 全ISBNを取得
        all_isbns = self.get_coverage_data()
        if not all_isbns:
            logger.warning("Coverage APIからISBNを取得できませんでした")
            return []
        
        # 新しいISBNのみフィルタリング
        new_isbns = self.filter_new_isbns(all_isbns)
        
        # 処理量制限（初回は5000件、通常は1000件まで）
        last_check = self.get_last_check_date()
        max_process = 5000 if last_check is None else 1000
        
        if len(new_isbns) > max_process:
            logger.info(f"処理量制限: {len(new_isbns)}件中最初の{max_process}件を処理")
            new_isbns = new_isbns[:max_process]
        
        return new_isbns
    
    def get_book_info(self, isbn: str) -> Optional[Dict[str, Any]]:
        """OpenBD APIから書籍情報を取得"""
        try:
            response = requests.get(f"{self.api_base}/get?isbn={isbn}")
            response.raise_for_status()
            data = response.json()
            return data[0] if data and data[0] else None
        except Exception as e:
            logger.error(f"ISBN {isbn}の取得エラー: {e}")
            return None
    
    def extract_ccode(self, book_data: Dict[str, Any]) -> Optional[str]:
        """書籍データからCコードを抽出"""
        if not book_data:
            return None
        
        # Subject配列からCコードを検索
        subjects = book_data.get('Subject', [])
        for subject in subjects:
            subject_code = subject.get('SubjectCode', '')
            # Cコードのパターン: C + 4桁数字
            if re.match(r'^C\d{4}$', subject_code):
                return subject_code
        
        # hanmotoセクションのgenrecodeもチェック
        hanmoto = book_data.get('hanmoto', {})
        if hanmoto:
            for field in ['genrecodetrc', 'genrecodetrcjidou']:
                genre_code = hanmoto.get(field, '')
                if re.match(r'^C\d{4}$', genre_code):
                    return genre_code
        
        return None
    
    def is_target_ccode(self, ccode: str) -> bool:
        """Cコードが監視対象か判定（左から二番目の数字が2）"""
        if not ccode or len(ccode) != 5:
            return False
        
        # Cコードの形式: C + 4桁数字
        if not re.match(r'^C\d{4}$', ccode):
            return False
        
        # 左から二番目の数字（インデックス2）が2かチェック
        return ccode[2] == '2'
    
    def extract_book_details(self, book_data: Dict[str, Any]) -> Dict[str, str]:
        """書籍の詳細情報を抽出"""
        details = {
            'title': 'Unknown Title',
            'publisher': 'Unknown Publisher',
            'authors': 'Unknown Author'
        }
        
        # タイトル抽出
        title_detail = book_data.get('TitleDetail', {})
        if title_detail:
            title_text = title_detail.get('TitleText', '')
            if title_text:
                details['title'] = title_text
        
        # 出版社抽出
        publishing_detail = book_data.get('PublishingDetail', {})
        if publishing_detail:
            publishers = publishing_detail.get('Publisher', [])
            if publishers:
                pub_name = publishers[0].get('PublisherName', '')
                if pub_name:
                    details['publisher'] = pub_name
        
        # 著者抽出
        contributors = book_data.get('Contributor', [])
        authors = []
        for contributor in contributors:
            if contributor.get('ContributorRole') == 'A01':  # 著者
                person_name = contributor.get('PersonName', '')
                if person_name:
                    authors.append(person_name)
        
        if authors:
            details['authors'] = ', '.join(authors)
        
        return details
    
    def generate_rss_feed(self, new_books: List[Dict[str, Any]], output_file: str = "index.xml"):
        """新しい書籍からRSSフィードを生成"""
        # RSS構造作成
        rss = ET.Element("rss", version="2.0")
        channel = ET.SubElement(rss, "channel")
        
        # チャンネルメタデータ
        ET.SubElement(channel, "title").text = "OpenBD Cコード監視フィード"
        ET.SubElement(channel, "description").text = "Cコード左から二番目が2の新刊書籍"
        ET.SubElement(channel, "link").text = "https://openbd.jp/"
        ET.SubElement(channel, "lastBuildDate").text = datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0900")
        
        # 各書籍のアイテム追加
        for book_info in new_books:
            item = ET.SubElement(channel, "item")
            
            title = f"{book_info['title']} (Cコード: {book_info['ccode']})"
            description = f"著者: {book_info['authors']} | 出版社: {book_info['publisher']} | ISBN: {book_info['isbn']}"
            
            ET.SubElement(item, "title").text = title
            ET.SubElement(item, "description").text = description
            ET.SubElement(item, "guid").text = book_info['isbn']
            ET.SubElement(item, "pubDate").text = datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0900")
            ET.SubElement(item, "link").text = f"https://api.openbd.jp/v1/get?isbn={book_info['isbn']}"
        
        # RSSファイル出力
        tree = ET.ElementTree(rss)
        ET.indent(tree, space="  ", level=0)
        tree.write(output_file, encoding='utf-8', xml_declaration=True)
        logger.info(f"RSSフィード生成完了: {output_file}")
    
    def monitor_new_books(self):
        """新しい書籍を監視してRSSフィードを更新"""
        logger.info("Cコード監視開始")
        
        # 最近のISBNリストを取得
        isbn_list = self.get_recent_isbns()
        new_books = []
        
        for isbn in isbn_list:
            if self.is_book_processed(isbn):
                continue
            
            # 書籍情報取得
            book_data = self.get_book_info(isbn)
            if not book_data:
                self.mark_book_processed(isbn, False)
                continue
            
            # Cコード抽出
            ccode = self.extract_ccode(book_data)
            has_match = False
            
            # 対象Cコードかチェック
            if ccode and self.is_target_ccode(ccode):
                details = self.extract_book_details(book_data)
                
                # データベースに保存
                self.save_book(isbn, details['title'], ccode, details['publisher'], details['authors'])
                
                # 新書籍リストに追加
                new_books.append({
                    'isbn': isbn,
                    'title': details['title'],
                    'ccode': ccode,
                    'publisher': details['publisher'],
                    'authors': details['authors']
                })
                
                has_match = True
                logger.info(f"新規対象書籍発見: {details['title']} (ISBN: {isbn}, Cコード: {ccode})")
            
            # 処理済みマーク
            self.mark_book_processed(isbn, has_match)
        
        # チェック履歴更新
        self.update_last_check_date()
        
        # 新しい書籍があればRSSフィード生成
        if new_books:
            self.generate_rss_feed(new_books)
            logger.info(f"{len(new_books)}冊の新規書籍を発見")
        else:
            logger.info("新規対象書籍なし")
        
        return len(new_books)

def main():
    """メイン処理"""
    monitor = OpenBDCCodeMonitor()
    new_count = monitor.monitor_new_books()
    
    # GitHub Actionsでの実行時は結果を出力
    if os.getenv('GITHUB_ACTIONS'):
        print(f"::notice::発見した新規書籍数: {new_count}")

if __name__ == "__main__":
    main()