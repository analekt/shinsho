import requests
import time
from feedgen.feed import FeedGenerator
from datetime import datetime, timezone
import pytz
from email.utils import format_datetime
import logging
import re

# --- Constants ---
OPENBD_API_COVERAGE_URL = "https://api.openbd.jp/v1/coverage"
OPENBD_API_GET_URL = "https://api.openbd.jp/v1/get"
TARGET_C_CODES = {
    "C0200", "C0201", "C0202", "C0204", "C0210", "C0211", "C0212", "C0214",
    "C0215", "C0216", "C0220", "C0221", "C0222", "C0223", "C0225", "C0226",
    "C0230", "C0231", "C0232", "C0233", "C0234", "C0236", "C0237", "C0239",
    "C0240", "C0241", "C0242", "C0243", "C0244", "C0245", "C0247", "C0250",
    "C0251", "C0252", "C0253", "C0254", "C0255", "C0256", "C0257", "C0258",
    "C0260", "C0261", "C0263", "C0265", "C0270", "C0271", "C0272", "C0273",
    "C0274", "C0275", "C0276", "C0277", "C0279", "C0280", "C0281", "C0282",
    "C0284", "C0285", "C0287", "C0290", "C0291", "C0292", "C0293", "C0295",
    "C0297", "C0298"
}
CHUNK_SIZE = 1000  # Max ISBNs per /get request
REQUEST_DELAY = 1  # Delay between /get requests in seconds
OUTPUT_FILE = "feed.xml"
FEED_TITLE = "発売決定新書RSSフィード"
FEED_DESCRIPTION = "発売が確定した新書の情報をRSSリーダーで購読できます。"
FEED_LINK_BASE = "https://www.books.or.jp/book-details/" # ISBN will be appended
FEED_WEBMASTER = "https://analekt.github.io/"
FEED_COPYRIGHT = "© openBDプロジェクト、JPO出版情報登録センター"
# --- End Constants ---

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
# --- End Logging Setup ---

# --- Helper Functions (To be implemented) ---
def get_all_isbns():
    """Retrieves the list of all ISBNs from the OpenBD coverage API."""
    try:
        # Increased timeout for potentially large response
        response = requests.get(OPENBD_API_COVERAGE_URL, timeout=60)
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
        isbns = response.json()
        if isinstance(isbns, list):
            # Ensure all items are strings, some might be numbers
            return [str(isbn) for isbn in isbns]
        else:
            logging.error(f"Unexpected data format from coverage API: {isbns}")
            return None
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching ISBN list: {e}")
        return None
    except ValueError as e: # Includes JSONDecodeError
        logging.error(f"Error decoding JSON from coverage API: {e}")
        return None

def get_book_details(isbn_list):
    """Fetches book details from the OpenBD get API for a list of ISBNs."""
    if not isbn_list:
        return []
    try:
        isbn_string = ",".join(isbn_list)
        # Using POST request with 'isbn' parameter
        # Increased timeout for potentially large response or slow API
        response = requests.post(OPENBD_API_GET_URL, data={'isbn': isbn_string}, timeout=60)
        response.raise_for_status()
        data = response.json()
        # The API returns null for ISBNs not found. Filter those out.
        # Also ensure each item is a dictionary before proceeding
        valid_data = [item for item in data if item is not None and isinstance(item, dict)]
        return valid_data
    except requests.exceptions.RequestException as e:
        # Log only the first few ISBNs to avoid overly long log messages
        logging.error(f"Error fetching book details for ISBNs {isbn_list[:5]}...: {e}")
        return []
    except ValueError as e: # Includes JSONDecodeError
        logging.error(f"Error decoding JSON from get API for ISBNs {isbn_list[:5]}...: {e}")
        return []

