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
    DATACITE_API_BASE,
    GITHUB_API_BASE,
    GITHUB_TOKEN,
    OPENALEX_API_BASE,
    OPENAIRE_API_BASE,
    PAPERSWITHCODE_API_BASE,
    REQUEST_TIMEOUT_SECONDS,
    RESULT_CACHE_TTL_SECONDS,
    SEMANTIC_SCHOLAR_API_BASE,
    SEMANTIC_SCHOLAR_API_KEY,
)


logger = logging.getLogger(__name__)

AI_CATEGORIES = {"stat.ML", "cs.AI", "cs.CV", "cs.LG", "cs.CL", "cs.RO"}
DOMAIN_KEYWORDS = {
    "ai": ["machine learning", "deep learning", "neural", "transformer", "llm", "artificial intelligence"],
    "materials": ["materials", "material", "crystal", "alloy", "perovskite", "bandgap", "catalyst"],
    "chemistry": ["chemistry", "chemical", "molecule", "molecular", "reaction", "retrosynthesis", "polymer"],
    "biology": ["biology", "biological", "protein", "genome", "genomic", "cell", "rna", "dna"],
    "medicine": ["medical", "medicine", "clinical", "disease", "patient", "radiograph", "diagnosis", "drug discovery"],
    "physics": ["physics", "physical", "quantum", "particle", "thermodynamic", "simulation"],
    "climate": ["climate", "weather", "earth", "atmospheric", "ocean", "carbon", "environment"],
    "robotics": ["robot", "robotics", "grasping", "navigation", "manipulation", "control"],
}
DOMAIN_CATEGORY_HINTS = {
    "ai": ["machine learning", "artificial intelligence", "computer vision", "natural language processing"],
    "materials": ["materials", "materials informatics", "condensed matter", "crystallography"],
    "chemistry": ["chemistry", "chemical engineering", "molecular science"],
    "biology": ["biology", "bioinformatics", "genomics", "proteomics"],
    "medicine": ["medicine", "medical imaging", "clinical medicine", "radiology", "biomedicine"],
    "physics": ["physics", "quantum", "physical chemistry"],
    "climate": ["climate", "earth science", "environmental science", "atmospheric science"],
    "robotics": ["robotics", "autonomous systems", "control systems"],
}
TASK_KEYWORDS = {
    "property prediction": ["property prediction", "bandgap", "yield prediction", "forecasting", "regression"],
    "inverse design": ["inverse design", "design generation", "molecule design", "materials design"],
    "retrosynthesis": ["retrosynthesis", "reaction planning"],
    "segmentation": ["segmentation", "mask", "pixel-wise"],
    "simulation": ["simulation", "molecular dynamics", "finite element", "dft"],
    "benchmarking": ["benchmark", "challenge", "leaderboard", "evaluation suite"],
    "structure prediction": ["structure prediction", "folding", "conformation"],
    "generation": ["generation", "generative", "synthesis"],
    "molecular property prediction": ["molecular property prediction", "admet", "solubility", "toxicity", "affinity prediction"],
    "reaction prediction": ["reaction prediction", "reaction outcome", "reaction yield"],
    "drug discovery": ["drug discovery", "virtual screening", "hit discovery", "lead optimization"],
    "genomics": ["gene expression", "genome", "genomic", "variant effect", "single-cell", "transcriptomics"],
    "protein modeling": ["protein function", "protein design", "protein engineering", "antibody design"],
    "diagnosis": ["diagnosis", "diagnostic", "detection", "screening", "triage"],
    "prognosis": ["prognosis", "risk prediction", "survival analysis", "outcome prediction"],
    "medical report generation": ["report generation", "clinical report", "radiology report"],
}
TASK_DOMAIN_HINTS = {
    "property prediction": ["materials", "chemistry"],
    "inverse design": ["materials", "chemistry"],
    "retrosynthesis": ["chemistry"],
    "reaction prediction": ["chemistry"],
    "drug discovery": ["chemistry", "medicine", "biology"],
    "molecular property prediction": ["chemistry", "medicine"],
    "genomics": ["biology", "medicine"],
    "protein modeling": ["biology", "medicine"],
    "diagnosis": ["medicine"],
    "prognosis": ["medicine"],
    "medical report generation": ["medicine"],
    "simulation": ["physics", "materials", "chemistry"],
}
METHOD_FAMILY_KEYWORDS = {
    "transformer": ["transformer", "bert", "gpt", "vision transformer"],
    "diffusion": ["diffusion"],
    "graph neural network": ["graph neural network", "gnn", "graph learning"],
    "foundation model": ["foundation model", "large language model", "llm", "pretrained model"],
    "molecular dynamics": ["molecular dynamics"],
    "dft-assisted ml": ["dft", "density functional theory"],
    "retrieval-augmented generation": ["retrieval-augmented generation", "rag"],
}
ARTIFACT_PROFILE_KEYWORDS = {
    "benchmark": ["benchmark", "challenge", "leaderboard"],
    "protocol": ["protocol", "workflow", "procedure", "assay"],
    "wet-lab resource": ["wet lab", "assay", "screening", "biobank"],
}
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
STRONG_DATASET_RELATIONS = {
    "issupplementto",
    "issupplementedby",
    "issourceof",
    "isderivedfrom",
    "ispartof",
    "haspart",
    "describes",
    "isdescribedby",
    "documents",
    "isdocumentedby",
    "ismetadatafor",
}
WEAK_DATASET_RELATIONS = {
    "references",
    "isreferencedby",
    "iscitedby",
    "cites",
}


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


def _normalize_doi(value: str | None) -> str:
    if not value:
        return ""
    normalized = value.strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):]
    return normalized.strip()


def _extract_year(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"\b(19|20)\d{2}\b", value)
    if not match:
        return None
    try:
        return int(match.group(0))
    except ValueError:
        return None


