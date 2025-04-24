import requests
import time
from feedgen.feed import FeedGenerator
from datetime import datetime, timezone
import pytz
from email.utils import format_datetime
import logging
import re
import json
import os

# --- Constants ---
OPENBD_API_COVERAGE_URL = "https://api.openbd.jp/v1/coverage"
OPENBD_API_GET_URL = "https://api.openbd.jp/v1/get"
TARGET_C_CODES = { # Updated C-Codes (no "C" prefix, Scheme 78)
    "0200", "0201", "0202", "0204", "0210", "0211", "0212", "0214",
    "0215", "0216", "0220", "0221", "0222", "0223", "0225", "0226",
    "0230", "0231", "0232", "0233", "0234", "0236", "0237", "0239",
    "0240", "0241", "0242", "0243", "0244", "0245", "0247", "0250",
    "0251", "0252", "0253", "0254", "0255", "0256", "0257", "0258",
    "0260", "0261", "0263", "0265", "0270", "0271", "0272", "0273",
    "0274", "0275", "0276", "0277", "0279", "0280", "0281", "0282",
    "0284", "0285", "0287", "0290", "0291", "0292", "0293", "0295",
    "0297", "0298"
}
CHUNK_SIZE = 1000
REQUEST_DELAY = 1
OUTPUT_FILE = "index.xml" # Changed filename
FEED_TITLE = "新刊新書RSSフィード"
FEED_DESCRIPTION = "発売が確定した新書の情報をRSSリーダーで購読できます。版元ドットコムのAPIを利用しています。"
FEED_LINK_BASE = "https://www.books.or.jp/book-details/"
FEED_WEBMASTER = "https://analekt.github.io/"
FEED_COPYRIGHT = "Copyright owner: openBDプロジェクト、JPO出版情報登録センター"
PREVIOUS_ISBNS_FILE = "isbns_previous.json"
MAX_FEED_ITEMS = 200
# --- End Constants ---

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
# --- End Logging Setup ---

# --- Helper Functions ---
# (load_previous_isbns, save_current_isbns, get_all_isbns, get_book_details,
#  parse_pubdate, get_description, filter_books functions remain unchanged
#  from the previous version with detailed logging)

def load_previous_isbns():
    """Loads the list of previously seen ISBNs from a JSON file."""
    if not os.path.exists(PREVIOUS_ISBNS_FILE):
        logging.info(f"{PREVIOUS_ISBNS_FILE} not found. Treating as first run.")
        return set()
    try:
        with open(PREVIOUS_ISBNS_FILE, 'r', encoding='utf-8') as f:
            isbns = json.load(f)
            if isinstance(isbns, list):
                logging.info(f"Loaded {len(isbns)} ISBNs from {PREVIOUS_ISBNS_FILE}")
                return set(isbns) # Return a set for efficient lookup
            else:
                logging.warning(f"Invalid format in {PREVIOUS_ISBNS_FILE}. Treating as empty.")
                return set()
    except json.JSONDecodeError:
        logging.error(f"Error decoding JSON from {PREVIOUS_ISBNS_FILE}. Treating as empty.")
        return set()
    except Exception as e:
        logging.error(f"Error loading previous ISBNs: {e}. Treating as empty.")
        return set()

def save_current_isbns(isbns_list):
    """Saves the current list of ISBNs to a JSON file."""
    try:
        # Ensure we save a list for consistency
        isbns_to_save = list(isbns_list) if isinstance(isbns_list, set) else isbns_list
        with open(PREVIOUS_ISBNS_FILE, 'w', encoding='utf-8') as f:
            json.dump(isbns_to_save, f, indent=2) # Save the list with indentation
        logging.info(f"Saved {len(isbns_to_save)} ISBNs to {PREVIOUS_ISBNS_FILE}")
    except Exception as e:
        logging.error(f"Error saving current ISBNs to {PREVIOUS_ISBNS_FILE}: {e}")

