import html
import json
import re
import time
from pathlib import Path

from flask import (
    Flask, redirect, render_template, request, send_file, url_for, abort
)

from crawler import crawl, write_csv, write_html


app = Flask(__name__)
PROJECT_DIR = Path(__file__).parent
CSV_PATH = PROJECT_DIR / "results.csv"
HTML_PATH = PROJECT_DIR / "results.html"
JOBS_DIR = PROJECT_DIR / "jobs"


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



# --- Background crawl job system (prevents Render worker timeouts) ---
import uuid
from threading import Thread

# In-memory job store (Render Free may still run multiple processes).
JOBS = {}


def _job_dir(job_id: str) -> Path:
    d = PROJECT_DIR / "jobs" / job_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _job_status_path(job_id: str) -> Path:
    # Persist status to disk so /job/<id>/status works even if
    # requests hit different Render processes.
    return _job_dir(job_id) / "job.json"


def _save_job(job_id: str) -> None:
    job = JOBS.get(job_id)
    if not job:
        return
    path = _job_status_path(job_id)
    # Best-effort atomic-ish write.
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _load_job(job_id: str) -> dict | None:
    path = _job_status_path(job_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _run_job(job_id: str, config: dict, terms: list[str]):
    try:
        findings, visited, abort_reason = crawl(config)

        # Highlight snippets once for HTML output.
        for row in findings:
            row["snippets"] = [highlight_snippet(s, terms) for s in row["snippets"]]
            try:
                row["count"] = int(row.get("count", 0))
            except Exception:
                row["count"] = 0

        total_hits = sum(r["count"] for r in findings)

        job_path = _job_dir(job_id)
        csv_path = job_path / "results.csv"
        html_path = job_path / "results.html"

        write_csv(findings, str(csv_path))
        write_html(
            findings,
            str(html_path),
            config["start_url"],
            len(visited),
            terms,
        )

        JOBS[job_id].update(
            {
                "status": "done",
                "abort_reason": abort_reason,
                "pages_crawled": len(visited),
                "total_hits": total_hits,
                "duration": JOBS[job_id]["duration"],
                "csv_ready": True,
                "html_ready": True,
            }
        )
        _save_job(job_id)
    except Exception as e:
        JOBS[job_id].update({"status": "error", "error": str(e)})
        _save_job(job_id)


@app.route("/crawl", methods=["POST"])
def do_crawl():
    url = request.form.get("url", "").strip()

    terms_raw = request.form.get("terms", "")
    terms = parse_terms(terms_raw)
    timeout = int(request.form.get("timeout", 30) or 30)

    if not url:
        return render_template(
            "index.html",
            error="Please enter a URL.",
            url=url,
            terms=terms_raw,
            timeout=timeout,
        )
    if not terms:
        return render_template(
            "index.html",
            error="Please enter at least one search term.",
            url=url,
            terms=terms_raw,
            timeout=timeout,
        )

    job_id = str(uuid.uuid4())
    start_ts = time.time()

    config = {
        "start_url": url,
        "search_terms": terms,
        "max_pages": 20,
        "max_queue_size": 120,
        "max_findings": 200,
        "same_domain_only": True,
        "case_sensitive": False,
        "headless": True,
        "timeout_ms": min(timeout * 1000, 12000),
        "max_total_runtime_s": 70,
    }

    # Initialize job state.
    JOBS[job_id] = {
        "status": "running",
        "start_url": url,
        "terms": terms,
        "duration": None,
        "csv_ready": False,
        "html_ready": False,
        "started_at": start_ts,
    }
    _save_job(job_id)

    def _thread_target():
        try:
            JOBS[job_id]["duration"] = round(time.time() - start_ts, 1)
            _save_job(job_id)
            _run_job(job_id, config, terms)
        except Exception as e:
            JOBS[job_id].update({"status": "error", "error": str(e)})
            _save_job(job_id)

    t = Thread(target=_thread_target, daemon=True)
    t.start()

    # Redirect to GET-based results page to avoid POST re-submit on reload.
    return redirect(url_for("show_results", job_id=job_id))




@app.route("/results/<job_id>", methods=["GET"])
def show_results(job_id):
    """GET-based results page. Renders immediately; polls /job/<id>/status."""
    job = JOBS.get(job_id)
    if not job:
        job = _load_job(job_id)
        if not job:
            return render_template("index.html", error="Job not found.")
        JOBS[job_id] = job

    start_url = job.get("start_url", "")
    terms = job.get("terms", [])
    pages_crawled = 0
    total_hits = 0
    duration = 0
    findings = []
    csv_available = False
    html_available = False
    abort_reason = None
    file_warning = None
    status = job.get("status", "running")

    if status == "done":
        job_path = _job_dir(job_id)
        csv_path = job_path / "results.csv"
        html_path = job_path / "results.html"
        csv_available = csv_path.exists()
        html_available = html_path.exists()

        pages_crawled = job.get("pages_crawled", 0)
        total_hits = job.get("total_hits", 0)
        duration = job.get("duration", 0)
        abort_reason = job.get("abort_reason")
        findings = []

    return render_template(
        "results.html",
        job_id=job_id,
        status=status,
        pages_crawled=pages_crawled,
        findings=findings,
        total_hits=total_hits,
        duration=duration,
        start_url=start_url,
        terms=terms,
        csv_available=csv_available,
        html_available=html_available,
        abort_reason=abort_reason,
        file_warning=file_warning,
    )


@app.route("/job/<job_id>/status", methods=["GET"])
def job_status(job_id):
    job = JOBS.get(job_id)
    if not job:
        # Fallback to disk (cross-process support).
        job = _load_job(job_id)
        if not job:
            return {"status": "not_found"}, 404
        JOBS[job_id] = job
    return job


@app.route("/download/<fmt>")
def download(fmt):
    # Backwards-compat: serve the latest completed results.
    if not JOBS:
        abort(404)

    # Pick the most recently finished job.
    finished = [j for j in JOBS.values() if j.get("status") == "done" and (j.get("csv_ready") or j.get("html_ready"))]
    if not finished:
        abort(404)

    latest_job_id = None
    latest_started = -1
    for jid, job in JOBS.items():
        if job.get("status") == "done" and job.get("started_at", 0) > latest_started:
            latest_started = job.get("started_at", 0)
            latest_job_id = jid

    if not latest_job_id:
        abort(404)

    job_path = _job_dir(latest_job_id)

    if fmt == "csv":
        csv_path = job_path / "results.csv"
        if not csv_path.exists():
            abort(404)
        return send_file(csv_path, as_attachment=True, download_name="results.csv")
    if fmt == "html":
        html_path = job_path / "results.html"
        if not html_path.exists():
            abort(404)
        return send_file(html_path, as_attachment=True, download_name="results.html")

    abort(404)



if __name__ == "__main__":
    print("=" * 60)
    print("  Find Text on Website  —  http://127.0.0.1:5001")
    print("=" * 60)
    app.run(host="127.0.0.1", port=5001, threaded=False, debug=False)
