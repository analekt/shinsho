def generate_rss_feed(filtered_books):
    """Generates the RSS feed using feedgen and saves it to OUTPUT_FILE.
    Includes updated docs and generator elements.
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

    # Set generator element as requested
    fg.generator("https://github.com/analekt/shinsho/")

    # Set docs element as requested
    fg.docs("http://blogs.law.harvard.edu/tech/rss")

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
             pass # Omit author tag if empty

        fe.description(get_description(onix))
        fe.pubDate(parsed_pubdate) # Pass the timezone-aware datetime object

    # --- Output Feed ---
    try:
        # Generate RSS 2.0 feed, ensuring UTF-8 encoding
        fg.rss_file(OUTPUT_FILE, pretty=True, encoding='utf-8')
        logging.info(f"Successfully wrote RSS feed to {OUTPUT_FILE}")
        # Check if the file was actually created (useful for the deploy step condition)
        if not os.path.exists(OUTPUT_FILE):
             logging.warning(f"Despite success log, {OUTPUT_FILE} was not found on disk.")
        elif os.path.getsize(OUTPUT_FILE) == 0:
             logging.warning(f"{OUTPUT_FILE} was created but is empty.")

    except Exception as e:
        logging.error(f"Error writing RSS feed file {OUTPUT_FILE}: {e}")