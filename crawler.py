import argparse
import csv
import html
import json
import re
import sys
import os
import gc
import time

from pathlib import Path
from collections import deque
from urllib.parse import urljoin, urlparse, urldefrag

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


def ensure_chromium_installed(timeout_s: int = 600) -> None:
    """Ensure Playwright's Chromium browser binary exists.

    Render may install only the Playwright python package but not download the
    actual browser binaries. When that happens, Playwright raises:

      BrowserType.launch: Executable doesn't exist at .../chrome-linux/chrome

    This function checks the expected Chromium executable path and runs
    `python -m playwright install chromium` if it's missing.
    """

    # Allow disabling auto-download for faster builds.
    if os.getenv("SKIP_PLAYWRIGHT_DOWNLOAD") == "1":
        return

    # Use Playwright to resolve the correct executable_path.
    with sync_playwright() as p:
        chrome_path = p.chromium.executable_path

    if chrome_path and Path(chrome_path).exists():
        return

    print(
        "Chromium executable not found (",
        chrome_path,
        "). Running `python -m playwright install chromium`...",
        flush=True,
    )

    import subprocess

    cmd = [sys.executable, "-m", "playwright", "install", "chromium"]
    subprocess.run(cmd, check=True, timeout=timeout_s)


def load_config(config_path):
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def normalize_url(url):
    url, _ = urldefrag(url)
    return url.rstrip("/")


def same_domain(url, root_netloc):
    try:
        host = urlparse(url).netloc.lower()
        root = root_netloc.lower()

        host = host.replace("www.", "")
        root = root.replace("www.", "")

        return host == root
    except Exception:
        return False


def is_crawlable(url):
    if not url:
        return False
    if url.startswith(("mailto:", "tel:", "javascript:", "#")):
        return False

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False

    # We only skip binary/document types.
    skip_ext = (
        ".pdf",
        ".zip",
        ".rar",
        ".mp4",
        ".mp3",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".ppt",
        ".pptx",
        ".css",
        ".js",
    )

    if parsed.path.lower().endswith(skip_ext):
        return False

    # Do not treat common image formats as crawl targets.
    # They won't have links we can crawl, but their surrounding HTML can still
    # be matched by extracting visible text from the HTML page.
    image_ext = (
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".avif",
        ".svg",
        ".gif",
        ".ico",
        ".bmp",
        ".tiff",
        ".tif",
        ".heic",
        ".heif",
        ".apng",
        ".jxl",
    )
    if parsed.path.lower().endswith(image_ext):
        return False

    return True


def extract_links(html_text, base_url):
    soup = BeautifulSoup(html_text, "html.parser")
    links = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href:
            continue

        # Skip javascript/mailto anchors and other non-http(s) targets early.
        if href.startswith(("mailto:", "tel:", "javascript:")):
            continue

        absolute = urljoin(base_url, href)
        absolute = normalize_url(absolute)
        if is_crawlable(absolute):
            links.add(absolute)

    # Return stable order to improve reproducibility.
    return links



def get_visible_text(html_text, max_chars: int = 20000):
    soup = BeautifulSoup(html_text, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator=" ", strip=True)
    # Hard cap to avoid memory/CPU blow-ups on very large pages.
    if len(text) > max_chars:
        text = text[:max_chars]
    return text




def find_term_matches(text, terms, case_sensitive):
    # Safety: if text is empty/too small, avoid regex work.
    if not text:
        return []

    """Find occurrences of each term in the visible page text."""

    results = []
    flags = 0 if case_sensitive else re.IGNORECASE

    for term in terms:
        term_str = str(term)


        # If term is strictly "wordy" keep \b behavior.
        if term_str and re.fullmatch(r"[A-Za-z0-9_]+", term_str):
            pattern = re.compile(r"\b" + re.escape(term_str) + r"\b", flags)
        else:
            # Fallback for numeric/non-word heavy tokens around punctuation.
            pattern = re.compile(re.escape(term_str), flags)

        matches = list(pattern.finditer(text))
        if not matches:
            continue

        snippets = []
        for m in matches[:5]:
            start = max(0, m.start() - 40)
            end = min(len(text), m.end() + 40)
            snippet = text[start:end].replace("\n", " ").strip()
            snippets.append(snippet)

        results.append({"term": term_str, "count": len(matches), "snippets": snippets})

    return results