def _text_contains_keyword(text: str, keyword: str) -> bool:
    lowered_text = text.lower()
    lowered_keyword = keyword.lower().strip()
    if not lowered_keyword:
        return False
    if " " in lowered_keyword or "-" in lowered_keyword:
        return lowered_keyword in lowered_text
    return re.search(rf"(?<![a-z0-9]){re.escape(lowered_keyword)}(?![a-z0-9])", lowered_text) is not None


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
            "year": None,
            "journal": None,
            "journal_conference": None,
            "pdf_url": None,
            "categories": [],
            "ai_related": "NO",
            "research_profile": self._build_research_profile(
                title=paper_title,
                categories=[],
                methods=[],
                datasets=[],
                repository_candidates=[],
                abstract_text="",
            ),
            "datasets": [],
            "dataset_candidates": [],
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
                "year": best.year,
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

        dataset_candidates, dataset_warning = self._discover_datasets(best, merged)
        result["dataset_candidates"] = dataset_candidates
        if dataset_candidates:
            result["datasets"] = dataset_candidates[:8]
        if dataset_warning:
            result["warnings"].append(dataset_warning)

        repositories, repo_warning = self._discover_repositories(best, merged)
        result["repository_candidates"] = repositories
        if repositories:
            result["repository_url"] = repositories[0]["url"]
        else:
            result["repository_url"] = self._fallback_repository_search(best.title or paper_title)
        result["research_profile"] = self._build_research_profile(
            title=result["title"],
            categories=result["categories"],
            methods=result["methods"],
            datasets=result["datasets"],
            repository_candidates=result["repository_candidates"],
            abstract_text=_first_non_empty([candidate.abstract_text for candidate in merged.candidates]) or "",
        )
        if repo_warning:
            result["warnings"].append(repo_warning)
        if source_status.get("paperswithcode_redirect_target"):
            result["warnings"].append(
                "Legacy Papers with Code API now redirects to Hugging Face Papers; CRUXpider uses ranked GitHub repository discovery instead."
            )
        self._cache_set(cache_key, result)
        return result

    def explore_research_assets(
        self,
        query: str,
        mode: str = "topic",
        max_papers: int = 5,
    ) -> dict[str, Any]:
        mode = "area" if mode == "area" else "topic"
        max_papers = max(3, min(max_papers, 8))
        query_profile = self._build_research_profile(
            title=query,
            categories=[],
            methods=[],
            datasets=[],
            repository_candidates=[],
            abstract_text="",
        )
        seeds = self._search_openalex_free_text(query, max_papers=max_papers)
        representative_papers: list[dict[str, Any]] = []

        with ThreadPoolExecutor(max_workers=min(4, max(1, len(seeds)))) as executor:
            future_map = {
                executor.submit(self.analyze_single_paper, seed["title"]): seed
                for seed in seeds[:max_papers]
                if seed.get("title")
            }
            for future in as_completed(future_map):
                seed = future_map[future]
                try:
                    enriched = future.result()
                    enriched["seed_citation_count"] = seed.get("citation_count", 0)
                    enriched["query_alignment"] = self._research_profile_alignment_score(
                        enriched.get("research_profile", {}),
                        query_profile,
                        query,
                        enriched.get("title", ""),
                    )
                    representative_papers.append(enriched)
                except Exception as exc:
                    logger.warning("Research asset exploration failed for %s: %s", seed.get("title"), exc)

        representative_papers = sorted(
            representative_papers,
            key=lambda item: (item.get("query_alignment", 0.0), item.get("confidence", 0.0), item.get("citation_count", 0)),
            reverse=True,
        )[:max_papers]

        common_methods = self._aggregate_named_assets(
            [paper.get("research_profile", {}).get("method_families", []) for paper in representative_papers],
            limit=8,
        )
        common_datasets = self._aggregate_dataset_assets(representative_papers, limit=8)
        code_repositories = self._aggregate_repository_assets(representative_papers, limit=6)
        benchmark_assets = self._aggregate_benchmark_assets(representative_papers, limit=6)
        aggregated_profile = self._aggregate_research_profiles(
            [paper.get("research_profile", {}) for paper in representative_papers],
            query_profile=query_profile,
        )
        if mode == "topic":
            return {
                "query": query,
                "mode": mode,
                "research_profile": aggregated_profile,
                "common_methods": common_methods,
                "common_datasets": common_datasets,
                "benchmark_assets": benchmark_assets,
                "code_repositories": code_repositories,
                "asset_brief": self._build_topic_asset_brief(
                    query=query,
                    aggregated_profile=aggregated_profile,
                    common_datasets=common_datasets,
                    common_methods=common_methods,
                    benchmark_assets=benchmark_assets,
                    code_repositories=code_repositories,
                ),
                "total_assets": len(common_methods) + len(common_datasets) + len(benchmark_assets) + len(code_repositories),
            }

        return {
            "query": query,
            "mode": mode,
            "research_profile": aggregated_profile,
            "representative_papers": representative_papers,
            "common_methods": common_methods,
            "common_datasets": common_datasets,
            "code_repositories": code_repositories,
            "reading_path": self._build_reading_path(representative_papers),
            "subdirection_layers": self._build_subdirection_layers(representative_papers),
            "research_brief": self._build_research_brief(
                query=query,
                aggregated_profile=aggregated_profile,
                representative_papers=representative_papers,
                common_datasets=common_datasets,
                common_methods=common_methods,
                code_repositories=code_repositories,
            ),
            "total": len(representative_papers),
        }

    @lru_cache(maxsize=1)
    def get_source_status(self) -> dict[str, Any]:
        status = {
            "paperswithcode_legacy_api": False,
            "paperswithcode_redirect_target": None,
            "arxiv": True,
            "openalex": False,
            "semantic_scholar": False,
            "crossref": False,
            "datacite": False,
            "openaire": False,
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
        status["datacite"] = self._check_endpoint(
            f"{DATACITE_API_BASE}/dois",
            params={"query": "imagenet", "resource-type-id": "dataset", "page[size]": 1},
        )
        status["openaire"] = self._check_endpoint(
            f"{OPENAIRE_API_BASE}/v1/researchProducts/links",
            params={
                "sourcePid": "10.1109/cvpr.2009.5206848",
                "sourceType": "publication",
                "targetType": "dataset",
                "page": 0,
                "pageSize": 1,
            },
        )
        status["github_api"] = self._check_endpoint(
            f"{GITHUB_API_BASE}/search/repositories",
            params={"q": "attention is all you need", "per_page": 1},
            extra_headers=self._github_headers(),
        )

        return status

    def _search_openalex_free_text(self, query: str, max_papers: int = 5) -> list[dict[str, Any]]:
        try:
            response = self.session.get(
                OPENALEX_API_BASE,
                params=self._with_mailto({"search": query, "per-page": max_papers}),
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("OpenAlex free-text exploration failed: %s", exc)
            return []

        results = []
        query_tokens = _token_set(query)
        for item in response.json().get("results", []):
            title = item.get("display_name")
            if not title:
                continue
            similarity = _title_similarity(query, title)
            token_overlap = len(query_tokens & _token_set(title))
            if similarity < 0.18 and token_overlap < max(1, min(2, len(query_tokens))):
                continue
            results.append(
                {
                    "title": title,
                    "year": item.get("publication_year"),
                    "citation_count": int(item.get("cited_by_count") or 0),
                    "venue": self._openalex_source_name(item),
                    "query_similarity": round(similarity, 3),
                }
            )
        return sorted(
            results,
            key=lambda item: (item.get("query_similarity", 0.0), item.get("citation_count", 0)),
            reverse=True,
        )[:max_papers]

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

    def _discover_datasets(
        self,
        best: PaperCandidate,
        merged: MergedPaper,
    ) -> tuple[list[dict[str, Any]], str | None]:
        context = self._build_dataset_context(best, merged)
        candidates: list[dict[str, Any]] = []
        warning = None

        public_fetchers = [
            self._fetch_openaire_dataset_candidates,
            self._fetch_datacite_dataset_candidates,
            self._fetch_crossref_dataset_candidates,
            self._fetch_openalex_dataset_candidates,
        ]
        with ThreadPoolExecutor(max_workers=len(public_fetchers)) as executor:
            futures = [executor.submit(fetcher, context) for fetcher in public_fetchers]
            for future in as_completed(futures):
                try:
                    for candidate in future.result():
                        self._merge_dataset_entry(candidates, candidate)
                except Exception as exc:
                    logger.warning("Dataset discovery source failed: %s", exc)
                    warning = "Some public dataset sources could not be queried; results may be incomplete."

        for heuristic in context["heuristic_datasets"]:
            self._merge_dataset_entry(
                candidates,
                {
                    "name": heuristic,
                    "url": "",
                    "source": "heuristic",
                    "score": 0.25,
                    "evidence": ["Extracted from public title/abstract/topic text."],
                },
            )

        ranked = sorted(
            [
                candidate
                for candidate in candidates
                if self._should_keep_dataset_candidate(candidate)
            ],
            key=lambda item: (item["score"], item["name"]),
            reverse=True,
        )
        for candidate in ranked:
            candidate["mapping_status"] = self._dataset_mapping_status(candidate)
        return ranked[:8], warning

    def _build_dataset_context(self, best: PaperCandidate, merged: MergedPaper) -> dict[str, Any]:
        authors = _dedupe_strings([author for candidate in merged.candidates for author in candidate.authors])[:10]
        heuristics = self._filtered_heuristic_datasets(best, merged)
        dataset_queries = heuristics[:4]
        if not dataset_queries:
            dataset_queries = [best.title]
        return {
            "title": best.title,
            "normalized_title": _normalize_title(best.title),
            "title_tokens": [token for token in _normalize_title(best.title).split() if len(token) > 3][:8],
            "authors": authors,
            "author_set": {author.lower() for author in authors},
            "year": best.year,
            "identifiers": merged.identifiers,
            "heuristic_datasets": heuristics,
            "dataset_queries": dataset_queries,
            "methods": _dedupe_strings([item for candidate in merged.candidates for item in candidate.methods])[:10],
            "categories": _dedupe_strings([item for candidate in merged.candidates for item in candidate.categories])[:10],
        }

    def _filtered_heuristic_datasets(self, best: PaperCandidate, merged: MergedPaper) -> list[str]:
        title_normalized = _normalize_title(best.title)
        title_tokens = set(title_normalized.split())
        raw_heuristics = _dedupe_strings([item for candidate in merged.candidates for item in candidate.datasets])[:12]
        filtered: list[str] = []
        for value in raw_heuristics:
            normalized_value = _normalize_title(value)
            if not normalized_value:
                continue
            value_tokens = set(normalized_value.split())
            if normalized_value in title_normalized or (value_tokens and value_tokens <= title_tokens):
                filtered.append(value)
        return filtered[:8]

    def _fetch_datacite_dataset_candidates(self, context: dict[str, Any]) -> list[dict[str, Any]]:
        queries = []
        doi = context["identifiers"].get("doi")
        arxiv_id = context["identifiers"].get("arxiv")
        if doi:
            queries.append(doi)
        if arxiv_id:
            queries.append(f"10.48550/arXiv.{arxiv_id}")
            queries.append(arxiv_id)
        queries.extend(context["dataset_queries"])

        candidates: list[dict[str, Any]] = []
        for query in _dedupe_strings(queries):
            response = self.session.get(
                f"{DATACITE_API_BASE}/dois",
                params={"query": query, "resource-type-id": "dataset", "page[size]": 6},
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            for item in response.json().get("data", []):
                attrs = item.get("attributes", {})
                candidate = {
                    "name": ((attrs.get("titles") or [{"title": "Untitled dataset"}])[0]).get("title", "Untitled dataset"),
                    "url": attrs.get("url") or f"https://doi.org/{attrs.get('doi')}" if attrs.get("doi") else "",
                    "source": "datacite",
                    "doi": _normalize_doi(attrs.get("doi", "")),
                    "year": attrs.get("publicationYear"),
                    "authors": [creator.get("name") for creator in attrs.get("creators", []) if creator.get("name")],
                    "score": 0.26,
                    "evidence": [],
                }
                related_identifiers = attrs.get("relatedIdentifiers") or []
                self._score_dataset_candidate(candidate, context, related_identifiers)
                candidates.append(candidate)
        return candidates

    def _fetch_openaire_dataset_candidates(self, context: dict[str, Any]) -> list[dict[str, Any]]:
        source_pids: list[str] = []
        doi = _normalize_doi(context["identifiers"].get("doi"))
        arxiv_id = context["identifiers"].get("arxiv")
        if doi:
            source_pids.append(doi)
        if arxiv_id:
            source_pids.extend([arxiv_id, f"10.48550/arxiv.{arxiv_id.lower()}"])

        candidates: list[dict[str, Any]] = []
        for source_pid in _dedupe_strings(source_pids):
            response = self.session.get(
                f"{OPENAIRE_API_BASE}/v1/researchProducts/links",
                params={
                    "sourcePid": source_pid,
                    "sourceType": "publication",
                    "targetType": "dataset",
                    "page": 0,
                    "pageSize": 8,
                },
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            for relation in response.json().get("results", []):
                candidate = self._openaire_relation_to_dataset_candidate(relation, source_pid)
                if not candidate:
                    continue
                self._score_dataset_candidate(
                    candidate,
                    context,
                    [
                        {
                            "relationType": candidate.get("relation_type", ""),
                            "relatedIdentifier": source_pid,
                            "relatedIdentifierType": "PID",
                        }
                    ],
                )
                candidates.append(candidate)
        return candidates

    def _fetch_crossref_dataset_candidates(self, context: dict[str, Any]) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for query_text in _dedupe_strings(context["dataset_queries"]):
            response = self.session.get(
                f"{CROSSREF_API_BASE}/types/dataset/works",
                params=self._with_mailto({"query.bibliographic": query_text, "rows": 6}),
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            for item in response.json().get("message", {}).get("items", []):
                title = ((item.get("title") or [None])[0]) or "Untitled dataset"
                candidate = {
                    "name": title,
                    "url": item.get("URL", ""),
                    "source": "crossref",
                    "doi": _normalize_doi(item.get("DOI", "")),
                    "year": self._crossref_year(item),
                    "authors": [
                        " ".join(filter(None, [author.get("given"), author.get("family")])).strip()
                        for author in item.get("author", [])
                        if author.get("given") or author.get("family")
                    ],
                    "score": 0.22,
                    "evidence": [],
                }
                related_identifiers = []
                for relation_name, relation_items in (item.get("relation") or {}).items():
                    for relation_item in relation_items:
                        related_identifiers.append(
                            {
                                "relationType": relation_name,
                                "relatedIdentifier": relation_item.get("id", ""),
                                "relatedIdentifierType": relation_item.get("id-type", ""),
                            }
                        )
                self._score_dataset_candidate(candidate, context, related_identifiers)
                candidates.append(candidate)
        return candidates

    def _fetch_openalex_dataset_candidates(self, context: dict[str, Any]) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for query_text in _dedupe_strings(context["dataset_queries"]):
            response = self.session.get(
                OPENALEX_API_BASE,
                params=self._with_mailto({"search": query_text, "filter": "type:dataset", "per-page": 6}),
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            for item in response.json().get("results", []):
                candidate = {
                    "name": item.get("display_name") or "Untitled dataset",
                    "url": (item.get("primary_location") or {}).get("landing_page_url")
                    or item.get("doi")
                    or item.get("id", ""),
                    "source": "openalex",
                    "doi": _normalize_doi((item.get("ids") or {}).get("doi", "")),
                    "year": item.get("publication_year"),
                    "authors": [
                        authorship.get("author", {}).get("display_name")
                        for authorship in item.get("authorships", [])
                        if authorship.get("author", {}).get("display_name")
                    ],
                    "score": 0.18,
                    "evidence": [],
                }
                related_identifiers = []
                ids = item.get("ids") or {}
                if ids.get("doi"):
                    related_identifiers.append(
                        {
                            "relationType": "openalex-match",
                            "relatedIdentifier": ids["doi"],
                            "relatedIdentifierType": "DOI",
                        }
                    )
                self._score_dataset_candidate(candidate, context, related_identifiers)
                candidates.append(candidate)
        return candidates

    def _score_dataset_candidate(
        self,
        candidate: dict[str, Any],
        context: dict[str, Any],
        related_identifiers: list[dict[str, Any]],
    ) -> None:
        evidence = list(candidate.get("evidence", []))
        score = float(candidate.get("score", 0.0))
        identifiers = {_normalize_doi(value) for value in context["identifiers"].values() if value}
        if context["identifiers"].get("arxiv"):
            identifiers.add(f"10.48550/arxiv.{context['identifiers']['arxiv'].lower()}")
        strong_relation_hit = False
        weak_relation_hit = False

        for relation in related_identifiers:
            related_identifier = _normalize_doi(relation.get("relatedIdentifier") or "")
            relation_type = (relation.get("relationType") or "").lower()
            if related_identifier and any(identifier and identifier in related_identifier for identifier in identifiers):
                if relation_type in STRONG_DATASET_RELATIONS:
                    score += 0.34
                    evidence.append(f"Public metadata links this dataset to the paper via {relation_type or 'relatedIdentifier'}.")
                    strong_relation_hit = True
                elif relation_type in WEAK_DATASET_RELATIONS:
                    score += 0.05
                    evidence.append("Dataset metadata references the paper, but this is only weak evidence.")
                    weak_relation_hit = True

        title_similarity = _title_similarity(context["title"], candidate.get("name", ""))
        if title_similarity >= 0.55:
            score += 0.12
            evidence.append("Dataset title is closely aligned with the paper title.")

        author_overlap = [
            author for author in candidate.get("authors", [])
            if author and author.lower() in context["author_set"]
        ]
        if author_overlap:
            score += 0.12
            evidence.append(f"Dataset shares creators with the paper: {', '.join(author_overlap[:2])}.")

        if candidate.get("year") and context.get("year"):
            try:
                if abs(int(candidate["year"]) - int(context["year"])) <= 2:
                    score += 0.05
                    evidence.append("Dataset was published near the paper year.")
            except (TypeError, ValueError):
                pass

        lowered_name = (candidate.get("name") or "").lower()
        if any(method.lower() in lowered_name for method in context["methods"]):
            score += 0.05
            evidence.append("Dataset name overlaps with the paper's method vocabulary.")

        if any(category.lower() in lowered_name for category in context["categories"][:4]):
            score += 0.03
            evidence.append("Dataset name overlaps with the paper's topic vocabulary.")

        evidence = _dedupe_strings(evidence)
        if strong_relation_hit:
            confidence_tier = "strong"
        elif title_similarity >= 0.78 or (title_similarity >= 0.55 and author_overlap):
            confidence_tier = "medium"
        elif weak_relation_hit or score >= 0.56:
            confidence_tier = "weak"
        else:
            confidence_tier = "weak"

        candidate["score"] = round(min(0.99, score), 3)
        candidate["evidence"] = evidence
        candidate["confidence_tier"] = confidence_tier
        candidate["strong_relation_hit"] = strong_relation_hit
        candidate["weak_relation_hit"] = weak_relation_hit
        candidate["title_similarity"] = round(title_similarity, 3)

    def _merge_dataset_entry(self, combined: list[dict[str, Any]], entry: dict[str, Any]) -> None:
        entry_key = (entry.get("doi") or _normalize_title(entry.get("name", ""))).lower()
        if not entry_key:
            return
        for current in combined:
            current_key = (current.get("doi") or _normalize_title(current.get("name", ""))).lower()
            if current_key != entry_key:
                continue
            current["score"] = max(current.get("score", 0.0), entry.get("score", 0.0))
            current["source"] = current.get("source") if current.get("source") == entry.get("source") else f"{current.get('source')}, {entry.get('source')}"
            current["evidence"] = _dedupe_strings((current.get("evidence") or []) + (entry.get("evidence") or []))
            current["confidence_tier"] = self._max_confidence_tier(
                current.get("confidence_tier", "weak"),
                entry.get("confidence_tier", "weak"),
            )
            current["strong_relation_hit"] = current.get("strong_relation_hit", False) or entry.get("strong_relation_hit", False)
            current["weak_relation_hit"] = current.get("weak_relation_hit", False) or entry.get("weak_relation_hit", False)
            current["title_similarity"] = max(current.get("title_similarity", 0.0), entry.get("title_similarity", 0.0))
            if not current.get("url") and entry.get("url"):
                current["url"] = entry["url"]
            return
        combined.append(entry)

    def _should_keep_dataset_candidate(self, candidate: dict[str, Any]) -> bool:
        if candidate.get("source") == "heuristic":
            return True
        if candidate.get("strong_relation_hit"):
            return True
        if candidate.get("confidence_tier") == "strong":
            return True
        if candidate.get("confidence_tier") == "medium":
            return True
        if candidate.get("title_similarity", 0.0) >= 0.86:
            return True
        if candidate.get("score", 0.0) >= 0.72 and len(candidate.get("evidence", [])) >= 2:
            return True
        return False

    def _max_confidence_tier(self, left: str, right: str) -> str:
        order = {"weak": 0, "medium": 1, "strong": 2}
        return left if order.get(left, 0) >= order.get(right, 0) else right

    def _dataset_mapping_status(self, candidate: dict[str, Any]) -> str:
        if candidate.get("url"):
            return "linked_dataset"
        return "possible_mention"

    def _openaire_relation_to_dataset_candidate(
        self,
        relation: dict[str, Any],
        source_pid: str,
    ) -> dict[str, Any] | None:
        source_node = relation.get("source") or {}
        target_node = relation.get("target") or {}
        dataset_node = None
        for node in (target_node, source_node):
            if (node.get("type") or "").lower() == "dataset":
                dataset_node = node
                break
        if dataset_node is None:
            return None

        identifiers = dataset_node.get("identifiers") or []
        dataset_url = ""
        dataset_doi = ""
        for identifier in identifiers:
            id_url = identifier.get("idUrl") or ""
            if id_url and not dataset_url:
                dataset_url = id_url
            normalized = _normalize_doi(identifier.get("id"))
            if identifier.get("idScheme", "").lower() == "doi" and normalized:
                dataset_doi = normalized
                if not dataset_url:
                    dataset_url = f"https://doi.org/{dataset_doi}"

        relation_type = ((relation.get("relType") or {}).get("name") or "").lower()
        relation_label = (relation.get("relType") or {}).get("name") or "IsRelatedTo"
        evidence = [f"OpenAIRE reports a {relation_label} link between the paper and this dataset."]
        return {
            "name": dataset_node.get("title") or "Untitled dataset",
            "url": dataset_url,
            "source": "openaire",
            "doi": dataset_doi,
            "year": _extract_year(dataset_node.get("publicationDate")),
            "authors": [
                author.get("name")
                for author in dataset_node.get("authors", [])
                if author.get("name")
            ],
            "score": 0.34,
            "evidence": evidence,
            "relation_type": relation_type,
            "source_pid": source_pid,
        }

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

    def _build_research_profile(
        self,
        title: str,
        categories: list[str],
        methods: list[str],
        datasets: list[Any],
        repository_candidates: list[dict[str, Any]],
        abstract_text: str,
    ) -> dict[str, Any]:
        title_text = title.lower()
        category_text = " ".join(categories).lower()
        text_parts = [title, abstract_text, " ".join(categories), " ".join(str(method) for method in methods)]
        text = " ".join(part for part in text_parts if part).lower()
        domains = self._rank_profile_tags(
            text=text,
            title_text=title_text,
            mapping=DOMAIN_KEYWORDS,
            category_text=category_text,
            category_mapping=DOMAIN_CATEGORY_HINTS,
            min_score=2.0,
        )
        tasks = self._rank_profile_tags(
            text=text,
            title_text=title_text,
            mapping=TASK_KEYWORDS,
            min_score=1.8,
        )
        domains = self._align_domains_with_tasks(domains, tasks)
        method_families = self._collect_method_families(text, title_text, methods)
        artifact_profile = self._collect_artifact_profile(text, datasets, repository_candidates)
        community_fit = self._collect_community_fit(domains, categories, title)
        reproducibility_level = self._infer_reproducibility_level(datasets, repository_candidates)

        summary_parts = []
        if domains:
            summary_parts.append(domains[0])
        if tasks:
            summary_parts.append(tasks[0])
        if method_families:
            summary_parts.append(method_families[0])
        if any(isinstance(item, dict) and item.get("mapping_status") == "linked_dataset" for item in datasets):
            summary_parts.append("dataset-linked")
        elif datasets:
            summary_parts.append("dataset-aware")
        summary_parts.append(f"reproducibility {reproducibility_level}")

        return {
            "domains": domains,
            "tasks": tasks,
            "method_families": method_families,
            "artifact_profile": artifact_profile,
            "community_fit": community_fit,
            "reproducibility_level": reproducibility_level,
            "summary": " + ".join(summary_parts) if summary_parts else "metadata pending",
        }

    def _build_research_brief(
        self,
        query: str,
        aggregated_profile: dict[str, Any],
        representative_papers: list[dict[str, Any]],
        common_datasets: list[dict[str, Any]],
        common_methods: list[dict[str, Any]],
        code_repositories: list[dict[str, Any]],
    ) -> dict[str, Any]:
        actions: list[str] = []
        if common_datasets:
            actions.append(f"Start by checking dataset candidates around {common_datasets[0]['name']}.")
        else:
            actions.append("Dataset coverage is still sparse here; inspect representative papers manually.")
        if common_methods:
            actions.append(f"Method family to anchor on: {common_methods[0]['name']}.")
        if code_repositories:
            actions.append("There is code evidence in this cluster, so reproducibility exploration should start with repositories.")
        else:
            actions.append("Code evidence is weak in this cluster; expect more manual repository verification.")

        starter_paper = representative_papers[0] if representative_papers else {}
        headline = aggregated_profile.get("summary") or f"{query} research asset overview"
        return {
            "headline": headline,
            "starter_paper": {
                "title": starter_paper.get("title"),
                "url": starter_paper.get("landing_page_url") or starter_paper.get("pdf_url") or "",
            } if starter_paper else {},
            "actions": actions[:3],
            "availability": {
                "papers": len(representative_papers),
                "datasets": len(common_datasets),
                "methods": len(common_methods),
                "repositories": len(code_repositories),
            },
        }

    def _build_topic_asset_brief(
        self,
        query: str,
        aggregated_profile: dict[str, Any],
        common_datasets: list[dict[str, Any]],
        common_methods: list[dict[str, Any]],
        benchmark_assets: list[dict[str, Any]],
        code_repositories: list[dict[str, Any]],
    ) -> dict[str, Any]:
        focus = aggregated_profile.get("summary") or f"{query} asset overview"
        actions: list[str] = []
        if common_datasets:
            actions.append(f"Inspect the strongest dataset candidates around {common_datasets[0]['name']}.")
        if code_repositories:
            actions.append("Validate repository quality next: stars alone are not enough for reproducibility.")
        if benchmark_assets:
            actions.append("Benchmarks exist here; use them to compare method claims before following code.")
        if common_methods:
            actions.append(f"Method family to anchor on: {common_methods[0]['name']}.")
        if not actions:
            actions.append("Public asset coverage is still sparse; inspect the underlying papers manually.")
        return {
            "headline": focus,
            "focus": [
                {"label": "datasets", "count": len(common_datasets)},
                {"label": "repositories", "count": len(code_repositories)},
                {"label": "benchmarks", "count": len(benchmark_assets)},
                {"label": "methods", "count": len(common_methods)},
            ],
            "actions": actions[:4],
        }

    def _aggregate_research_profiles(
        self,
        profiles: list[dict[str, Any]],
        query_profile: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        min_count = 2 if len(profiles) >= 4 else 1

        def top_values(field_name: str, limit: int = 4) -> list[str]:
            counts: dict[str, int] = {}
            for profile in profiles:
                for value in profile.get(field_name, []):
                    counts[value] = counts.get(value, 0) + 1
            if query_profile:
                for value in query_profile.get(field_name, []):
                    counts[value] = counts.get(value, 0) + 3
            filtered = [
                (item, count)
                for item, count in counts.items()
                if count >= min_count
            ] or list(counts.items())
            if query_profile and query_profile.get(field_name):
                preferred = set(query_profile.get(field_name, []))
                prioritized = [
                    (item, count)
                    for item, count in filtered
                    if item in preferred
                ]
                extras = [
                    (item, count)
                    for item, count in filtered
                    if item not in preferred and count >= (min_count + 1 if field_name in {"domains", "tasks"} else min_count)
                ]
                filtered = prioritized + extras if prioritized else filtered
            return [item for item, _ in sorted(filtered, key=lambda pair: (-pair[1], pair[0]))[:limit]]

        reproducibility = "low"
        if any(profile.get("reproducibility_level") == "high" for profile in profiles):
            reproducibility = "high"
        elif any(profile.get("reproducibility_level") == "medium" for profile in profiles):
            reproducibility = "medium"

        primary_query_domain = (query_profile or {}).get("domains", [])[:1]
        domain_limit = 2 if primary_query_domain and primary_query_domain[0] in {"materials", "chemistry", "biology", "medicine"} else 3
        domains = top_values("domains", limit=domain_limit)
        tasks = top_values("tasks", limit=4)
        method_families = top_values("method_families")
        artifact_profile = top_values("artifact_profile")
        community_fit = self._align_community_fit_with_domains(top_values("community_fit"), domains)
        summary_parts = [part for part in [domains[:1], tasks[:1], method_families[:1]] if part]
        summary = " + ".join(part[0] for part in summary_parts)
        if summary:
            summary = f"{summary} + reproducibility {reproducibility}"
        else:
            summary = f"research assets + reproducibility {reproducibility}"
        return {
            "domains": domains,
            "tasks": tasks,
            "method_families": method_families,
            "artifact_profile": artifact_profile,
            "community_fit": community_fit,
            "reproducibility_level": reproducibility,
            "summary": summary,
        }

    def _align_domains_with_tasks(self, domains: list[str], tasks: list[str]) -> list[str]:
        scores: dict[str, float] = {}
        for index, domain in enumerate(domains):
            scores[domain] = max(scores.get(domain, 0.0), 3.0 - index * 0.3)
        for task in tasks:
            for index, domain in enumerate(TASK_DOMAIN_HINTS.get(task, [])):
                scores[domain] = scores.get(domain, 0.0) + (2.5 - index * 0.5)
        ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
        return [domain for domain, score in ranked if score >= 2.0][:4]

    def _research_profile_alignment_score(
        self,
        paper_profile: dict[str, Any],
        query_profile: dict[str, Any],
        query: str,
        title: str,
    ) -> float:
        score = _title_similarity(query, title)
        score += 0.25 * len(set(paper_profile.get("domains", [])) & set(query_profile.get("domains", [])))
        score += 0.2 * len(set(paper_profile.get("tasks", [])) & set(query_profile.get("tasks", [])))
        score += 0.1 * len(set(paper_profile.get("method_families", [])) & set(query_profile.get("method_families", [])))
        return round(score, 3)

    def _align_community_fit_with_domains(self, community_fit: list[str], domains: list[str]) -> list[str]:
        aligned: list[str] = []
        allowed = {"AI4Science"}
        if "materials" in domains:
            allowed.add("materials")
        if "chemistry" in domains:
            allowed.add("chem")
        if "biology" in domains or "medicine" in domains:
            allowed.add("bio")
        if "ai" in domains:
            allowed.update({"CV", "NLP"})

        for label in community_fit:
            if label in allowed or label in domains:
                aligned.append(label)
        if not aligned:
            aligned = community_fit[:3]
        return aligned[:4]

    def _aggregate_named_assets(self, groups: list[list[str]], limit: int = 8) -> list[dict[str, Any]]:
        counts: dict[str, int] = {}
        for group in groups:
            for item in group:
                counts[item] = counts.get(item, 0) + 1
        return [
            {"name": name, "count": count}
            for name, count in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))[:limit]
        ]

    def _aggregate_dataset_assets(self, papers: list[dict[str, Any]], limit: int = 8) -> list[dict[str, Any]]:
        counts: dict[str, dict[str, Any]] = {}
        for paper in papers:
            for dataset in paper.get("datasets", []):
                if isinstance(dataset, dict):
                    name = dataset.get("name")
                    if not name:
                        continue
                    if dataset.get("mapping_status") != "linked_dataset" and not self._is_plausible_dataset_name(name):
                        continue
                    entry = counts.setdefault(
                        name,
                        {
                            "name": name,
                            "count": 0,
                            "mapping_status": dataset.get("mapping_status", "possible_mention"),
                            "url": dataset.get("url", ""),
                            "source": dataset.get("source", ""),
                        },
                    )
                    entry["count"] += 1
                    if dataset.get("mapping_status") == "linked_dataset":
                        entry["mapping_status"] = "linked_dataset"
                    if not entry.get("url") and dataset.get("url"):
                        entry["url"] = dataset["url"]
                else:
                    name = str(dataset).strip()
                    if not name:
                        continue
                    if not self._is_plausible_dataset_name(name):
                        continue
                    entry = counts.setdefault(
                        name,
                        {"name": name, "count": 0, "mapping_status": "possible_mention", "url": "", "source": "heuristic"},
                    )
                    entry["count"] += 1
        return sorted(counts.values(), key=lambda item: (-item["count"], item["name"]))[:limit]

    def _aggregate_repository_assets(self, papers: list[dict[str, Any]], limit: int = 6) -> list[dict[str, Any]]:
        repositories: dict[str, dict[str, Any]] = {}
        for paper in papers:
            for candidate in paper.get("repository_candidates", []):
                key = candidate.get("url") or candidate.get("name")
                if not key:
                    continue
                current = repositories.setdefault(
                    key,
                    {
                        "name": candidate.get("name", "repository"),
                        "url": candidate.get("url", ""),
                        "score": candidate.get("score", 0.0),
                        "count": 0,
                    },
                )
                current["count"] += 1
                current["score"] = max(current["score"], candidate.get("score", 0.0))
        return sorted(repositories.values(), key=lambda item: (-item["count"], -item["score"], item["name"]))[:limit]

    def _aggregate_benchmark_assets(self, papers: list[dict[str, Any]], limit: int = 6) -> list[dict[str, Any]]:
        benchmarks: dict[str, dict[str, Any]] = {}
        for paper in papers:
            profile = paper.get("research_profile", {})
            qualifies = (
                "benchmarking" in (profile.get("tasks") or [])
                or "benchmark" in (profile.get("artifact_profile") or [])
            )
            if not qualifies:
                continue
            title = paper.get("title") or ""
            if not title:
                continue
            entry = benchmarks.setdefault(
                title,
                {
                    "name": title,
                    "count": 0,
                    "url": paper.get("landing_page_url") or paper.get("pdf_url") or "",
                    "year": paper.get("year"),
                },
            )
            entry["count"] += 1
        return sorted(benchmarks.values(), key=lambda item: (-item["count"], item["name"]))[:limit]

    def _build_subdirection_layers(self, papers: list[dict[str, Any]], limit: int = 4) -> list[dict[str, Any]]:
        layers: dict[str, dict[str, Any]] = {}
        for paper in papers:
            profile = paper.get("research_profile", {})
            name = (
                (profile.get("tasks") or [None])[0]
                or (profile.get("domains") or [None])[0]
            )
            if not name:
                continue
            layer = layers.setdefault(
                name,
                {
                    "name": name,
                    "count": 0,
                    "domains": [],
                    "methods": [],
                    "papers": [],
                },
            )
            layer["count"] += 1
            layer["domains"].extend(profile.get("domains", [])[:2])
            layer["methods"].extend(profile.get("method_families", [])[:2])
            layer["papers"].append(
                {
                    "title": paper.get("title", "Untitled paper"),
                    "url": paper.get("landing_page_url") or paper.get("pdf_url") or "",
                }
            )

        ranked = sorted(layers.values(), key=lambda item: (-item["count"], item["name"]))[:limit]
        for layer in ranked:
            layer["domains"] = _dedupe_strings(layer["domains"])[:3]
            layer["methods"] = _dedupe_strings(layer["methods"])[:3]
            layer["papers"] = layer["papers"][:3]
            summary_parts = []
            if layer["domains"]:
                summary_parts.append(layer["domains"][0])
            if layer["methods"]:
                summary_parts.append(layer["methods"][0])
            layer["summary"] = " + ".join(summary_parts) if summary_parts else layer["name"]
        return ranked

    def _build_reading_path(self, papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
        ordered = sorted(
            papers,
            key=lambda item: (
                item.get("year") or 9999,
                -int(item.get("citation_count") or 0),
            ),
        )
        reading_path = []
        for index, paper in enumerate(ordered[:5]):
            stage = "recent follow-up"
            if index == 0:
                stage = "foundation"
            elif index == 1:
                stage = "bridge"
            reading_path.append(
                {
                    "title": paper.get("title", "Untitled paper"),
                    "year": paper.get("year"),
                    "stage": stage,
                    "url": paper.get("landing_page_url") or paper.get("pdf_url") or "",
                }
            )
        return reading_path

    def _is_plausible_dataset_name(self, name: str) -> bool:
        lowered = name.strip().lower()
        if not lowered:
            return False
        if lowered in {item.lower() for item in DATASET_KEYWORDS}:
            return True
        if any(keyword in lowered for keyword in ("dataset", "benchmark", "challenge", "database", "corpus")):
            return True
        if len(lowered) < 5:
            return False
        if re.fullmatch(r"[a-z0-9\-]+", lowered) and any(char.isdigit() for char in lowered):
            return False
        if re.fullmatch(r"[a-z]{1,4}\-?", lowered):
            return False
        return " " in lowered

    def _rank_profile_tags(
        self,
        text: str,
        title_text: str,
        mapping: dict[str, list[str]],
        category_text: str = "",
        category_mapping: dict[str, list[str]] | None = None,
        min_score: float = 1.5,
    ) -> list[str]:
        scored: list[tuple[str, float]] = []
        for label, keywords in mapping.items():
            score = 0.0
            for keyword in keywords:
                if _text_contains_keyword(title_text, keyword):
                    score += 2.0
                elif _text_contains_keyword(text, keyword):
                    score += 1.0
            if category_mapping:
                for keyword in category_mapping.get(label, []):
                    if _text_contains_keyword(category_text, keyword):
                        score += 2.0
            if score >= min_score:
                scored.append((label, score))
        scored.sort(key=lambda item: (-item[1], item[0]))
        return [label for label, _ in scored[:4]]

    def _collect_method_families(self, text: str, title_text: str, methods: list[str]) -> list[str]:
        lowered_methods = " ".join(methods).lower()
        families: list[tuple[str, float]] = []
        for label, keywords in METHOD_FAMILY_KEYWORDS.items():
            score = 0.0
            for keyword in keywords:
                if _text_contains_keyword(title_text, keyword):
                    score += 2.0
                elif _text_contains_keyword(text, keyword) or _text_contains_keyword(lowered_methods, keyword):
                    score += 1.0
            if score >= 1.0:
                families.append((label, score))
        families.sort(key=lambda item: (-item[1], item[0]))
        return [label for label, _ in families[:4]]

    def _collect_artifact_profile(
        self,
        text: str,
        datasets: list[Any],
        repository_candidates: list[dict[str, Any]],
    ) -> list[str]:
        artifacts: list[str] = []
        if repository_candidates:
            artifacts.append("code")
            if any(candidate.get("name", "").lower().endswith((".ckpt", ".pt", ".pth")) for candidate in repository_candidates):
                artifacts.append("model weights")
        if datasets:
            artifacts.append("dataset")
            if any(isinstance(item, dict) and item.get("mapping_status") == "linked_dataset" for item in datasets):
                artifacts.append("benchmark")
        for label, keywords in ARTIFACT_PROFILE_KEYWORDS.items():
            if any(keyword in text for keyword in keywords):
                artifacts.append(label)
        return _dedupe_strings(artifacts)[:6]

    def _collect_community_fit(self, domains: list[str], categories: list[str], title: str) -> list[str]:
        fits: list[str] = []
        lowered_categories = " ".join(categories).lower()
        lowered_title = title.lower()
        if any(domain in {"materials", "chemistry", "biology", "medicine", "physics", "climate"} for domain in domains):
            fits.append("AI4Science")
        if "cs.cv" in lowered_categories or "vision" in lowered_title:
            fits.append("CV")
        if "cs.cl" in lowered_categories or "language" in lowered_title:
            fits.append("NLP")
        if "biology" in domains or "medicine" in domains:
            fits.append("bio")
        if "chemistry" in domains:
            fits.append("chem")
        if "materials" in domains:
            fits.append("materials")
        if not fits and domains:
            fits.append(domains[0])
        return _dedupe_strings(fits)[:5]

    def _infer_reproducibility_level(
        self,
        datasets: list[Any],
        repository_candidates: list[dict[str, Any]],
    ) -> str:
        linked_datasets = sum(
            1 for item in datasets
            if isinstance(item, dict) and item.get("mapping_status") == "linked_dataset"
        )
        if repository_candidates and linked_datasets:
            return "high"
        if repository_candidates or datasets:
            return "medium"
        return "low"

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

        methods = [keyword for keyword in METHOD_KEYWORDS if _text_contains_keyword(lowered, keyword)]
        datasets = [keyword for keyword in DATASET_KEYWORDS if _text_contains_keyword(lowered, keyword)]

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
