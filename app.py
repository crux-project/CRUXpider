from __future__ import annotations

import logging
import io
import os
import tempfile
from datetime import datetime
from functools import lru_cache
from typing import Any
from urllib.parse import quote_plus

import arxiv
import pandas as pd
import pyalex
import requests
from flask import Flask, jsonify, render_template, request, send_file
from pyalex import Works

from config import (
    HOST,
    LOG_LEVEL,
    MAX_BATCH_SIZE,
    PAPERSWITHCODE_API_BASE,
    PORT,
    PYALEX_EMAIL,
    REQUEST_TIMEOUT_SECONDS,
    SECRET_KEY,
)


logging.basicConfig(level=getattr(logging, LOG_LEVEL.upper(), logging.INFO))
logger = logging.getLogger(__name__)

if PYALEX_EMAIL:
    pyalex.config.email = PYALEX_EMAIL


app = Flask(__name__)
app.config["SECRET_KEY"] = SECRET_KEY

AI_CATEGORIES = {"stat.ML", "cs.AI", "cs.CV", "cs.LG", "cs.CL", "cs.RO"}


class CRUXpiderAnalyzer:
    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "CRUXpider/1.0"})

    def analyze_single_paper(self, paper_title: str) -> dict[str, Any]:
        result: dict[str, Any] = {
            "title": paper_title,
            "journal": None,
            "journal_conference": None,
            "pdf_url": None,
            "categories": [],
            "ai_related": "NO",
            "datasets": [],
            "methods": [],
            "repository_url": "N/A",
            "warnings": [],
            "source_status": self.get_source_status(),
        }

        arxiv_info = self._get_arxiv_info(paper_title)
        if arxiv_info:
            result.update(arxiv_info)

        openalex_info = self._get_openalex_info(paper_title)
        if openalex_info:
            if not result.get("journal_conference") and openalex_info.get("journal_conference"):
                result["journal_conference"] = openalex_info["journal_conference"]
                result["journal"] = openalex_info["journal_conference"]
            if not result.get("pdf_url") and openalex_info.get("pdf_url"):
                result["pdf_url"] = openalex_info["pdf_url"]
            if not result.get("categories") and openalex_info.get("categories"):
                result["categories"] = openalex_info["categories"]
                result["ai_related"] = self._infer_ai_related(openalex_info["categories"])

        repository_url, warning = self._build_repository_fallback(paper_title)
        result["repository_url"] = repository_url
        if warning:
            result["warnings"].append(warning)

        return result

    @lru_cache(maxsize=1)
    def get_source_status(self) -> dict[str, Any]:
        status = {
            "paperswithcode_legacy_api": False,
            "paperswithcode_redirect_target": None,
            "arxiv": True,
            "openalex": True,
            "github_search_fallback": True,
        }

        try:
            response = self.session.get(
                f"{PAPERSWITHCODE_API_BASE}papers/",
                timeout=REQUEST_TIMEOUT_SECONDS,
                allow_redirects=False,
            )
            if response.status_code in {301, 302, 303, 307, 308}:
                status["paperswithcode_redirect_target"] = response.headers.get("Location")
            elif response.ok:
                status["paperswithcode_legacy_api"] = True
        except requests.RequestException as exc:
            logger.warning("Legacy Papers with Code API check failed: %s", exc)

        return status

    @lru_cache(maxsize=128)
    def find_relevant_papers(self, paper_title: str, max_papers: int = 10) -> list[dict[str, Any]]:
        try:
            search_result = Works().search_filter(title=paper_title).get()
            if not search_result:
                return []

            original_work = search_result[0]
            openalex_id = original_work.get("id", "")
            if not openalex_id:
                return []

            work_detail = Works()[openalex_id.replace("https://openalex.org/", "")]
            related_urls = work_detail.get("related_works", [])[:max_papers]

            papers: list[dict[str, Any]] = []
            for work_url in related_urls:
                try:
                    work_id = work_url.replace("https://openalex.org/", "")
                    work = Works()[work_id]
                    authors = [
                        authorship["author"]["display_name"]
                        for authorship in work.get("authorships", [])[:3]
                        if authorship.get("author", {}).get("display_name")
                    ]
                    location = work.get("primary_location") or {}
                    papers.append(
                        {
                            "title": work.get("title", "Unknown title"),
                            "authors": authors,
                            "year": work.get("publication_year"),
                            "url": location.get("landing_page_url") or "",
                        }
                    )
                except Exception as exc:
                    logger.warning("Skipping related paper due to OpenAlex error: %s", exc)
            return papers
        except Exception as exc:
            logger.warning("OpenAlex related paper lookup failed: %s", exc)
            return []

    def _get_arxiv_info(self, title: str) -> dict[str, Any] | None:
        try:
            search = arxiv.Search(query=f'ti:"{title}"', max_results=3)
            best_match = None
            for candidate in search.results():
                best_match = candidate
                if self._normalize_title(candidate.title) == self._normalize_title(title):
                    break

            if not best_match:
                return None

            categories = list(best_match.categories or [])
            journal = best_match.journal_ref or None
            return {
                "journal": journal,
                "journal_conference": journal,
                "pdf_url": best_match.pdf_url,
                "categories": categories,
                "ai_related": self._infer_ai_related(categories),
            }
        except Exception as exc:
            logger.warning("arXiv lookup failed: %s", exc)
            return None

    def _get_openalex_info(self, title: str) -> dict[str, Any] | None:
        try:
            search_results = Works().search(title).get()
            if not search_results:
                return None

            for work in search_results[:5]:
                work_title = work.get("title") or ""
                if not self._titles_look_similar(title, work_title):
                    continue

                source_name = self._extract_source_name(work)
                concepts = [
                    concept.get("display_name")
                    for concept in work.get("concepts", [])[:5]
                    if concept.get("display_name")
                ]
                location = work.get("primary_location") or {}
                pdf_url = location.get("pdf_url") or location.get("landing_page_url")
                return {
                    "journal_conference": source_name,
                    "pdf_url": pdf_url,
                    "categories": concepts,
                }
        except Exception as exc:
            logger.warning("OpenAlex metadata lookup failed: %s", exc)

        return None

    def _extract_source_name(self, work: dict[str, Any]) -> str | None:
        primary_location = work.get("primary_location") or {}
        source = primary_location.get("source") or {}
        source_name = source.get("display_name")
        if source_name and "arxiv" not in source_name.lower():
            return source_name

        for location in work.get("locations", []):
            location_source = (location or {}).get("source") or {}
            candidate = location_source.get("display_name")
            if candidate and "arxiv" not in candidate.lower():
                return candidate

        if source_name:
            return source_name
        return None

    def _build_repository_fallback(self, title: str) -> tuple[str, str | None]:
        search_url = f"https://github.com/search?q={quote_plus(title)}&type=repositories"
        source_status = self.get_source_status()
        if source_status.get("paperswithcode_redirect_target"):
            warning = (
                "Legacy Papers with Code API now redirects to Hugging Face Papers; "
                "repository results currently fall back to GitHub search."
            )
            return search_url, warning
        return search_url, None

    def _infer_ai_related(self, categories: list[str]) -> str:
        lowered = {category.lower() for category in categories}
        if any(tag.lower() in lowered for tag in AI_CATEGORIES):
            return "YES"

        keywords = ("learning", "neural", "vision", "language", "transformer", "llm", "ai")
        if any(any(keyword in category.lower() for keyword in keywords) for category in categories):
            return "YES"
        return "NO"

    def _normalize_title(self, title: str) -> str:
        return " ".join("".join(ch.lower() if ch.isalnum() else " " for ch in title).split())

    def _titles_look_similar(self, left: str, right: str) -> bool:
        normalized_left = self._normalize_title(left)
        normalized_right = self._normalize_title(right)
        if normalized_left == normalized_right:
            return True

        left_tokens = set(normalized_left.split())
        right_tokens = set(normalized_right.split())
        if not left_tokens or not right_tokens:
            return False
        overlap = len(left_tokens & right_tokens) / max(1, min(len(left_tokens), len(right_tokens)))
        return overlap >= 0.6