def get_all_isbns():
    """Retrieves the list of all ISBNs from the OpenBD coverage API."""
    logging.info(f"Fetching all ISBNs from {OPENBD_API_COVERAGE_URL}...")
    try:
        response = requests.get(OPENBD_API_COVERAGE_URL, timeout=90) # Increased timeout
        response.raise_for_status()
        isbns = response.json()
        if isinstance(isbns, list):
            logging.info(f"Successfully fetched {len(isbns)} ISBNs.")
            return [str(isbn) for isbn in isbns] # Ensure all are strings
        else:
            logging.error(f"Unexpected data format from coverage API: {type(isbns)}")
            return None
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching ISBN list: {e}")
        return None
    except json.JSONDecodeError as e:
        logging.error(f"Error decoding JSON from coverage API: {e}")
        return None

def get_book_details(isbn_list):
    """Fetches book details from the OpenBD get API for a list of ISBNs."""
    if not isbn_list:
        return []
    # logging.info(f"Fetching details for {len(isbn_list)} ISBNs from {OPENBD_API_GET_URL}...")
    try:
        isbn_string = ",".join(isbn_list)
        response = requests.post(OPENBD_API_GET_URL, data={'isbn': isbn_string}, timeout=180) # Further increased timeout
        response.raise_for_status()
        data = response.json()
        valid_data = [item for item in data if item is not None and isinstance(item, dict)]
        # logging.info(f"Successfully fetched details for {len(valid_data)} out of {len(isbn_list)} requested ISBNs.")
        return valid_data
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching book details batch starting with {isbn_list[:3]}...: {e}")
        return []
    except json.JSONDecodeError as e:
        logging.error(f"Error decoding JSON from get API batch starting with {isbn_list[:3]}...: {e}")
        return []

def parse_pubdate(pubdate_str):
    """Parses various date string formats into timezone-aware datetime objects."""
    if not pubdate_str or not isinstance(pubdate_str, str):
        return None
    dt = None
    formats_to_try = [
        ("%Y%m%d", False),      # YYYYMMDD
        ("%Y-%m-%d", False),    # YYYY-MM-DD
        ("%Y年%m月%d日", False), # YYYY年MM月DD日
        ("%Y", True),           # YYYY (treat as Jan 1st)
    ]
    for fmt, is_year_only in formats_to_try:
        try:
            dt = datetime.strptime(pubdate_str, fmt)
            if is_year_only:
                dt = dt.replace(month=1, day=1)
            break
        except ValueError:
            continue
    if dt is None:
        # logging.debug(f"Could not parse date string: {pubdate_str}")
        return None
    try:
        jst = pytz.timezone('Asia/Tokyo')
        dt_aware = jst.localize(dt.replace(hour=0, minute=0, second=0, microsecond=0))
        return dt_aware
    except Exception as e:
        # logging.debug(f"Error localizing parsed date {dt} for input '{pubdate_str}': {e}")
        return None

def get_description(onix_data):
    """Extracts the description text (content summary or TOC) from ONIX data."""
    description = ""
    toc = ""
    try:
        if onix_data and isinstance(onix_data, dict):
            collateral_detail = onix_data.get('CollateralDetail')
            if collateral_detail and isinstance(collateral_detail, dict):
                text_content_list = collateral_detail.get('TextContent')
                if text_content_list and isinstance(text_content_list, list):
                    for content in text_content_list:
                        if isinstance(content, dict) and 'TextType' in content and 'Text' in content:
                            text_type = content.get('TextType')
                            text = content.get('Text', '')
                            if text_type == '03':
                                description = text
                                break
                            elif text_type == '02':
                                 toc = text
    except Exception as e:
        logging.warning(f"Error extracting description: {e}")
    final_description = description if description else toc
    # if final_description:
    #    final_description = re.sub('<[^<]+?>', '', final_description)
    return final_description