def crawl(config):
    start_time_overall = time.time()
    start_url = normalize_url(config["start_url"])

    root_netloc = urlparse(start_url).netloc
    search_terms = config["search_terms"]

    max_pages = min(int(config.get("max_pages", 50)), 50)
    same_only = bool(config.get("same_domain_only", True))
    case_sensitive = bool(config.get("case_sensitive", False))
    headless = bool(config.get("headless", True))
    timeout_ms = int(config.get("timeout_ms", 30000))

    queue = deque([start_url])
    visited = set()
    findings = []

    consecutive_failures = 0
    max_consecutive_failures = 8
    abort_reason = None

    # Render workers may be killed before Playwright timeouts if the
    # overall request takes too long. Keep a global budget.
    max_total_runtime_s = float(config.get("max_total_runtime_s", 80))


    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-extensions",
                "--disable-background-networking",
                "--disable-sync",
                "--disable-default-apps",
                "--disable-renderer-backgrounding",
                "--memory-pressure-off",
            ],
        )

        try:
            context = browser.new_context(
                viewport={"width": 1280, "height": 720},
                java_script_enabled=True,
                ignore_https_errors=True,
            )

            try:
                while queue and len(visited) < max_pages:
                    # Global budget guard (helps avoid Render 502 / worker kill).
                    if time.time() - start_time_overall > max_total_runtime_s:
                        abort_reason = "Global runtime limit reached"
                        break

                    url = queue.popleft()

                    if url in visited:
                        continue

                    visited.add(url)
                    print(f"[{len(visited)}/{max_pages}] Crawling: {url}")

                    page = None
                    try:

                        page = context.new_page()
                        page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")

                        # Render may populate key content after DOMContentLoaded.
                        # Wait briefly for the page to have “meaningful” innerText.
                        try:
                            page.wait_for_load_state("networkidle", timeout=250)
                        except PlaywrightTimeoutError:
                            pass

                        # Safety-bounded dynamic wait (helps pages that load text via JS)
                        dynamic_wait_ms = min(timeout_ms, 900)

                        try:
                            page.wait_for_function(
                                "() => document.body && document.body.innerText && document.body.innerText.length > 80",
                                timeout=dynamic_wait_ms,
                            )
                        except PlaywrightTimeoutError:
                            pass

                        # Keep per-page processing time bounded even if the page is slow.
                        page.set_default_timeout(min(timeout_ms, 2500))



                        final_url = normalize_url(page.url)

                        root_netloc = urlparse(final_url).netloc

                        title = page.title()

                        # Avoid storing/processing huge HTML blobs.
                        # Extract text directly from the live DOM.
                        text = ""
                        try:
                            text = page.inner_text("body", timeout=1000)
                        except Exception:
                            html_content = page.content()
                            text = get_visible_text(html_content, max_chars=12000)

                        # Cap text size and processing to keep Render worker stable.
                        if len(text) > 12000:
                            text = text[:12000]

                        # We still need HTML for link extraction.
                        if "html_content" not in locals():
                            html_content = page.content()

                        # Cap term processing; too many terms can explode CPU.
                        terms_limited = search_terms[:20]


                        matches = find_term_matches(text, terms_limited, case_sensitive)


                        if matches:
                            for m in matches:
                                findings.append(
                                    {
                                        "url": final_url,
                                        "title": title,
                                        "term": m["term"],
                                        "count": m["count"],
                                        "snippets": m["snippets"],
                                    }
                                )

                        # Extracting & crawling links can also explode work; cap link count per page.
                        links = list(extract_links(html_content, final_url))[:50]

                        # Fallback: landing pages sometimes have no crawlable <a href> links
                        # in the HTML we receive (or they get filtered). Ensure we can still
                        # progress by enqueueing a few likely same-domain internal URLs.
                        if not links:
                            parsed_base = urlparse(final_url)
                            base_root = f"{parsed_base.scheme}://{parsed_base.netloc}"
                            fallback_paths = (
                                "/",
                                "/about",
                                "/products",
                                "/product",
                                "/services",
                                "/contact",
                                "/blog",
                                "/shop",
                            )
                            for pth in fallback_paths:
                                candidate = normalize_url(base_root + pth)
                                if not candidate or candidate in visited or candidate in queue:
                                    continue
                                if not is_crawlable(candidate):
                                    continue
                                if same_only and not same_domain(candidate, root_netloc):
                                    continue
                                queue.append(candidate)

                        # Always enqueue links discovered on the page; do not require
                        # the link to already be in the queue (only de-dupe via `visited`).
                        for link in links:

                            if link in visited:
                                continue
                            if same_only and not same_domain(link, root_netloc):
                                continue
                            if link not in queue:
                                queue.append(link)


                        consecutive_failures = 0

                    except PlaywrightTimeoutError:
                        print(f"Timeout -> {url}")
                        consecutive_failures += 1
                        if consecutive_failures >= max_consecutive_failures:
                            abort_reason = "Too many timeouts"
                            break

                    except Exception as e:
                        print(f"Error -> {url}")
                        print(e)
                        # Don’t let one bad page kill the crawl.
                        consecutive_failures += 1

                        if consecutive_failures >= max_consecutive_failures:
                            abort_reason = "Too many errors"
                            break

                    finally:
                        if page:
                            try:
                                page.close()
                            except Exception:
                                pass
                        gc.collect()

            finally:
                context.close()

        finally:
            browser.close()

    return findings, visited, abort_reason