def parse_pubdate(pubdate_str):
    """Parses various date string formats (YYYYMMDD, YYYY, YYYY-MM-DD, YYYY年MM月DD日)
    into timezone-aware datetime objects (assumed JST).
    Returns None if parsing fails.
    """
    if not pubdate_str or not isinstance(pubdate_str, str):
        return None

    dt = None
    formats_to_try = [
        ("%Y%m%d", False), # YYYYMMDD
        ("%Y", True),      # YYYY (treat as Jan 1st)
        ("%Y-%m-%d", False), # YYYY-MM-DD
    ]

    # Try standard formats first
    for fmt, is_year_only in formats_to_try:
        try:
            dt = datetime.strptime(pubdate_str, fmt)
            if is_year_only:
                dt = dt.replace(month=1, day=1)
            break # Success
        except ValueError:
            continue # Try next format

    # If standard formats failed, try Japanese format
    if dt is None:
        try:
            cleaned_date = pubdate_str.replace('年', '-').replace('月', '-').replace('日', '')
            dt = datetime.strptime(cleaned_date, "%Y-%m-%d")
        except ValueError:
            logging.warning(f"Could not parse date string: {pubdate_str} with any known format.")
            return None

    # Assume JST timezone for publication dates based in Japan
    jst = pytz.timezone('Asia/Tokyo')
    # Make the datetime object timezone-aware (assuming JST)
    # For date-only formats, assume start of day (midnight)
    # Ensure dt is not None before localizing
    if dt:
        dt_aware = jst.localize(dt.replace(hour=0, minute=0, second=0, microsecond=0))
        return dt_aware
    else:
        # Should not happen if parsing succeeded, but as a safeguard
        logging.error("Internal error: dt became None after parsing attempt.")
        return None

def get_description(onix_data):
    """Extracts the description text (content summary or TOC) from ONIX data.
    Prioritizes TextType '03' (summary), falls back to '02' (TOC).
    Returns an empty string if neither is found or data is invalid.
    """
    # Basic validation of input structure
    if not onix_data or not isinstance(onix_data, dict): return ""
    collateral_detail = onix_data.get('CollateralDetail')
    if not collateral_detail or not isinstance(collateral_detail, dict): return ""
    text_content_list = collateral_detail.get('TextContent')
    if not text_content_list or not isinstance(text_content_list, list): return ""

    description = ""
    toc = ""

    for content in text_content_list:
        if isinstance(content, dict) and 'TextType' in content and 'Text' in content:
            text_type = content.get('TextType')
            text = content.get('Text', '')

            if text_type == '03': # 内容紹介
                description = text
                break # Found primary description, stop searching
            elif text_type == '02': # 目次
                 toc = text
        else:
            logging.debug(f"Skipping invalid content item in TextContent: {content}")

    # Return description if found, otherwise return TOC, otherwise return empty string
    final_description = description if description else toc
    # Basic HTML tag removal (optional, can be improved)
    # final_description = re.sub('<[^<]+?>', '', final_description) # Requires import re
    return final_description

def filter_books(book_data_list):
    """Filters books based on target C-Codes and valid, parsable pubdate.
    Returns a list of tuples: (book_data, parsed_pubdate_datetime)
    sorted by pubdate (newest first).
    """
    filtered_list = []
    seen_isbns = set() # To handle potential duplicates from API

    for book_data in book_data_list:
        # Basic validation and ensure 'summary' exists
        if not book_data or not isinstance(book_data, dict) or 'summary' not in book_data:
            logging.debug(f"Skipping invalid book data item: {book_data}")
            continue

        summary = book_data.get('summary')
        # Ensure summary is a dictionary before proceeding
        if not isinstance(summary, dict):
             logging.debug(f"Skipping book data with non-dict summary: {book_data}")
             continue

        isbn = summary.get('isbn')

        # Skip if essential data is missing or already processed
        # Title is essential for the feed item
        if not isbn or not summary.get('title') or isbn in seen_isbns:
            logging.debug(f"Skipping book ISBN {isbn}: Missing data or duplicate.")
            continue

        # Check C-Code (Subject)
        c_code_match = False
        try:
            # Navigate through the structure carefully, checking types
            onix = book_data.get('onix')
            if isinstance(onix, dict):
                 descriptive_detail = onix.get('DescriptiveDetail')
                 if isinstance(descriptive_detail, dict):
                     subjects = descriptive_detail.get('Subject')
                     if isinstance(subjects, list):
                         for subject in subjects:
                             if isinstance(subject, dict) and subject.get('SubjectSchemeIdentifier') == 'C6':
                                 subject_code = subject.get('SubjectCode')
                                 if subject_code in TARGET_C_CODES:
                                     c_code_match = True
                                     logging.debug(f"ISBN {isbn} matched C-Code {subject_code}")
                                     break # Found a match, no need to check further subjects
        except (AttributeError, TypeError, KeyError) as e:
             # Log unexpected structure issues but don't halt processing
             logging.warning(f"Error accessing subject data for ISBN {isbn}: {e}. Skipping C-Code check for this book.")
             # Depending on requirements, you might choose to `continue` here
             # If C-Code is strictly required, uncomment the next line:
             # continue

        if not c_code_match:
            logging.debug(f"Skipping ISBN {isbn}: No matching C-Code found.")
            continue # Skip if no target C-Code found

        # Check and parse pubdate
        pubdate_str = summary.get('pubdate')
        parsed_date = parse_pubdate(pubdate_str)

        if parsed_date:
            # Add book data and its parsed date to the list
            filtered_list.append((book_data, parsed_date))
            seen_isbns.add(isbn)
            logging.debug(f"Adding ISBN {isbn} (Pubdate: {parsed_date}) to filtered list.")
        else:
            # Log if pubdate was present but couldn't be parsed
            if pubdate_str:
                logging.debug(f"Skipping book ISBN {isbn} due to unparsable pubdate: {pubdate_str}")
            else:
                logging.debug(f"Skipping book ISBN {isbn} due to missing pubdate.")

    # Sort books by publication date (newest first)
    filtered_list.sort(key=lambda item: item[1], reverse=True)

    logging.info(f"Filtering complete. Kept {len(filtered_list)} books out of {len(book_data_list)} initial details.")
    return filtered_list

