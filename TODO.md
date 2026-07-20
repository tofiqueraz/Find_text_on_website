# TODO - Fix internal crawling (BFS) up to max_pages

- [x] Update `crawler.py` visited/duplicate logic to key by `final_url` after redirects (normalize_url(page.url)) instead of the pre-navigation queued URL.

- [ ] Keep BFS queue behavior and existing extraction logic intact.
- [ ] Verify crawler can discover/enqueue internal pages and stops at `max_pages` (e.g., 15).
- [ ] Ensure CSV + HTML report generation still works.

