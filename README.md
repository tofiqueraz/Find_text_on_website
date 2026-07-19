# find_text

Crawl an entire website with Playwright and locate given words/phrases on every page. Results are saved to **CSV** and **HTML** with URL, page title, term, count, and surrounding snippets.

## Setup

```bash
cd /Users/codeclouds-tofique/Desktop/find_text
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
```

## Usage

### 1. Edit `config.json`

```json
{
  "start_url": "https://yourwebsite.com",
  "search_terms": ["drime", "trim", "find", "products"],
  "max_pages": 200,
  "same_domain_only": true,
  "case_sensitive": false,
  "headless": true,
  "timeout_ms": 30000,
  "output_csv": "results.csv",
  "output_html": "results.html"
}
```

### 2. Run

```bash
python crawler.py
```

### Override via CLI

```bash
python crawler.py --url https://example.com --terms drime trim find products
python crawler.py --max-pages 50 --show     # show the browser
```

## Output

- `results.csv` — open in Excel / Google Sheets
- `results.html` — open in any browser; styled table with clickable URLs and highlighted snippets

## Notes

- Only crawls links on the **same domain** by default (set `same_domain_only: false` to crawl off-site links too).
- Matches whole-word, case-insensitive by default.
- Skips binary files (PDF, images, video, archives, etc).
- Respects `max_pages` to avoid runaway crawls.
