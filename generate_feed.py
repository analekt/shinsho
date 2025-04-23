import requests
import time
from feedgen.feed import FeedGenerator
from datetime import datetime, timezone
import pytz
from email.utils import format_datetime
import logging
import re
import json # Added import
import os # Added import for checking file existence

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
OUTPUT_FILE = "feed.xml"
FEED_TITLE = "発売決定新書RSSフィード"
FEED_DESCRIPTION = "発売が確定した新書の情報をRSSリーダーで購読できます。"
FEED_LINK_BASE = "https://www.books.or.jp/book-details/"
FEED_WEBMASTER = "https://analekt.github.io/" # Or your contact info
FEED_COPYRIGHT = "© openBDプロジェクト、JPO出版情報登録センター"
PREVIOUS_ISBNS_FILE = "isbns_previous.json" # File to store previous ISBNs
MAX_FEED_ITEMS = 200 # Max items in the generated feed
# --- End Constants ---

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
# --- End Logging Setup ---

# --- Helper Functions ---

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
    logging.info(f"Fetching details for {len(isbn_list)} ISBNs from {OPENBD_API_GET_URL}...")
    try:
        isbn_string = ",".join(isbn_list)
        # Use POST request with 'isbn' parameter
        response = requests.post(OPENBD_API_GET_URL, data={'isbn': isbn_string}, timeout=180) # Further increased timeout
        response.raise_for_status()
        data = response.json()
        # Filter out null responses and ensure items are dicts
        valid_data = [item for item in data if item is not None and isinstance(item, dict)]
        logging.info(f"Successfully fetched details for {len(valid_data)} out of {len(isbn_list)} requested ISBNs.")
        return valid_data
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching book details batch starting with {isbn_list[:3]}...: {e}")
        return []
    except json.JSONDecodeError as e:
        logging.error(f"Error decoding JSON from get API batch starting with {isbn_list[:3]}...: {e}")
        return []

def parse_pubdate(pubdate_str):
    """Parses various date string formats (YYYYMMDD, YYYY, YYYY-MM-DD, YYYY年MM月DD日)
    into timezone-aware datetime objects (assumed JST). Returns None if parsing fails.
    """
    if not pubdate_str or not isinstance(pubdate_str, str):
        return None

    dt = None
    # Define formats to try, including Japanese style directly
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
                # Ensure month and day are set for year-only format
                dt = dt.replace(month=1, day=1)
            break # Success
        except ValueError:
            continue # Try next format

    # If parsing failed with all formats
    if dt is None:
        # logging.warning(f"Could not parse date string: {pubdate_str} with any known format.") # Reduce log noise
        return None

    # Try to make it timezone-aware (JST)
    try:
        jst = pytz.timezone('Asia/Tokyo')
        # Localize the datetime object (assuming naive dt represents JST)
        dt_aware = jst.localize(dt.replace(hour=0, minute=0, second=0, microsecond=0))
        return dt_aware
    except Exception as e:
        # Failed to localize (e.g., invalid date components after parsing?)
        # logging.warning(f"Error localizing parsed date {dt} for input '{pubdate_str}': {e}") # Reduce log noise
        return None


def get_description(onix_data):
    """Extracts the description text (content summary or TOC) from ONIX data.
    Prioritizes TextType '03' (summary), falls back to '02' (TOC).
    Returns an empty string if neither is found or data is invalid.
    """
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
                            if text_type == '03': # 内容紹介
                                description = text
                                break # Found primary description, stop searching
                            elif text_type == '02': # 目次
                                 toc = text
    except Exception as e:
        logging.warning(f"Error extracting description: {e}")

    final_description = description if description else toc
    # Optional: Basic HTML tag removal - uncomment if needed
    # if final_description:
    #    final_description = re.sub('<[^<]+?>', '', final_description)
    return final_description

