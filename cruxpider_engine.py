from __future__ import annotations

import base64
import copy
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
import math
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from difflib import SequenceMatcher
from functools import lru_cache
from typing import Any
from urllib.parse import quote_plus
import xml.etree.ElementTree as ET

import requests

from config import (
    CROSSREF_API_BASE,
    CROSSREF_MAILTO,
    GITHUB_API_BASE,
    GITHUB_TOKEN,
    OPENALEX_API_BASE,
    PAPERSWITHCODE_API_BASE,
    REQUEST_TIMEOUT_SECONDS,
    RESULT_CACHE_TTL_SECONDS,
    SEMANTIC_SCHOLAR_API_BASE,
    SEMANTIC_SCHOLAR_API_KEY,
)


logger = logging.getLogger(__name__)

AI_CATEGORIES = {"stat.ML", "cs.AI", "cs.CV", "cs.LG", "cs.CL", "cs.RO"}
METHOD_KEYWORDS = [
    "transformer",
    "bert",
    "gpt",
    "diffusion",
    "cnn",
    "rnn",
    "lstm",
    "gan",
    "vae",
    "retrieval-augmented generation",
    "rag",
    "reinforcement learning",
    "meta-learning",
    "contrastive learning",
    "fine-tuning",
    "instruction tuning",
    "self-supervised learning",
    "graph neural network",
    "llm",
    "vision transformer",
]
DATASET_KEYWORDS = [
    "imagenet",
    "cifar-10",
    "cifar10",
    "cifar-100",
    "cifar100",
    "mnist",
    "fashion-mnist",
    "wikitext",
    "common crawl",
    "squad",
    "glue",
    "superglue",
    "coco",
    "ms coco",
    "librispeech",
    "mmlu",
    "gsm8k",
    "hellaswag",
    "humanml3d",
]


@dataclass
class PaperCandidate:
    source: str
    source_id: str
    title: str
    year: int | None = None
    authors: list[str] = field(default_factory=list)
    venue: str | None = None
    pdf_url: str | None = None
    url: str | None = None
    categories: list[str] = field(default_factory=list)
    methods: list[str] = field(default_factory=list)
    datasets: list[str] = field(default_factory=list)
    identifiers: dict[str, str] = field(default_factory=dict)
    citation_count: int = 0
    reference_count: int = 0
    title_score: float = 0.0
    confidence_evidence: list[str] = field(default_factory=list)
    abstract_text: str | None = None


@dataclass
class MergedPaper:
    candidates: list[PaperCandidate] = field(default_factory=list)
    sources: set[str] = field(default_factory=set)
    identifiers: dict[str, str] = field(default_factory=dict)
    score: float = 0.0

    @property
    def best(self) -> PaperCandidate:
        return max(self.candidates, key=lambda item: item.title_score)


def _normalize_title(title: str) -> str:
    return " ".join("".join(ch.lower() if ch.isalnum() else " " for ch in title).split())


def _token_set(title: str) -> set[str]:
    return set(_normalize_title(title).split())


def _title_similarity(left: str, right: str) -> float:
    normalized_left = _normalize_title(left)
    normalized_right = _normalize_title(right)
    if not normalized_left or not normalized_right:
        return 0.0
    if normalized_left == normalized_right:
        return 1.0

    sequence = SequenceMatcher(None, normalized_left, normalized_right).ratio()
    left_tokens = set(normalized_left.split())
    right_tokens = set(normalized_right.split())
    overlap = len(left_tokens & right_tokens) / max(1, len(left_tokens | right_tokens))
    coverage = len(left_tokens & right_tokens) / max(1, min(len(left_tokens), len(right_tokens)))
    return min(1.0, 0.45 * sequence + 0.25 * overlap + 0.30 * coverage)


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        cleaned = str(value).strip()
        if not cleaned:
            continue
        marker = cleaned.lower()
        if marker in seen:
            continue
        seen.add(marker)
        deduped.append(cleaned)
    return deduped


def _first_non_empty(values: list[str | None]) -> str | None:
    for value in values:
        if value:
            return value
    return None


