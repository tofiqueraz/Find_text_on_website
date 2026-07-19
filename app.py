import html
import re
import time
from pathlib import Path

from flask import (
    Flask, render_template, request, send_file, abort
)

from crawler import crawl, write_csv, write_html

app = Flask(__name__)
PROJECT_DIR = Path(__file__).parent
CSV_PATH = PROJECT_DIR / "results.csv"
HTML_PATH = PROJECT_DIR / "results.html"


def parse_terms(raw):
    parts = re.split(r"[,\n]+", raw or "")
    return [p.strip() for p in parts if p.strip()]


def highlight_snippet(snippet, terms):
    escaped = html.escape(snippet)
    for term in sorted(terms, key=len, reverse=True):
        pattern = re.compile(r"\b" + re.escape(html.escape(term)) + r"\b", re.IGNORECASE)
        escaped = pattern.sub(lambda m: f"<mark>{m.group(0)}</mark>", escaped)
    return escaped


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


# Avoid Render logs / stray browser requests failing with 405/404.
@app.route("/favicon.ico")
def favicon():
    return "", 204



@app.route("/crawl", methods=["POST"])
def do_crawl():
    url = request.form.get("url", "").strip()
    terms_raw = request.form.get("terms", "")
    terms = parse_terms(terms_raw)
    timeout = int(request.form.get("timeout", 30) or 30)

    if not url:
        return render_template("index.html", error="Please enter a URL.",
                               url=url, terms=terms_raw, timeout=timeout)
    if not terms:
        return render_template("index.html", error="Please enter at least one search term.",
                               url=url, terms=terms_raw, timeout=timeout)

    config = {
        "start_url": url,
        "search_terms": terms,
        # Render worker memory/time is limited; default to a smaller crawl.
        "max_pages": 12,



        "same_domain_only": True,
        "case_sensitive": False,
        "headless": True,
        "timeout_ms": timeout * 1000,
    }

    start_time = time.time()
    try:
        findings, visited, abort_reason = crawl(config)
    except Exception as e:
        return render_template("index.html",
                               error=f"Crawl failed: {e}",
                               url=url, terms=terms_raw, timeout=timeout)
    duration = round(time.time() - start_time, 1)

    file_warning = None
    csv_available = False
    html_available = False
    try:
        write_csv(findings, str(CSV_PATH))
        csv_available = True
    except Exception as e:
        file_warning = f"Could not write results.csv ({e}). Results are still shown below."
        print(f"WARN: CSV write failed: {e}")
    try:
        write_html(findings, str(HTML_PATH), url, len(visited), terms)
        html_available = True
    except Exception as e:
        file_warning = (file_warning or "") + f" HTML file write also failed: {e}"
        print(f"WARN: HTML write failed: {e}")

    for row in findings:
        row["snippets"] = [highlight_snippet(s, terms) for s in row["snippets"]]
        # Ensure numeric/str counts render even if crawler returns unexpected types.
        try:
            row["count"] = int(row.get("count", 0))
        except Exception:
            row["count"] = 0


    total_hits = sum(r["count"] for r in findings)

    return render_template(
        "results.html",
        findings=findings,
        pages_crawled=len(visited),
        total_hits=total_hits,
        duration=duration,
        start_url=url,
        terms=terms,
        abort_reason=abort_reason,
        file_warning=file_warning,
        csv_available=csv_available,
        html_available=html_available,
    )


@app.route("/download/<fmt>")
def download(fmt):
    if fmt == "csv":
        if not CSV_PATH.exists():
            abort(404)
        return send_file(CSV_PATH, as_attachment=True, download_name="results.csv")
    if fmt == "html":
        if not HTML_PATH.exists():
            abort(404)
        return send_file(HTML_PATH, as_attachment=True, download_name="results.html")
    abort(404)


if __name__ == "__main__":
    print("=" * 60)
    print("  Find Text on Website  —  http://127.0.0.1:5001")
    print("=" * 60)
    app.run(host="127.0.0.1", port=5001, threaded=False, debug=False)
