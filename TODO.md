# TODO - Fix Crawl Status & Progress Issues

## Completed Steps
- [x] Plan approved by user

# TODO - Fix Crawl Status & Progress Issues

## All Steps Completed ✅

### 1. crawler.py - Add debug logging & progress callback support
- [x] Add print statements at key points in `crawl()` for debugging
- [x] Accept an optional `progress_callback` parameter to update pages_crawled in real-time

### 2. app.py - Fix thread target & exception handling
- [x] Remove premature duration save before crawl starts
- [x] Add `import traceback` and capture full stack trace in `_run_job()`
- [x] Pass progress callback to `crawl()` to update `JOBS[job_id]` during crawl
- [x] Move duration calculation to after crawl completes
- [x] Fix duration being `None` in results (moved duration calc into `_run_job()`)

### 3. templates/results.html - Fix JavaScript polling
- [x] Update JS to dynamically show progress with pages_crawled from status endpoint
- [x] When job completes, dynamically render results instead of `window.location.reload()`
- [x] Show proper "Crawling… (X pages)" during crawl
- [x] Show current URL being crawled in progress display
- [x] Add error handling for network failures during polling
