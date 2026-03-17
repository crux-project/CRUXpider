import unittest
from unittest.mock import patch

from cruxpider_engine import CRUXpiderEngine, MergedPaper, PaperCandidate


class EngineCacheTestCase(unittest.TestCase):
    def test_analyze_single_paper_uses_ttl_cache(self):
        engine = CRUXpiderEngine()
        candidate = PaperCandidate(
            source="semantic_scholar",
            source_id="paper-1",
            title="Attention Is All You Need",
            venue="NeurIPS",
            identifiers={"semantic_scholar": "paper-1", "arxiv": "1706.03762"},
            title_score=0.98,
        )
        merged = MergedPaper(
            candidates=[candidate],
            sources={"semantic_scholar"},
            identifiers={"semantic_scholar": "paper-1", "arxiv": "1706.03762"},
            score=0.95,
        )

        with patch.object(engine, "get_source_status", return_value={"github_search_fallback": True}), patch.object(
            engine, "_collect_candidates", return_value=[candidate]
        ) as mock_collect, patch.object(engine, "_merge_candidates", return_value=merged), patch.object(
            engine,
            "_discover_repositories",
            return_value=([{"name": "repo", "url": "https://github.com/example/repo", "score": 0.9, "reasons": []}], None),
        ):
            first = engine.analyze_single_paper("Attention Is All You Need")
            second = engine.analyze_single_paper("Attention Is All You Need")

        self.assertEqual(mock_collect.call_count, 1)
        self.assertEqual(first["repository_url"], second["repository_url"])
        self.assertEqual(first["identifiers"]["arxiv"], "1706.03762")

    def test_extract_methods_and_datasets_from_text(self):
        engine = CRUXpiderEngine()
        methods, datasets = engine._extract_methods_and_datasets(
            [
                "A Vision Transformer for Image Classification",
                "We evaluate on ImageNet and CIFAR-10 with a transformer model.",
            ]
        )

        self.assertIn("transformer", methods)
        self.assertIn("imagenet", datasets)
        self.assertIn("cifar-10", datasets)

    def test_merge_related_entry_deduplicates_similar_titles(self):
        engine = CRUXpiderEngine()
        combined = [
            {
                "title": "Attention is All you Need",
                "year": 2017,
                "score": 0.9,
                "signal_count": 2,
                "sources": ["semantic_scholar"],
                "reasons": ["Recommended by Semantic Scholar."],
                "citation_count": 100,
                "categories": ["Machine Learning"],
                "methods": ["transformer"],
                "datasets": [],
                "url": "https://example.com/a",
            }
        ]
        engine._merge_related_entry(
            combined,
            {
                "title": "Attention Is All You Need",
                "year": 2017,
                "score": 0.95,
                "signal_count": 4,
                "sources": ["openalex"],
                "reasons": ["Overlaps on topics: machine learning."],
                "citation_count": 120,
                "categories": ["Deep Learning"],
                "methods": ["transformer"],
                "datasets": ["WMT"],
                "url": "https://example.com/b",
            },
        )

        self.assertEqual(len(combined), 1)
        self.assertIn("openalex", combined[0]["sources"])
        self.assertIn("WMT", combined[0]["datasets"])
        self.assertEqual(combined[0]["score"], 0.95)


if __name__ == "__main__":
    unittest.main()
