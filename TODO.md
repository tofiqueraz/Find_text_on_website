# TODO

- [x] Update `app.py` to reduce default `max_pages` to 8 (from 50).
- [x] Update `crawler.py` to cap per-page processing time (fixed Playwright timeout) and truncate visible text length before regex matching.
- [x] Update `crawler.py` to reduce `networkidle` wait time to ~250ms (or remove it) to reduce crawl latency.
- [x] Sanity check for syntax errors.
- [ ] Deploy to Render and verify crawl completes without 502/worker timeout.

- [ ] Fix Render 502 by reducing worst-case Playwright cost (optional: reduce max_pages default, and tighten per-page text wait / timeouts). 


- [x] Fix dynamic inner-page text loading (wait for meaningful `document.body.innerText` before extracting visible text) so terms like “gummies” are found reliably on ~20 inner pages.