def filter_books(book_data_list):
    """Filters books based on target C-Codes ('78' scheme) and valid, parsable pubdate.
    Returns a list of tuples: (book_data, parsed_pubdate_datetime)
    sorted by pubdate (newest first).
    """
    filtered_list = []
    processed_count = 0
    matched_count = 0
    logging.info(f"Filtering {len(book_data_list)} book data items...")

    for book_data in book_data_list:
        processed_count += 1
        # Basic validation
        if not book_data or not isinstance(book_data, dict) or 'summary' not in book_data:
            # logging.debug(f"Skipping invalid book data item: {book_data}")
            continue
        summary = book_data.get('summary')
        if not isinstance(summary, dict): continue
        isbn = summary.get('isbn')
        if not isbn or not summary.get('title'): continue # Skip if essential info missing

        # Check C-Code (Subject) - Updated Logic for Scheme '78'
        c_code_match = False
        try:
            onix = book_data.get('onix')
            if isinstance(onix, dict):
                 descriptive_detail = onix.get('DescriptiveDetail')
                 if isinstance(descriptive_detail, dict):
                     subjects = descriptive_detail.get('Subject')
                     if isinstance(subjects, list):
                         for subject in subjects:
                             if (isinstance(subject, dict) and
                                 subject.get('SubjectSchemeIdentifier') == '78' and # Check '78'
                                 subject.get('SubjectCode') in TARGET_C_CODES):     # Check updated codes
                                     c_code_match = True
                                     break
        except Exception as e:
             # Log unexpected structure issues but don't halt processing for one book
             logging.warning(f"Error accessing subject data for ISBN {isbn}: {e}. Assuming no C-Code match.")

        if not c_code_match:
            continue # Skip if no target C-Code found

        # Check and parse pubdate
        pubdate_str = summary.get('pubdate')
        parsed_date = parse_pubdate(pubdate_str)

        if parsed_date:
            # Add book data and its parsed date to the list
            filtered_list.append((book_data, parsed_date))
            matched_count += 1
        # else:
            # logging.debug(f"Skipping ISBN {isbn}: Missing or unparsable pubdate '{pubdate_str}'.") # Reduce noise

    # Sort books by publication date (newest first)
    filtered_list.sort(key=lambda item: item[1], reverse=True)

    logging.info(f"Filtering complete. Processed {processed_count} items, found {matched_count} matching criteria.")
    return filtered_list

def generate_rss_feed(filtered_books):
    """Generates the RSS feed using feedgen and saves it to OUTPUT_FILE.
    Limits the number of items in the feed to MAX_FEED_ITEMS.
    """
    fg = FeedGenerator()
    # Use the determined GitHub Pages URL for the feed's main link
    feed_link_url = "https://analekt.github.io/shinsho/"

    # --- Feed Header ---
    fg.title(FEED_TITLE)
    fg.description(FEED_DESCRIPTION)
    fg.link(href=feed_link_url, rel='alternate') # Set the determined base URL
    fg.language('ja')
    fg.copyright(FEED_COPYRIGHT)
    fg.managingEditor(FEED_WEBMASTER) # Using managingEditor for webMaster info
    fg.generator("OpenBD Feed Generator v0.1") # Simpler generator string

    # Set lastBuildDate to current time in JST
    jst = pytz.timezone('Asia/Tokyo')
    now_jst = datetime.now(jst)
    fg.lastBuildDate(now_jst) # feedgen handles formatting

    # Limit the books to the newest MAX_FEED_ITEMS
    books_for_feed = filtered_books[:MAX_FEED_ITEMS]
    logging.info(f"Generating feed with {len(books_for_feed)} items (limited from {len(filtered_books)}, max: {MAX_FEED_ITEMS}).")


    if books_for_feed:
        # Set feed's overall pubDate to the date of the newest item in the limited list
        # Items are sorted newest first
        latest_pubdate = books_for_feed[0][1] # The datetime object
        fg.pubDate(latest_pubdate)
    else:
         # If no books matching criteria are found for the feed, use current time
         fg.pubDate(now_jst)


    # --- Feed Items ---
    for book_data, parsed_pubdate in books_for_feed: # Iterate over the potentially limited list
        summary = book_data.get('summary', {})
        onix = book_data.get('onix', {})
        isbn = summary.get('isbn')
        title = summary.get('title')
        author = summary.get('author', '') # Default to empty string if missing

        # Double check essential data for the item
        if not isbn or not title:
             # logging.warning(f"Skipping item generation in feed due to missing ISBN or title: {summary}") # Reduce noise
             continue

        fe = fg.add_entry()
        fe.title(title)
        fe.id(isbn) # Use ISBN as the unique ID (GUID)
        # Link to the specific book details page
        fe.link(href=f"{FEED_LINK_BASE}{isbn}", rel='alternate')
        # Ensure author is passed correctly if not empty
        if author:
            fe.author({'name': author})
        else:
            # Add an empty author tag? Or omit? feedgen likely omits if None/empty.
             pass # Omit author tag if empty

        fe.description(get_description(onix))
        fe.pubDate(parsed_pubdate) # Pass the timezone-aware datetime object

    # --- Output Feed ---
    try:
        # Generate RSS 2.0 feed, ensuring UTF-8 encoding
        fg.rss_file(OUTPUT_FILE, pretty=True, encoding='utf-8')
        logging.info(f"Successfully wrote RSS feed to {OUTPUT_FILE}")
    except Exception as e:
        logging.error(f"Error writing RSS feed file {OUTPUT_FILE}: {e}")