def write_csv(findings, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["URL", "Page Title", "Search Term", "Match Count", "Snippets"])

        for row in findings:
            writer.writerow(
                [
                    row.get("url", ""),
                    row.get("title", ""),
                    row.get("term", ""),
                    row.get("count", 0),
                    " | ".join(row.get("snippets", []) or []),
                ]
            )

    print(f"CSV saved: {path}")


def write_html(findings, path, start_url, pages_crawled, terms):
    rows_html = []
    for row in findings:
        snippets_html = "<br>".join(
            f"<em>…{html.escape(s)}…</em>" for s in (row.get("snippets") or [])
        )
        rows_html.append(
            f"""
        <tr>
          <td><a href="{html.escape(row.get('url',''))}" target="_blank">{html.escape(row.get('url',''))}</a></td>
          <td>{html.escape(row.get('title') or '')}</td>
          <td><span class="term">{html.escape(row.get('term') or '')}</span></td>
          <td class="count">{row.get('count', 0)}</td>
          <td>{snippets_html}</td>
        </tr>"""
        )

    rows_str = (
        "\n".join(rows_html)
        if rows_html
        else "<tr><td colspan='5' style='text-align:center;padding:20px;'>No matches found.</td></tr>"
    )

    document = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Text Search Results</title>
<style>
  body {{ font-family: -apple-system, Segoe UI, sans-serif; margin: 24px; color: #222; }}
  h1 {{ margin-bottom: 4px; }}
  .meta {{ color: #666; margin-bottom: 20px; }}
  table {{ border-collapse: collapse; width: 100%; background: #fff; }}
  th, td {{ border: 1px solid #ddd; padding: 10px; vertical-align: top; text-align: left; }}
  th {{ background: #f4f4f4; }}
  tr:nth-child(even) {{ background: #fafafa; }}
  .term {{ background: #ffe680; padding: 2px 6px; border-radius: 3px; font-weight: 600; }}
  .count {{ text-align: center; font-weight: bold; }}
  a {{ color: #1565c0; text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  em {{ color: #444; font-style: normal; }}
</style>
</head>
<body>
  <h1>Text Search Results</h1>
  <div class="meta">
    <div><strong>Start URL:</strong> {html.escape(start_url)}</div>
    <div><strong>Pages crawled:</strong> {pages_crawled}</div>
    <div><strong>Search terms:</strong> {html.escape(", ".join(terms))}</div>
    <div><strong>Total matches found:</strong> {len(findings)}</div>
  </div>
  <table>
    <thead>
      <tr>
        <th>URL</th>
        <th>Page Title</th>
        <th>Term</th>
        <th>Count</th>
        <th>Snippets</th>
      </tr>
    </thead>
    <tbody>{rows_str}
    </tbody>
  </table>
</body>
</html>"""

    Path(path).write_text(document, encoding="utf-8")
    print(f"HTML saved: {path}")


def main():
    parser = argparse.ArgumentParser(description="Crawl a website and find given words on every page.")
    parser.add_argument("--config", default="config.json", help="Path to config.json")
    parser.add_argument("--url", help="Override start URL")
    parser.add_argument("--terms", nargs="+", help="Override search terms")
    parser.add_argument("--max-pages", type=int, help="Override max pages")
    parser.add_argument("--headless", action="store_true", help="Run headless")
    parser.add_argument("--show", action="store_true", help="Run with visible browser")
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        print(f"Config not found: {config_path}", file=sys.stderr)
        sys.exit(1)

    config = load_config(config_path)

    if args.url:
        config["start_url"] = args.url
    if args.terms:
        config["search_terms"] = args.terms
    if args.max_pages:
        config["max_pages"] = args.max_pages

    if args.show:
        config["headless"] = False
    if args.headless:
        config["headless"] = True

    if not config.get("search_terms"):
        print("No search terms provided.", file=sys.stderr)
        sys.exit(1)

    print(f"Start URL    : {config['start_url']}")
    print(f"Search terms : {config['search_terms']}")
    print(f"Max pages    : {config.get('max_pages', 20)}")
    print("-" * 60)

    findings, visited, abort_reason = crawl(config)

    print("-" * 60)
    if abort_reason:
        print(f"WARNING: {abort_reason}")
    print(f"Crawled {len(visited)} pages, found {len(findings)} term-matches.")

    write_csv(findings, config.get("output_csv", "results.csv"))
    write_html(
        findings,
        config.get("output_html", "results.html"),
        config["start_url"],
        len(visited),
        config["search_terms"],
    )


if __name__ == "__main__":
    main()