def generate_rss_feed(filtered_books):
    """Generates the RSS feed using feedgen and saves it to a file."""
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
    # Generator can be customized
    fg.generator("OpenBD Feed Generator v0.1") # Simpler generator string

    # Set lastBuildDate to current time in JST
    jst = pytz.timezone('Asia/Tokyo')
    now_jst = datetime.now(jst)
    fg.lastBuildDate(now_jst) # feedgen handles formatting

    # Set feed's overall pubDate to the date of the newest item
    if filtered_books:
        # Items are sorted newest first, so the first item has the latest pubDate
        latest_pubdate = filtered_books[0][1] # The datetime object
        fg.pubDate(latest_pubdate)
    else:
         # If no books, set pubDate to now as well
         fg.pubDate(now_jst)


    # --- Feed Items ---
    for book_data, parsed_pubdate in filtered_books:
        summary = book_data.get('summary', {})
        onix = book_data.get('onix', {})
        isbn = summary.get('isbn')
        title = summary.get('title')
        author = summary.get('author', '') # Default to empty string if missing

        # Double check essential data for the item
        if not isbn or not title:
             logging.warning(f"Skipping item generation due to missing ISBN or title: {summary}")
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
             pass # Omit author tag if empty

        fe.description(get_description(onix))
        fe.pubDate(parsed_pubdate) # Pass the timezone-aware datetime object

    # --- Output Feed ---
    try:
        # Generate RSS 2.0 feed
        fg.rss_file(OUTPUT_FILE, pretty=True) # pretty=True for readability
        logging.info(f"Successfully wrote RSS feed to {OUTPUT_FILE}")
    except Exception as e:
        logging.error(f"Error writing RSS feed file: {e}")

# --- End Helper Functions ---

# --- Main Execution Logic (To be implemented) ---
if __name__ == "__main__":
    logging.info("Starting feed generation process...")

    # 1. Get all ISBNs
    all_isbns = get_all_isbns()
    if not all_isbns:
        logging.error("Failed to retrieve ISBN list. Exiting.")
        exit(1)
    logging.info(f"Retrieved {len(all_isbns)} ISBNs.")

    # 2. Get book details in chunks
    all_book_data = []
    for i in range(0, len(all_isbns), CHUNK_SIZE):
        chunk = all_isbns[i:i + CHUNK_SIZE]
        logging.info(f"Fetching details for ISBN chunk {i // CHUNK_SIZE + 1}...")
        details = get_book_details(chunk)
        if details:
            all_book_data.extend(details)
        logging.info(f"Sleeping for {REQUEST_DELAY} second(s)...")
        time.sleep(REQUEST_DELAY)

    logging.info(f"Retrieved details for {len(all_book_data)} books (before filtering).")

    # 3. Filter books based on C-Code and valid pubdate
    filtered_books = filter_books(all_book_data)
    logging.info(f"Found {len(filtered_books)} books matching the criteria.")

    # 4. Generate RSS feed
    if filtered_books:
        generate_rss_feed(filtered_books)
        logging.info(f"RSS feed generated successfully: {OUTPUT_FILE}")
    else:
        logging.warning("No books matched the criteria. RSS feed not generated.")

    logging.info("Feed generation process finished.")
# --- End Main Execution Logic --- 