# TODO

- [x] Update `app.py` to reduce default `max_pages` to 8 (from 50).
- [x] Update `crawler.py` to cap per-page processing time (fixed Playwright timeout) and truncate visible text length before regex matching.
- [x] Update `crawler.py` to reduce `networkidle` wait time to ~250ms (or remove it) to reduce crawl latency.
- [x] Sanity check for syntax errors.
- [x] Run local test crawl quickly (optional) and/or run unit-free sanity checks.
- [ ] Deploy to Render and verify crawl completes without 502/worker timeout.