def filter_books(book_data_list):
    """Filters books based on target C-Codes ('78' scheme) and valid, parsable pubdate. (Includes detailed logging)"""
    filtered_list = []
    processed_count = 0
    matched_count = 0
    logging.info(f"Filtering {len(book_data_list)} book data items...")
    for book_data in book_data_list:
        processed_count += 1
        if not book_data or not isinstance(book_data, dict) or 'summary' not in book_data:
            logging.debug(f"Item {processed_count}: Skipping invalid book data structure.")
            continue
        summary = book_data.get('summary')
        if not isinstance(summary, dict):
            logging.debug(f"Item {processed_count}: Skipping due to non-dict summary.")
            continue
        isbn = summary.get('isbn')
        title = summary.get('title', '[No Title]')
        if not isbn or not summary.get('title'):
             logging.debug(f"Item {processed_count} (ISBN: {isbn or 'N/A'}): Skipping due to missing ISBN or title.")
             continue

        c_code_match = False
        c_code_found = None
        try:
            onix = book_data.get('onix')
            if isinstance(onix, dict):
                 descriptive_detail = onix.get('DescriptiveDetail')
                 if isinstance(descriptive_detail, dict):
                     subjects = descriptive_detail.get('Subject')
                     if isinstance(subjects, list):
                         for subject in subjects:
                             if (isinstance(subject, dict) and
                                 subject.get('SubjectSchemeIdentifier') == '78'):
                                 c_code_found = subject.get('SubjectCode')
                                 if c_code_found in TARGET_C_CODES:
                                     c_code_match = True
                                     break
        except Exception as e:
             logging.warning(f"ISBN {isbn} ('{title}'): Error accessing subject data: {e}. Assuming no C-Code match.")

        if c_code_match:
            pubdate_str = summary.get('pubdate')
            parsed_date = parse_pubdate(pubdate_str)
            if parsed_date:
                filtered_list.append((book_data, parsed_date))
                matched_count += 1
                logging.debug(f"ISBN {isbn} ('{title}'): MATCHED! (C-Code: {c_code_found}, Pubdate: {parsed_date})")
            else:
                if pubdate_str:
                    logging.debug(f"ISBN {isbn} ('{title}'): Skipping. Matched C-Code '{c_code_found}' but pubdate '{pubdate_str}' is unparsable/invalid.")
                else:
                    logging.debug(f"ISBN {isbn} ('{title}'): Skipping. Matched C-Code '{c_code_found}' but pubdate is missing.")
        else:
            if logging.getLogger().isEnabledFor(logging.DEBUG):
                if c_code_found is None:
                    logging.debug(f"ISBN {isbn} ('{title}'): Skipping because no C-Code with Scheme '78' was found.")
                else:
                    logging.debug(f"ISBN {isbn} ('{title}'): Skipping because found C-Code '{c_code_found}' (Scheme 78) is not in TARGET_C_CODES.")

    filtered_list.sort(key=lambda item: item[1], reverse=True)
    logging.info(f"Filtering complete. Processed {processed_count} items, found {matched_count} matching criteria.")
    return filtered_list

