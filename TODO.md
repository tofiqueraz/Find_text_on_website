# TODO - Fix internal crawling (BFS) up to max_pages

- [x] Update `crawler.py` visited/duplicate logic to key by `final_url` after redirects (normalize_url(page.url)) instead of the pre-navigation queued URL.
- [x] Fix crawler exception indentation / flow so errors don’t prematurely abort crawl.
- [ ] Persist background job status to disk in `app.py` so Render Free doesn’t lose `/job/<id>/status` across processes (fixes Pages Crawled staying 0).
- [ ] Verify inner page crawling reaches `max_pages` (e.g., 15) on a real site like wholesalehealthclub.com.
- [ ] Ensure CSV + HTML generation still works after job status persistence.