# --- Main Execution Logic (Differential Update) ---
if __name__ == "__main__":
    start_time = time.time()
    logging.info("Starting differential feed generation process...")

    # 1. Load previous ISBNs (returns empty set if first run or error)
    previous_isbn_set = load_previous_isbns()

    # 2. Get current full ISBN list
    current_isbn_list = get_all_isbns()
    if not current_isbn_list:
        logging.error("Failed to retrieve current ISBN list. Exiting.")
        exit(1) # Critical error, cannot proceed
    current_isbn_set = set(current_isbn_list)

    # 3. Handle First Run or Determine New ISBNs
    if not previous_isbn_set:
        # First run scenario
        logging.info("First run detected (no previous ISBN file or invalid file).")
        # Save the current list for the *next* run
        save_current_isbns(current_isbn_list)
        # Generate an empty feed for this first run
        logging.info("Generating initial empty feed.")
        generate_rss_feed([])
        new_isbn_set = set() # Ensure no details are fetched on first run
    else:
        # Subsequent runs: find difference
        new_isbn_set = current_isbn_set - previous_isbn_set
        removed_isbn_set = previous_isbn_set - current_isbn_set # Optional: Log removed ISBNs
        logging.info(f"Found {len(new_isbn_set)} new ISBNs since last run.")
        if removed_isbn_set:
            logging.info(f"Detected {len(removed_isbn_set)} ISBNs removed from coverage.")

    # 4. Get details for new books only (if any)
    new_book_data = []
    if new_isbn_set:
        new_isbn_list = sorted(list(new_isbn_set)) # Sort for consistent chunking if needed
        logging.info(f"Fetching details for {len(new_isbn_list)} new ISBNs...")
        total_fetched_details = 0
        for i in range(0, len(new_isbn_list), CHUNK_SIZE):
            chunk = new_isbn_list[i:i + CHUNK_SIZE]
            # logging.info(f"Fetching details for new ISBN chunk {i // CHUNK_SIZE + 1}/{ (len(new_isbn_list) + CHUNK_SIZE - 1) // CHUNK_SIZE }...") # Reduce log noise
            details = get_book_details(chunk)
            if details:
                new_book_data.extend(details)
                total_fetched_details += len(details)
            # Add delay only if there are more chunks
            if i + CHUNK_SIZE < len(new_isbn_list):
                # logging.info(f"Sleeping for {REQUEST_DELAY} second(s)...") # Reduce log noise
                time.sleep(REQUEST_DELAY)
        logging.info(f"Retrieved details for {total_fetched_details} out of {len(new_isbn_list)} new ISBNs.")
    else:
        # Only log "no new ISBNs" if it wasn't the first run
        if previous_isbn_set:
             logging.info("No new ISBNs found since last run.")

    # 5. Filter new books based on criteria (C-Code, pubdate)
    if new_book_data:
        filtered_new_books = filter_books(new_book_data)
        # Logging is now inside filter_books
    else:
        filtered_new_books = []
        logging.info("No new book details to filter.")

    # 6. Generate RSS feed (contains only newly matched books from this run)
    generate_rss_feed(filtered_new_books)

    # 7. Save current full ISBN list for the *next* run (only if not first run, already saved there)
    if previous_isbn_set:
        save_current_isbns(current_isbn_list)

    end_time = time.time()
    logging.info(f"Differential feed generation process finished in {end_time - start_time:.2f} seconds.")
# --- End Main Execution Logic ---