def generate_rss_feed(filtered_books):
    """Generates the RSS feed using feedgen and saves it to OUTPUT_FILE."""
    fg = FeedGenerator()
    feed_link_url = "https://analekt.github.io/shinsho/"

    fg.title(FEED_TITLE)
    fg.description(FEED_DESCRIPTION)
    fg.link(href=feed_link_url, rel='alternate')
    fg.language('ja')
    fg.copyright(FEED_COPYRIGHT)
    fg.managingEditor(FEED_WEBMASTER)
    fg.generator("https://github.com/analekt/shinsho")

    jst = pytz.timezone('Asia/Tokyo')
    now_jst = datetime.now(jst)
    fg.lastBuildDate(now_jst)

    books_for_feed = filtered_books[:MAX_FEED_ITEMS]
    logging.info(f"Generating feed with {len(books_for_feed)} items (limited from {len(filtered_books)}, max: {MAX_FEED_ITEMS}).")

    if books_for_feed:
        latest_pubdate = books_for_feed[0][1]
        fg.pubDate(latest_pubdate)
    else:
         fg.pubDate(now_jst)

    for book_data, parsed_pubdate in books_for_feed:
        summary = book_data.get('summary', {})
        onix = book_data.get('onix', {})
        isbn = summary.get('isbn')
        title = summary.get('title')
        author = summary.get('author', '')

        if not isbn or not title: continue

        fe = fg.add_entry()
        fe.title(title)
        fe.id(isbn)
        fe.link(href=f"{FEED_LINK_BASE}{isbn}", rel='alternate')
        if author:
            fe.author({'name': author})
        fe.description(get_description(onix))
        fe.pubDate(parsed_pubdate)

    try:
        # Use the OUTPUT_FILE constant here
        fg.rss_file(OUTPUT_FILE, pretty=True, encoding='utf-8')
        logging.info(f"Successfully wrote RSS feed to {OUTPUT_FILE}") # Uses the constant
        if not os.path.exists(OUTPUT_FILE):
             logging.warning(f"Despite success log, {OUTPUT_FILE} was not found on disk.")
        elif os.path.getsize(OUTPUT_FILE) == 0:
             logging.warning(f"{OUTPUT_FILE} was created but is empty.")
    except Exception as e:
        logging.error(f"Error writing RSS feed file {OUTPUT_FILE}: {e}")

# --- Main Execution Logic (Differential Update) ---
if __name__ == "__main__":
    start_time = time.time()
    logging.info("Starting differential feed generation process...")

    previous_isbn_set = load_previous_isbns()
    current_isbn_list = get_all_isbns()
    if not current_isbn_list:
        logging.error("Failed to retrieve current ISBN list. Exiting.")
        exit(1)
    current_isbn_set = set(current_isbn_list)

    if not previous_isbn_set:
        logging.info("First run detected (no previous ISBN file or invalid file).")
        save_current_isbns(current_isbn_list)
        logging.info("Generating initial empty feed.")
        generate_rss_feed([]) # Generate empty index.xml on first run
        new_isbn_set = set()
        logging.info("Initial ISBN list saved. Feed generated (empty). Exiting first run.")
    else:
        new_isbn_set = current_isbn_set - previous_isbn_set
        removed_isbn_set = previous_isbn_set - current_isbn_set
        logging.info(f"Found {len(new_isbn_set)} new ISBNs since last run.")
        if removed_isbn_set:
            logging.info(f"Detected {len(removed_isbn_set)} ISBNs removed from coverage.")

    new_book_data = []
    if new_isbn_set: # Only fetch details if there are new ISBNs
        new_isbn_list = sorted(list(new_isbn_set))
        logging.info(f"Fetching details for {len(new_isbn_list)} new ISBNs...")
        total_fetched_details = 0
        for i in range(0, len(new_isbn_list), CHUNK_SIZE):
            chunk = new_isbn_list[i:i + CHUNK_SIZE]
            details = get_book_details(chunk)
            if details:
                new_book_data.extend(details)
                total_fetched_details += len(details)
            if i + CHUNK_SIZE < len(new_isbn_list):
                time.sleep(REQUEST_DELAY)
        logging.info(f"Retrieved details for {total_fetched_details} out of {len(new_isbn_list)} new ISBNs.")
    # Don't need the 'else' for logging no new ISBNs if previous_isbn_set check is done

    if new_book_data:
        filtered_new_books = filter_books(new_book_data)
    else:
        filtered_new_books = []
        # Only log if it wasn't the first run
        if previous_isbn_set:
            logging.info("No new book details to filter (or no new ISBNs found).")

    # Generate feed (potentially empty if no matches, but not on first run)
    if previous_isbn_set: # Don't regenerate feed on first run here
        generate_rss_feed(filtered_new_books)

    # Save current list only on subsequent runs
    if previous_isbn_set:
        save_current_isbns(current_isbn_list)

    end_time = time.time()
    logging.info(f"Differential feed generation process finished in {end_time - start_time:.2f} seconds.")
# --- End Main Execution Logic ---
