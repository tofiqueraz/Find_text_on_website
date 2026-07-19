# TODO - Render Free stability optimizations

## Step 1 (Crawl stability)
- [x] Refactor `crawler.py` to avoid loading large HTML twice per page.
- [x] Extract links via DOM evaluation (`eval_on_selector_all`) instead of `page.content()` + BeautifulSoup for link graph.


## Step 2 (Memory + CPU caps)
- [ ] Add caps: `max_queue_size`, `max_links_per_page`, `max_findings`.
- [ ] Remove/limit per-page `gc.collect()` and reduce unnecessary waits (drop `networkidle`).

## Step 3 (Playwright resource blocking)
- [ ] Add `context.route()` to abort images/media/fonts to reduce memory.

## Step 4 (Regex performance)
- [ ] Precompile term matchers/patterns once per crawl.

## Step 5 (Timeout alignment)
- [ ] Adjust `render.yaml` / Gunicorn `--timeout` to exceed `max_total_runtime_s`.
- [ ] Keep `/crawl` functionality + UI unchanged.

## Step 6 (Validation)
- [ ] Local run sanity check on a small site.
- [ ] Trigger crawl to confirm no worker timeout.