class CRUXpiderEngine:
    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self._build_user_agent()})
        self._result_cache: dict[tuple[str, str], tuple[float, Any]] = {}
        self._cache_lock = threading.Lock()

    def analyze_single_paper(self, paper_title: str) -> dict[str, Any]:
        cache_key = ("paper", _normalize_title(paper_title))
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        source_status = self.get_source_status()
        warnings: list[str] = []
        candidates = self._collect_candidates(paper_title)
        merged = self._merge_candidates(candidates, paper_title)

        result: dict[str, Any] = {
            "query_title": paper_title,
            "title": paper_title,
            "journal": None,
            "journal_conference": None,
            "pdf_url": None,
            "categories": [],
            "ai_related": "NO",
            "datasets": [],
            "methods": [],
            "repository_url": "N/A",
            "repository_candidates": [],
            "warnings": warnings,
            "source_status": source_status,
            "confidence": 0.0,
            "matched_sources": [],
            "identifiers": {},
            "citation_count": 0,
            "reference_count": 0,
            "landing_page_url": None,
            "resolution_notes": [],
        }

        if merged is None:
            result["warnings"].append("No strong metadata match was found; results use fallback repository search only.")
            result["repository_url"] = self._fallback_repository_search(paper_title)
            self._cache_set(cache_key, result)
            return result

        best = merged.best
        result.update(
            {
                "title": best.title or paper_title,
                "journal": _first_non_empty([candidate.venue for candidate in merged.candidates]),
                "journal_conference": _first_non_empty([candidate.venue for candidate in merged.candidates]),
                "pdf_url": _first_non_empty([candidate.pdf_url for candidate in merged.candidates]),
                "categories": _dedupe_strings(
                    [item for candidate in merged.candidates for item in candidate.categories]
                ),
                "methods": _dedupe_strings(
                    [item for candidate in merged.candidates for item in candidate.methods]
                )[:8],
                "datasets": _dedupe_strings(
                    [item for candidate in merged.candidates for item in candidate.datasets]
                )[:8],
                "confidence": round(min(0.99, merged.score), 3),
                "matched_sources": sorted(merged.sources),
                "identifiers": merged.identifiers,
                "citation_count": max(candidate.citation_count for candidate in merged.candidates),
                "reference_count": max(candidate.reference_count for candidate in merged.candidates),
                "landing_page_url": _first_non_empty([candidate.url for candidate in merged.candidates]),
                "resolution_notes": _dedupe_strings(
                    [item for candidate in merged.candidates for item in candidate.confidence_evidence]
                )[:6],
            }
        )
        result["ai_related"] = self._infer_ai_related(result["categories"])

        repositories, repo_warning = self._discover_repositories(best, merged)
        result["repository_candidates"] = repositories
        if repositories:
            result["repository_url"] = repositories[0]["url"]
        else:
            result["repository_url"] = self._fallback_repository_search(best.title or paper_title)
        if repo_warning:
            result["warnings"].append(repo_warning)
        if source_status.get("paperswithcode_redirect_target"):
            result["warnings"].append(
                "Legacy Papers with Code API now redirects to Hugging Face Papers; CRUXpider uses ranked GitHub repository discovery instead."
            )
        self._cache_set(cache_key, result)
        return result

    @lru_cache(maxsize=1)
    def get_source_status(self) -> dict[str, Any]:
        status = {
            "paperswithcode_legacy_api": False,
            "paperswithcode_redirect_target": None,
            "arxiv": True,
            "openalex": False,
            "semantic_scholar": False,
            "crossref": False,
            "github_api": False,
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

        status["openalex"] = self._check_endpoint(
            OPENALEX_API_BASE,
            params={"search": "attention is all you need", "per-page": 1},
        )
        status["semantic_scholar"] = self._check_endpoint(
            f"{SEMANTIC_SCHOLAR_API_BASE}/paper/search/match",
            params={"query": "Attention Is All You Need"},
            extra_headers=self._semantic_scholar_headers(),
        )
        status["crossref"] = self._check_endpoint(
            f"{CROSSREF_API_BASE}/works",
            params={"query.title": "Attention Is All You Need", "rows": 1},
        )
        status["github_api"] = self._check_endpoint(
            f"{GITHUB_API_BASE}/search/repositories",
            params={"q": "attention is all you need", "per_page": 1},
            extra_headers=self._github_headers(),
        )

        return status

    def find_relevant_papers(self, paper_title: str, max_papers: int = 10) -> list[dict[str, Any]]:
        cache_key = ("related", f"{_normalize_title(paper_title)}::{int(max_papers)}")
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        resolved = self._merge_candidates(self._collect_candidates(paper_title), paper_title)
        if resolved is None:
            return []

        best = resolved.best
        best.identifiers = {**resolved.identifiers, **best.identifiers}
        context = self._build_related_context(best, resolved)

        semantic_related = self._semantic_related_papers(best, max_papers * 2)
        openalex_related = self._openalex_related_papers(best, max_papers * 2)

        combined: list[dict[str, Any]] = []
        for entry in semantic_related + openalex_related:
            if not entry.get("title") or entry.get("title") == "Unknown title":
                continue
            enriched = self._rerank_related_candidate(entry, context)
            normalized = _normalize_title(enriched["title"])
            if not normalized or normalized == context["normalized_title"]:
                continue
            self._merge_related_entry(combined, enriched)

        ranked = sorted(
            combined,
            key=lambda item: (
                item.get("score", 0.0),
                item.get("signal_count", 0),
                item.get("citation_count", 0),
                item.get("year") or 0,
            ),
            reverse=True,
        )

        results = [
            {
                "title": item["title"],
                "authors": item.get("authors", [])[:3],
                "year": item.get("year"),
                "url": item.get("url") or "",
                "venue": item.get("venue"),
                "sources": item.get("sources", []),
                "score": round(item.get("score", 0.0), 3),
                "reasons": item.get("reasons", [])[:3],
                "signal_count": item.get("signal_count", 0),
                "groups": item.get("groups", []),
            }
            for item in ranked[:max_papers]
        ]
        self._cache_set(cache_key, results)
        return results

    def _build_user_agent(self) -> str:
        if CROSSREF_MAILTO:
            return f"CRUXpider/1.2 (mailto:{CROSSREF_MAILTO})"
        return "CRUXpider/1.2"

    def _cache_get(self, key: tuple[str, str]) -> Any | None:
        now = time.time()
        with self._cache_lock:
            cached = self._result_cache.get(key)
            if cached is None:
                return None
            expires_at, value = cached
            if expires_at <= now:
                self._result_cache.pop(key, None)
                return None
            return copy.deepcopy(value)

    def _cache_set(self, key: tuple[str, str], value: Any) -> None:
        with self._cache_lock:
            self._result_cache[key] = (time.time() + RESULT_CACHE_TTL_SECONDS, copy.deepcopy(value))

    def _check_endpoint(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> bool:
        try:
            response = self.session.get(
                url,
                params=params,
                headers=extra_headers,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            return response.ok
        except requests.RequestException:
            return False

    def _collect_candidates(self, paper_title: str) -> list[PaperCandidate]:
        candidates: list[PaperCandidate] = []
        fetchers = [
            self._fetch_arxiv_candidates,
            self._fetch_semantic_scholar_candidates,
            self._fetch_openalex_candidates,
            self._fetch_crossref_candidates,
        ]
        with ThreadPoolExecutor(max_workers=len(fetchers)) as executor:
            futures = [executor.submit(fetcher, paper_title) for fetcher in fetchers]
            for future in as_completed(futures):
                try:
                    candidates.extend(future.result())
                except Exception as exc:
                    logger.warning("Candidate fetcher failed: %s", exc)
        return candidates

    def _fetch_arxiv_candidates(self, paper_title: str) -> list[PaperCandidate]:
        queries = [f'ti:"{paper_title}"', paper_title]
        candidates: list[PaperCandidate] = []
        seen_ids: set[str] = set()
        for query in queries:
            try:
                response = self.session.get(
                    "https://export.arxiv.org/api/query",
                    params={"search_query": query, "start": 0, "max_results": 5},
                    timeout=REQUEST_TIMEOUT_SECONDS,
                )
                response.raise_for_status()
                root = ET.fromstring(response.text)
                namespaces = {
                    "atom": "http://www.w3.org/2005/Atom",
                    "arxiv": "http://arxiv.org/schemas/atom",
                }
                for entry in root.findall("atom:entry", namespaces):
                    entry_id = entry.findtext("atom:id", default="", namespaces=namespaces)
                    arxiv_id = entry_id.rsplit("/", 1)[-1].split("v")[0]
                    if arxiv_id in seen_ids:
                        continue
                    seen_ids.add(arxiv_id)
                    categories = [
                        category.attrib.get("term", "")
                        for category in entry.findall("atom:category", namespaces)
                        if category.attrib.get("term")
                    ]
                    pdf_url = None
                    for link in entry.findall("atom:link", namespaces):
                        if link.attrib.get("title") == "pdf":
                            pdf_url = link.attrib.get("href")
                            break
                    authors = [
                        author.findtext("atom:name", default="", namespaces=namespaces)
                        for author in entry.findall("atom:author", namespaces)
                        if author.findtext("atom:name", default="", namespaces=namespaces)
                    ]
                    abstract_text = (entry.findtext("atom:summary", default="", namespaces=namespaces) or "").strip()
                    extracted_methods, extracted_datasets = self._extract_methods_and_datasets(
                        [
                            entry.findtext("atom:title", default=paper_title, namespaces=namespaces) or paper_title,
                            abstract_text,
                            " ".join(categories),
                        ]
                    )
                    published = entry.findtext("atom:published", default="", namespaces=namespaces)
                    year = None
                    if published:
                        try:
                            year = datetime.fromisoformat(published.replace("Z", "+00:00")).year
                        except ValueError:
                            year = None
                    candidates.append(
                        PaperCandidate(
                            source="arxiv",
                            source_id=arxiv_id,
                            title=(entry.findtext("atom:title", default=paper_title, namespaces=namespaces) or paper_title).strip(),
                            year=year,
                            authors=authors,
                            venue=entry.findtext("arxiv:journal_ref", default="arXiv", namespaces=namespaces) or "arXiv",
                            pdf_url=pdf_url,
                            url=entry_id,
                            categories=categories,
                            methods=extracted_methods,
                            datasets=extracted_datasets,
                            identifiers={"arxiv": arxiv_id},
                            title_score=self._candidate_title_score(
                                paper_title,
                                (entry.findtext("atom:title", default=paper_title, namespaces=namespaces) or paper_title).strip(),
                                "arxiv",
                            ),
                            confidence_evidence=["Matched through arXiv title search."],
                            abstract_text=abstract_text,
                        )
                    )
            except Exception as exc:
                logger.warning("arXiv lookup failed: %s", exc)
        return candidates

    def _fetch_semantic_scholar_candidates(self, paper_title: str) -> list[PaperCandidate]:
        try:
            response = self.session.get(
                f"{SEMANTIC_SCHOLAR_API_BASE}/paper/search/match",
                params={
                    "query": paper_title,
                    "fields": ",".join(
                        [
                            "title",
                            "year",
                            "authors",
                            "externalIds",
                            "venue",
                            "url",
                            "citationCount",
                            "referenceCount",
                            "openAccessPdf",
                            "publicationTypes",
                            "fieldsOfStudy",
                            "abstract",
                        ]
                    ),
                },
                headers=self._semantic_scholar_headers(),
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            items = response.json().get("data", [])
        except requests.RequestException as exc:
            logger.warning("Semantic Scholar lookup failed: %s", exc)
            return []

        candidates: list[PaperCandidate] = []
        for item in items[:3]:
            external_ids = item.get("externalIds") or {}
            identifiers = {
                "semantic_scholar": item.get("paperId", ""),
            }
            if external_ids.get("DOI"):
                identifiers["doi"] = external_ids["DOI"]
            if external_ids.get("ArXiv"):
                identifiers["arxiv"] = external_ids["ArXiv"]

            fields_of_study = item.get("fieldsOfStudy") or []
            abstract_text = item.get("abstract") or ""
            methods = [field for field in fields_of_study if field not in {"Computer Science", "Mathematics"}]
            extracted_methods, extracted_datasets = self._extract_methods_and_datasets(
                [item.get("title") or paper_title, abstract_text, " ".join(fields_of_study)]
            )
            open_access_pdf = item.get("openAccessPdf") or {}
            candidates.append(
                PaperCandidate(
                    source="semantic_scholar",
                    source_id=item.get("paperId", ""),
                    title=item.get("title") or paper_title,
                    year=item.get("year"),
                    authors=[author.get("name") for author in item.get("authors", []) if author.get("name")],
                    venue=item.get("venue"),
                    pdf_url=open_access_pdf.get("url") or None,
                    url=item.get("url"),
                    categories=fields_of_study,
                    methods=_dedupe_strings(methods + extracted_methods),
                    datasets=extracted_datasets,
                    identifiers=identifiers,
                    citation_count=int(item.get("citationCount") or 0),
                    reference_count=int(item.get("referenceCount") or 0),
                    title_score=self._candidate_title_score(
                        paper_title,
                        item.get("title") or paper_title,
                        "semantic_scholar",
                    ),
                    confidence_evidence=["Matched through Semantic Scholar title search."],
                    abstract_text=abstract_text,
                )
            )
        return candidates

    def _fetch_openalex_candidates(self, paper_title: str) -> list[PaperCandidate]:
        try:
            response = self.session.get(
                OPENALEX_API_BASE,
                params=self._with_mailto({"search": paper_title, "per-page": 5}),
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            items = response.json().get("results", [])
        except requests.RequestException as exc:
            logger.warning("OpenAlex lookup failed: %s", exc)
            return []

        candidates: list[PaperCandidate] = []
        for item in items:
            authors = [
                authorship.get("author", {}).get("display_name")
                for authorship in item.get("authorships", [])
                if authorship.get("author", {}).get("display_name")
            ]
            topics = [topic.get("display_name") for topic in item.get("topics", []) if topic.get("display_name")]
            abstract_text = self._openalex_abstract_text(item.get("abstract_inverted_index"))
            extracted_methods, extracted_datasets = self._extract_methods_and_datasets(
                [item.get("display_name") or paper_title, abstract_text, " ".join(topics)]
            )
            best_oa = item.get("best_oa_location") or {}
            primary_location = item.get("primary_location") or {}
            ids = item.get("ids") or {}
            identifiers = {"openalex": item.get("id", "")}
            if ids.get("doi"):
                identifiers["doi"] = ids["doi"].replace("https://doi.org/", "")
            if ids.get("arxiv"):
                identifiers["arxiv"] = ids["arxiv"].replace("https://arxiv.org/abs/", "")
            candidates.append(
                PaperCandidate(
                    source="openalex",
                    source_id=item.get("id", ""),
                    title=item.get("display_name") or paper_title,
                    year=item.get("publication_year"),
                    authors=authors,
                    venue=self._openalex_source_name(item),
                    pdf_url=best_oa.get("pdf_url") or primary_location.get("pdf_url"),
                    url=best_oa.get("landing_page_url") or primary_location.get("landing_page_url"),
                    categories=topics,
                    methods=_dedupe_strings(topics[:5] + extracted_methods),
                    datasets=extracted_datasets,
                    identifiers=identifiers,
                    citation_count=int(item.get("cited_by_count") or 0),
                    title_score=self._candidate_title_score(
                        paper_title,
                        item.get("display_name") or paper_title,
                        "openalex",
                    ),
                    confidence_evidence=["Matched through OpenAlex search."],
                    abstract_text=abstract_text,
                )
            )
        return candidates

    def _fetch_crossref_candidates(self, paper_title: str) -> list[PaperCandidate]:
        try:
            response = self.session.get(
                f"{CROSSREF_API_BASE}/works",
                params=self._with_mailto(
                    {
                        "query.bibliographic": paper_title,
                        "rows": 5,
                        "select": "DOI,title,score,publisher,URL,issued,author,container-title,license,type,link",
                    }
                ),
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            items = response.json().get("message", {}).get("items", [])
        except requests.RequestException as exc:
            logger.warning("Crossref lookup failed: %s", exc)
            return []

        candidates: list[PaperCandidate] = []
        for item in items:
            title = (item.get("title") or [paper_title])[0]
            authors = [
                " ".join(filter(None, [author.get("given"), author.get("family")])).strip()
                for author in item.get("author", [])
            ]
            extracted_methods, extracted_datasets = self._extract_methods_and_datasets(
                [title, ((item.get("container-title") or [None])[0]) or "", item.get("type") or ""]
            )
            links = item.get("link") or []
            pdf_url = None
            for link in links:
                if "pdf" in (link.get("content-type") or "").lower():
                    pdf_url = link.get("URL")
                    break
            candidates.append(
                PaperCandidate(
                    source="crossref",
                    source_id=item.get("DOI", ""),
                    title=title,
                    year=self._crossref_year(item),
                    authors=[author for author in authors if author],
                    venue=((item.get("container-title") or [None])[0]) or item.get("publisher"),
                    pdf_url=pdf_url,
                    url=item.get("URL"),
                    categories=[item.get("type")] if item.get("type") else [],
                    methods=extracted_methods,
                    datasets=extracted_datasets,
                    identifiers={"doi": item.get("DOI", "")},
                    title_score=self._candidate_title_score(paper_title, title, "crossref"),
                    confidence_evidence=["Matched through Crossref bibliographic search."],
                )
            )
        return candidates

    def _candidate_title_score(self, query_title: str, candidate_title: str, source: str) -> float:
        reliability = {
            "semantic_scholar": 0.96,
            "arxiv": 0.94,
            "openalex": 0.92,
            "crossref": 0.82,
        }.get(source, 0.75)
        similarity = _title_similarity(query_title, candidate_title)
        return min(0.99, 0.84 * similarity + 0.16 * reliability)

    def _merge_candidates(self, candidates: list[PaperCandidate], paper_title: str) -> MergedPaper | None:
        viable = [candidate for candidate in candidates if candidate.title_score >= 0.55]
        if not viable:
            return None

        groups: list[MergedPaper] = []
        for candidate in sorted(viable, key=lambda item: item.title_score, reverse=True):
            matched_group = None
            for group in groups:
                if self._same_paper(group.best, candidate):
                    matched_group = group
                    break
            if matched_group is None:
                matched_group = MergedPaper()
                groups.append(matched_group)

            matched_group.candidates.append(candidate)
            matched_group.sources.add(candidate.source)
            matched_group.identifiers.update({k: v for k, v in candidate.identifiers.items() if v})

        for group in groups:
            best = group.best
            support_bonus = 0.08 * (len(group.sources) - 1)
            identifier_bonus = 0.05 * min(3, len(group.identifiers))
            citation_bonus = min(0.08, math.log1p(max(0, best.citation_count)) / 200)
            exact_bonus = 0.08 if _normalize_title(best.title) == _normalize_title(paper_title) else 0.0
            group.score = min(0.99, best.title_score + support_bonus + identifier_bonus + citation_bonus + exact_bonus)

        return max(groups, key=lambda item: item.score)

    def _same_paper(self, left: PaperCandidate, right: PaperCandidate) -> bool:
        shared_identifiers = set(left.identifiers.items()) & set(right.identifiers.items())
        if shared_identifiers:
            return True
        similarity = _title_similarity(left.title, right.title)
        if similarity >= 0.96:
            if left.year and right.year and abs(left.year - right.year) > 1:
                return False
            return True
        return False

    def _discover_repositories(
        self,
        best: PaperCandidate,
        merged: MergedPaper,
    ) -> tuple[list[dict[str, Any]], str | None]:
        normalized_title = _normalize_title(best.title)
        title_slug = normalized_title.replace(" ", "-")
        queries = [f'"{best.title}" in:name,description']
        if title_slug:
            queries.append(f"{title_slug} in:name")
        if GITHUB_TOKEN and merged.identifiers.get("arxiv"):
            queries.append(f'"{merged.identifiers["arxiv"]}" in:description,readme')
        if GITHUB_TOKEN and merged.identifiers.get("doi"):
            queries.append(f'"{merged.identifiers["doi"]}" in:description,readme')

        repos: dict[str, dict[str, Any]] = {}
        warning = None
        for query in queries:
            try:
                response = self.session.get(
                    f"{GITHUB_API_BASE}/search/repositories",
                    params={"q": query, "sort": "stars", "order": "desc", "per_page": 8},
                    headers=self._github_headers(),
                    timeout=REQUEST_TIMEOUT_SECONDS,
                )
                response.raise_for_status()
                items = response.json().get("items", [])
            except requests.RequestException as exc:
                logger.warning("GitHub repository search failed: %s", exc)
                warning = "GitHub API search is currently unavailable; using repository search URL fallback."
                continue

            for item in items:
                scored = self._score_repository(item, best, merged)
                if scored["score"] < 0.42:
                    continue
                key = item.get("full_name", "")
                if key not in repos or repos[key]["score"] < scored["score"]:
                    repos[key] = scored

        if not repos:
            try:
                response = self.session.get(
                    f"{GITHUB_API_BASE}/search/repositories",
                    params={"q": f'"{best.title}" in:name,description,readme', "sort": "stars", "order": "desc", "per_page": 8},
                    headers=self._github_headers(),
                    timeout=REQUEST_TIMEOUT_SECONDS,
                )
                response.raise_for_status()
                items = response.json().get("items", [])
                for item in items:
                    scored = self._score_repository(item, best, merged)
                    if scored["score"] >= 0.42:
                        repos[item.get("full_name", "")] = scored
            except requests.RequestException as exc:
                logger.warning("GitHub repository search fallback failed: %s", exc)
                warning = "GitHub API search is currently unavailable; using repository search URL fallback."

        ranked = sorted(
            repos.values(),
            key=lambda item: (item["score"], item["stars"], item["updated_at"]),
            reverse=True,
        )
        return ranked[:5], warning

    def _score_repository(
        self,
        repo: dict[str, Any],
        best: PaperCandidate,
        merged: MergedPaper,
    ) -> dict[str, Any]:
        title_norm = _normalize_title(best.title)
        name_and_description = " ".join(
            [
                repo.get("name", ""),
                repo.get("full_name", ""),
                repo.get("description") or "",
            ]
        )
        searchable_text = " ".join([name_and_description, " ".join(repo.get("topics", []) or [])])
        name_similarity = _title_similarity(best.title, name_and_description)
        similarity = 0.7 * name_similarity + 0.3 * _title_similarity(best.title, searchable_text)
        reasons: list[str] = []
        implementation_bonus = 0.0
        penalty = 0.0

        readme_text = self._fetch_repository_readme(repo.get("full_name", ""))
        if readme_text:
            if title_norm and title_norm in _normalize_title(readme_text):
                similarity += 0.20
                reasons.append("README mentions the paper title.")
            arxiv_id = merged.identifiers.get("arxiv")
            if arxiv_id and arxiv_id.lower() in readme_text.lower():
                similarity += 0.18
                reasons.append("README mentions the arXiv identifier.")
            doi = merged.identifiers.get("doi")
            if doi and doi.lower() in readme_text.lower():
                similarity += 0.18
                reasons.append("README mentions the DOI.")

        repo_name_lower = (repo.get("name") or "").lower()
        description = (repo.get("description") or "").lower()
        generic_markers = ("awesome", "list", "reading", "survey", "papers", "resources", "collection")
        if any(marker in repo_name_lower or marker in description for marker in generic_markers):
            penalty += 0.20
            reasons.append("Looks like a generic resource list, not a dedicated implementation.")

        implementation_markers = ("implementation", "pytorch", "tensorflow", "jax", "reproduce", "reproduction")
        if any(marker in description or marker in repo_name_lower for marker in implementation_markers):
            implementation_bonus += 0.10
            reasons.append("Repository description looks like a real implementation.")

        if name_similarity >= 0.7:
            implementation_bonus += 0.08
            reasons.append("Repository name is highly aligned with the paper title.")

        stars = int(repo.get("stargazers_count") or 0)
        star_signal = min(0.18, math.log1p(stars) / 60)
        updated_signal = 0.0
        updated_at = repo.get("updated_at") or ""
        if updated_at:
            try:
                updated_days = (
                    datetime.now(timezone.utc) - datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
                ).days
                updated_signal = 0.12 if updated_days <= 365 else 0.05 if updated_days <= 1095 else 0.0
            except ValueError:
                updated_signal = 0.0

        if name_similarity < 0.35 and not reasons:
            penalty += 0.15

        score = min(0.99, max(0.0, similarity + implementation_bonus + star_signal + updated_signal - penalty))
        return {
            "name": repo.get("full_name"),
            "url": repo.get("html_url"),
            "description": repo.get("description"),
            "stars": stars,
            "updated_at": updated_at,
            "score": round(score, 3),
            "reasons": _dedupe_strings(reasons),
        }

    def _fetch_repository_readme(self, full_name: str) -> str:
        if not full_name:
            return ""
        try:
            response = self.session.get(
                f"{GITHUB_API_BASE}/repos/{full_name}/readme",
                headers=self._github_headers(),
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            if not response.ok:
                return ""
            payload = response.json()
            content = payload.get("content")
            if not content:
                return ""
            return base64.b64decode(content).decode("utf-8", errors="ignore")
        except (requests.RequestException, ValueError, base64.binascii.Error):
            return ""

    def _fallback_repository_search(self, title: str) -> str:
        return f"https://github.com/search?q={quote_plus(title)}&type=repositories"

    def _semantic_related_papers(self, best: PaperCandidate, limit: int) -> list[dict[str, Any]]:
        paper_id = best.identifiers.get("semantic_scholar") or best.source_id
        if not paper_id:
            return []
        try:
            response = self.session.get(
                f"{SEMANTIC_SCHOLAR_API_BASE.replace('/graph/v1', '')}/recommendations/v1/papers/forpaper/{paper_id}",
                params={
                    "from": "all-cs",
                    "limit": min(100, limit),
                    "fields": "title,url,authors,year,venue,citationCount,fieldsOfStudy,abstract",
                },
                headers=self._semantic_scholar_headers(),
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            items = response.json().get("recommendedPapers", [])
        except requests.RequestException as exc:
            logger.warning("Semantic Scholar recommendations failed: %s", exc)
            return []

        related: list[dict[str, Any]] = []
        for item in items:
            related.append(
                {
                    "title": item.get("title") or "Unknown title",
                    "authors": [author.get("name") for author in item.get("authors", []) if author.get("name")],
                    "year": item.get("year"),
                    "url": item.get("url") or "",
                    "venue": item.get("venue"),
                    "citation_count": int(item.get("citationCount") or 0),
                    "categories": item.get("fieldsOfStudy") or [],
                    "abstract_text": item.get("abstract") or "",
                    "sources": ["semantic_scholar"],
                    "score": self._related_score(item.get("citationCount") or 0, 0.82),
                    "reasons": ["Recommended by Semantic Scholar."],
                }
            )
        return related

    def _openalex_related_papers(self, best: PaperCandidate, limit: int) -> list[dict[str, Any]]:
        openalex_id = best.identifiers.get("openalex")
        if not openalex_id:
            fallback_candidates = self._fetch_openalex_candidates(best.title)
            if fallback_candidates:
                openalex_id = fallback_candidates[0].identifiers.get("openalex")
        if not openalex_id:
            return []
        work_id = openalex_id.replace("https://openalex.org/", "")
        try:
            detail = self.session.get(
                f"{OPENALEX_API_BASE}/{work_id}",
                params=self._with_mailto({}),
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            detail.raise_for_status()
            related_urls = detail.json().get("related_works", [])[:limit]
        except requests.RequestException as exc:
            logger.warning("OpenAlex related works lookup failed: %s", exc)
            return []

        related: list[dict[str, Any]] = []
        for related_url in related_urls:
            work_id = related_url.replace("https://openalex.org/", "")
            try:
                response = self.session.get(
                    f"{OPENALEX_API_BASE}/{work_id}",
                    params=self._with_mailto({}),
                    timeout=REQUEST_TIMEOUT_SECONDS,
                )
                response.raise_for_status()
                item = response.json()
            except requests.RequestException:
                continue
            related.append(
                {
                    "title": item.get("display_name") or "Unknown title",
                    "authors": [
                        authorship.get("author", {}).get("display_name")
                        for authorship in item.get("authorships", [])[:5]
                        if authorship.get("author", {}).get("display_name")
                    ],
                    "year": item.get("publication_year"),
                    "url": (item.get("primary_location") or {}).get("landing_page_url") or "",
                    "venue": self._openalex_source_name(item),
                    "citation_count": int(item.get("cited_by_count") or 0),
                    "categories": [topic.get("display_name") for topic in item.get("topics", []) if topic.get("display_name")],
                    "abstract_text": self._openalex_abstract_text(item.get("abstract_inverted_index")),
                    "sources": ["openalex"],
                    "score": self._related_score(item.get("cited_by_count") or 0, 0.73),
                    "reasons": ["Connected through OpenAlex related works."],
                }
            )
        return related

    def _related_score(self, citation_count: int, base: float) -> float:
        return min(0.99, base + min(0.15, math.log1p(max(0, citation_count)) / 90))

    def _build_related_context(self, best: PaperCandidate, merged: MergedPaper) -> dict[str, Any]:
        authors = _dedupe_strings([author for candidate in merged.candidates for author in candidate.authors])[:12]
        categories = _dedupe_strings([item for candidate in merged.candidates for item in candidate.categories])[:12]
        methods = _dedupe_strings([item for candidate in merged.candidates for item in candidate.methods])[:12]
        return {
            "title": best.title,
            "normalized_title": _normalize_title(best.title),
            "title_tokens": _token_set(best.title),
            "venue": (best.venue or "").strip().lower(),
            "year": best.year,
            "authors": {author.lower() for author in authors},
            "categories": {category.lower() for category in categories},
            "methods": {method.lower() for method in methods},
        }

    def _rerank_related_candidate(self, entry: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        candidate = copy.deepcopy(entry)
        reasons = list(candidate.get("reasons", []))
        signal_count = 0
        score = float(candidate.get("score", 0.0))
        groups: set[str] = set()

        title = candidate.get("title") or ""
        title_similarity = _title_similarity(context["title"], title)
        if title_similarity >= 0.78:
            score += 0.04
            reasons.append("Title is strongly aligned with the seed paper.")
            signal_count += 1

        candidate_tokens = _token_set(title)
        token_overlap = len(context["title_tokens"] & candidate_tokens)
        if token_overlap >= 2:
            reasons.append(f"Shares {token_overlap} key title tokens with the seed paper.")
            signal_count += 1

        venue = (candidate.get("venue") or "").strip().lower()
        if venue and context["venue"] and venue == context["venue"]:
            score += 0.05
            reasons.append("Published in the same venue as the seed paper.")
            signal_count += 1
            groups.add("same-wave")

        candidate_year = candidate.get("year")
        if context["year"] and candidate_year:
            distance = abs(int(candidate_year) - int(context["year"]))
            if distance <= 2:
                score += 0.03
                reasons.append("Published in a nearby year, suggesting the same research wave.")
                signal_count += 1
                groups.add("same-wave")

        author_overlap = [
            author for author in candidate.get("authors", [])
            if author and author.lower() in context["authors"]
        ]
        if author_overlap:
            score += 0.08
            reasons.append(f"Shares author overlap with the seed paper: {', '.join(author_overlap[:2])}.")
            signal_count += 1
            groups.add("same-author")

        category_overlap = {
            category.lower()
            for category in (candidate.get("categories") or [])
            if category and category.lower() in context["categories"]
        }
        if category_overlap:
            score += 0.05
            reasons.append(f"Overlaps on topics: {', '.join(sorted(category_overlap)[:2])}.")
            signal_count += 1
            groups.add("same-method")

        candidate_methods, candidate_datasets = self._extract_methods_and_datasets(
            [title, candidate.get("abstract_text") or "", " ".join(candidate.get("categories") or [])]
        )
        candidate["methods"] = candidate_methods
        candidate["datasets"] = candidate_datasets

        method_overlap = {
            method.lower()
            for method in candidate_methods
            if method and method.lower() in context["methods"]
        }
        if method_overlap:
            score += 0.06
            reasons.append(f"Touches the same method family: {', '.join(sorted(method_overlap)[:2])}.")
            signal_count += 1
            groups.add("same-method")

        citation_count = int(candidate.get("citation_count") or 0)
        if citation_count >= 500:
            score += 0.03
            reasons.append("Highly cited within the neighborhood of this topic.")
            signal_count += 1
            groups.add("strong-follow-up")

        candidate["score"] = min(0.99, round(score, 3))
        candidate["reasons"] = _dedupe_strings(reasons)
        candidate["signal_count"] = signal_count
        candidate["groups"] = sorted(groups)
        return candidate

    def _merge_related_entry(self, combined: list[dict[str, Any]], entry: dict[str, Any]) -> None:
        for current in combined:
            current_title = current.get("title") or ""
            current_year = current.get("year")
            entry_year = entry.get("year")
            similar = _title_similarity(current_title, entry.get("title") or "")
            close_year = (
                current_year is None
                or entry_year is None
                or abs(int(current_year) - int(entry_year)) <= 1
            )
            if similar >= 0.94 and close_year:
                current["score"] = max(current.get("score", 0.0), entry.get("score", 0.0))
                current["signal_count"] = max(current.get("signal_count", 0), entry.get("signal_count", 0))
                current["sources"] = sorted(set(current.get("sources", [])) | set(entry.get("sources", [])))
                current["reasons"] = _dedupe_strings(current.get("reasons", []) + entry.get("reasons", []))
                current["citation_count"] = max(current.get("citation_count", 0), entry.get("citation_count", 0))
                current["categories"] = _dedupe_strings((current.get("categories") or []) + (entry.get("categories") or []))
                current["methods"] = _dedupe_strings((current.get("methods") or []) + (entry.get("methods") or []))
                current["datasets"] = _dedupe_strings((current.get("datasets") or []) + (entry.get("datasets") or []))
                current["groups"] = sorted(set(current.get("groups", [])) | set(entry.get("groups", [])))
                if not current.get("url") and entry.get("url"):
                    current["url"] = entry["url"]
                return
        combined.append(entry)

    def group_relevant_papers(self, papers: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        grouped = {
            "same_author": [],
            "same_method": [],
            "same_wave": [],
            "strong_follow_up": [],
        }
        mapping = {
            "same-author": "same_author",
            "same-method": "same_method",
            "same-wave": "same_wave",
            "strong-follow-up": "strong_follow_up",
        }
        for paper in papers:
            for group in paper.get("groups", []):
                target = mapping.get(group)
                if target:
                    grouped[target].append(paper)
        return grouped

    def _infer_ai_related(self, categories: list[str]) -> str:
        lowered = {category.lower() for category in categories}
        if any(tag.lower() in lowered for tag in AI_CATEGORIES):
            return "YES"
        keywords = ("learning", "neural", "vision", "language", "transformer", "llm", "ai")
        if any(any(keyword in category.lower() for keyword in keywords) for category in categories):
            return "YES"
        return "NO"

    def _extract_methods_and_datasets(self, text_parts: list[str]) -> tuple[list[str], list[str]]:
        text = " ".join(part for part in text_parts if part).strip()
        if not text:
            return [], []
        lowered = text.lower()

        methods = [keyword for keyword in METHOD_KEYWORDS if keyword in lowered]
        datasets = [keyword for keyword in DATASET_KEYWORDS if keyword in lowered]

        benchmark_matches = re.findall(r"\b([A-Z]{2,}[A-Z0-9\-\_]{1,})\b", text)
        for match in benchmark_matches:
            if any(char.isdigit() for char in match) or match in {"GLUE", "MMLU", "GSM8K"}:
                datasets.append(match)

        method_matches = re.findall(r"\b([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,2}\s+(?:Transformer|Network|Model))\b", text)
        methods.extend(method_matches)

        return _dedupe_strings(methods)[:10], _dedupe_strings(datasets)[:10]

    def _openalex_abstract_text(self, inverted_index: dict[str, list[int]] | None) -> str:
        if not inverted_index:
            return ""
        terms: dict[int, str] = {}
        for word, positions in inverted_index.items():
            for position in positions:
                terms[position] = word
        if not terms:
            return ""
        return " ".join(terms[index] for index in sorted(terms))

    def _crossref_year(self, item: dict[str, Any]) -> int | None:
        for field_name in ("issued", "published-print", "published-online", "created"):
            date_parts = (item.get(field_name) or {}).get("date-parts") or []
            if date_parts and date_parts[0]:
                try:
                    return int(date_parts[0][0])
                except (TypeError, ValueError):
                    return None
        return None

    def _openalex_source_name(self, item: dict[str, Any]) -> str | None:
        primary_location = item.get("primary_location") or {}
        source = primary_location.get("source") or {}
        source_name = source.get("display_name")
        if source_name and "arxiv" not in source_name.lower():
            return source_name
        for location in item.get("locations", []):
            location_source = (location or {}).get("source") or {}
            candidate = location_source.get("display_name")
            if candidate and "arxiv" not in candidate.lower():
                return candidate
        return source_name

    def _with_mailto(self, params: dict[str, Any]) -> dict[str, Any]:
        if CROSSREF_MAILTO and "mailto" not in params:
            return {**params, "mailto": CROSSREF_MAILTO}
        return params

    def _github_headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if GITHUB_TOKEN:
            headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
        return headers

    def _semantic_scholar_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if SEMANTIC_SCHOLAR_API_KEY:
            headers["x-api-key"] = SEMANTIC_SCHOLAR_API_KEY
        return headers