analyzer = CRUXpiderAnalyzer()


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
    source_status = analyzer.get_source_status()
    return jsonify(
        {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "services": {
                "paperswithcode": source_status["paperswithcode_legacy_api"],
                "arxiv": source_status["arxiv"],
                "pyalex": source_status["openalex"],
                "database": False,
                "github_search_fallback": source_status["github_search_fallback"],
            },
            "version": "1.1.0",
            "notes": {
                "paperswithcode_redirect_target": source_status["paperswithcode_redirect_target"],
            },
        }
    )


@app.route("/api/status")
def api_status():
    source_status = analyzer.get_source_status()
    return jsonify(
        {
            "paperswithcode_available": source_status["paperswithcode_legacy_api"],
            "paperswithcode_redirect_target": source_status["paperswithcode_redirect_target"],
            "arxiv_available": source_status["arxiv"],
            "pyalex_available": source_status["openalex"],
            "github_search_fallback": source_status["github_search_fallback"],
        }
    )


@app.route("/api/search_paper", methods=["POST"])
def search_paper():
    data = request.get_json(silent=True) or {}
    paper_title = (data.get("title") or "").strip()
    if not paper_title:
        return jsonify({"error": "请输入论文标题"}), 400

    result = analyzer.analyze_single_paper(paper_title)
    return jsonify(result)


@app.route("/api/find_relevant_papers", methods=["POST"])
def find_relevant_papers():
    data = request.get_json(silent=True) or {}
    paper_title = (data.get("title") or "").strip()
    max_papers = int(data.get("max_papers", 10))

    if not paper_title:
        return jsonify({"error": "请输入论文标题"}), 400

    papers = analyzer.find_relevant_papers(paper_title, max_papers)
    return jsonify(
        {
            "papers": papers,
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
        papers_df = pd.read_csv(input_path, header=None, names=["PaperTitle"]).dropna()
        if len(papers_df) > MAX_BATCH_SIZE:
            return (
                jsonify({"error": f"单次批量处理最多支持 {MAX_BATCH_SIZE} 篇论文"}),
                400,
            )

        rows = []
        for _, row in papers_df.iterrows():
            title = str(row["PaperTitle"]).strip()
            rows.append(analyzer.analyze_single_paper(title))

        buffer = io.BytesIO()
        pd.DataFrame(rows).to_csv(buffer, index=False)
        buffer.seek(0)
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
    app.run(host=HOST, port=PORT, debug=True)
