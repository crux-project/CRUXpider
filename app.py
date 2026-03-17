from __future__ import annotations

import csv
import io
import logging
import os
import tempfile
from datetime import datetime

from flask import Flask, jsonify, render_template, request, send_file

from config import HOST, LOG_LEVEL, MAX_BATCH_SIZE, PORT, SECRET_KEY
from cruxpider_engine import CRUXpiderEngine


logging.basicConfig(level=getattr(logging, LOG_LEVEL.upper(), logging.INFO))
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config["SECRET_KEY"] = SECRET_KEY

engine = CRUXpiderEngine()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/status")
def status_page():
    return render_template("status.html")


@app.route("/api/docs")
def api_docs():
    return render_template("api_docs.html")


@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")


@app.route("/api/health")
def health_check():
    source_status = engine.get_source_status()
    return jsonify(
        {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "services": {
                "paperswithcode": source_status["paperswithcode_legacy_api"],
                "arxiv": source_status["arxiv"],
                "openalex": source_status["openalex"],
                "semantic_scholar": source_status["semantic_scholar"],
                "crossref": source_status["crossref"],
                "github_api": source_status["github_api"],
                "github_search_fallback": source_status["github_search_fallback"],
            },
            "version": "1.2.0",
            "notes": {
                "paperswithcode_redirect_target": source_status["paperswithcode_redirect_target"],
            },
        }
    )


@app.route("/api/status")
def api_status():
    source_status = engine.get_source_status()
    return jsonify(
        {
            "paperswithcode_available": source_status["paperswithcode_legacy_api"],
            "paperswithcode_redirect_target": source_status["paperswithcode_redirect_target"],
            "arxiv_available": source_status["arxiv"],
            "openalex_available": source_status["openalex"],
            "semantic_scholar_available": source_status["semantic_scholar"],
            "crossref_available": source_status["crossref"],
            "github_api_available": source_status["github_api"],
            "github_search_fallback": source_status["github_search_fallback"],
        }
    )


@app.route("/api/search_paper", methods=["POST"])
def search_paper():
    data = request.get_json(silent=True) or {}
    paper_title = (data.get("title") or "").strip()
    if not paper_title:
        return jsonify({"error": "请输入论文标题"}), 400

    result = engine.analyze_single_paper(paper_title)
    return jsonify(result)


@app.route("/api/find_relevant_papers", methods=["POST"])
def find_relevant_papers():
    data = request.get_json(silent=True) or {}
    paper_title = (data.get("title") or "").strip()
    max_papers = int(data.get("max_papers", 10))

    if not paper_title:
        return jsonify({"error": "请输入论文标题"}), 400

    papers = engine.find_relevant_papers(paper_title, max_papers)
    return jsonify(
        {
            "papers": papers,
            "grouped_papers": engine.group_relevant_papers(papers),
            "total": len(papers),
            "original_title": paper_title,
        }
    )


@app.route("/api/batch_process", methods=["POST"])
def batch_process():
    if "file" not in request.files:
        return jsonify({"error": "没有上传文件"}), 400

    upload = request.files["file"]
    if not upload.filename or not upload.filename.endswith(".csv"):
        return jsonify({"error": "请上传CSV文件"}), 400

    input_file = tempfile.NamedTemporaryFile(suffix=".csv", delete=False)
    input_path = input_file.name
    input_file.close()

    try:
        upload.save(input_path)
        titles = []
        with open(input_path, newline="", encoding="utf-8") as handle:
            reader = csv.reader(handle)
            for row in reader:
                if not row:
                    continue
                title = str(row[0]).strip()
                if title:
                    titles.append(title)

        if len(titles) > MAX_BATCH_SIZE:
            return jsonify({"error": f"单次批量处理最多支持 {MAX_BATCH_SIZE} 篇论文"}), 400

        rows = [engine.analyze_single_paper(title) for title in titles]

        text_buffer = io.StringIO()
        fieldnames = list(rows[0].keys()) if rows else ["title"]
        writer = csv.DictWriter(text_buffer, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

        buffer = io.BytesIO(text_buffer.getvalue().encode("utf-8"))
        return send_file(
            buffer,
            as_attachment=True,
            download_name=f"cruxpider_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mimetype="text/csv",
        )
    finally:
        if os.path.exists(input_path):
            os.unlink(input_path)


if __name__ == "__main__":
    debug = os.getenv("CRUXPIDER_DEBUG", "0") == "1"
    app.run(host=HOST, port=PORT, debug=debug)
