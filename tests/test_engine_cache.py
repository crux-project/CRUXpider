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

    def test_filtered_heuristic_datasets_prefers_title_aligned_terms(self):
        engine = CRUXpiderEngine()
        best = PaperCandidate(
            source="semantic_scholar",
            source_id="paper-1",
            title="Microsoft COCO: Common Objects in Context",
            datasets=["imagenet", "coco"],
        )
        merged = MergedPaper(candidates=[best], sources={"semantic_scholar"}, identifiers={}, score=0.9)

        heuristics = engine._filtered_heuristic_datasets(best, merged)

        self.assertEqual(heuristics, ["coco"])

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

    def test_group_relevant_papers_buckets_by_group_tag(self):
        engine = CRUXpiderEngine()
        grouped = engine.group_relevant_papers(
            [
                {"title": "Paper A", "groups": ["same-author", "same-wave"]},
                {"title": "Paper B", "groups": ["strong-follow-up"]},
            ]
        )

        self.assertEqual(grouped["same_author"][0]["title"], "Paper A")
        self.assertEqual(grouped["same_wave"][0]["title"], "Paper A")
        self.assertEqual(grouped["strong_follow_up"][0]["title"], "Paper B")

    def test_discover_datasets_prefers_public_candidates(self):
        engine = CRUXpiderEngine()
        best = PaperCandidate(
            source="semantic_scholar",
            source_id="paper-1",
            title="Attention Is All You Need",
            year=2017,
            authors=["Ashish Vaswani"],
            methods=["transformer"],
            identifiers={"doi": "10.1000/test", "arxiv": "1706.03762"},
            title_score=0.98,
        )
        merged = MergedPaper(
            candidates=[best],
            sources={"semantic_scholar"},
            identifiers={"doi": "10.1000/test", "arxiv": "1706.03762"},
            score=0.95,
        )

        with patch.object(engine, "_fetch_datacite_dataset_candidates", return_value=[{
            "name": "WMT Dataset",
            "url": "https://example.com/wmt",
            "source": "datacite",
            "score": 0.88,
            "confidence_tier": "strong",
            "evidence": ["Public metadata links this dataset to the paper."],
        }]), patch.object(engine, "_fetch_openaire_dataset_candidates", return_value=[]), patch.object(
            engine, "_fetch_crossref_dataset_candidates", return_value=[]
        ), patch.object(
            engine, "_fetch_openalex_dataset_candidates", return_value=[]
        ):
            datasets, warning = engine._discover_datasets(best, merged)

        self.assertIsNone(warning)
        self.assertEqual(datasets[0]["name"], "WMT Dataset")
        self.assertEqual(datasets[0]["source"], "datacite")
        self.assertEqual(datasets[0]["confidence_tier"], "strong")
        self.assertEqual(datasets[0]["mapping_status"], "linked_dataset")

    def test_discover_datasets_marks_heuristics_as_possible_mentions(self):
        engine = CRUXpiderEngine()
        best = PaperCandidate(
            source="semantic_scholar",
            source_id="paper-1",
            title="Microsoft COCO: Common Objects in Context",
            datasets=["coco"],
            identifiers={"doi": "10.1000/test"},
        )
        merged = MergedPaper(candidates=[best], sources={"semantic_scholar"}, identifiers={"doi": "10.1000/test"}, score=0.9)

        with patch.object(engine, "_fetch_openaire_dataset_candidates", return_value=[]), patch.object(
            engine, "_fetch_datacite_dataset_candidates", return_value=[]
        ), patch.object(engine, "_fetch_crossref_dataset_candidates", return_value=[]), patch.object(
            engine, "_fetch_openalex_dataset_candidates", return_value=[]
        ):
            datasets, warning = engine._discover_datasets(best, merged)

        self.assertIsNone(warning)
        self.assertEqual(datasets[0]["name"], "coco")
        self.assertEqual(datasets[0]["mapping_status"], "possible_mention")

    def test_openaire_relation_to_dataset_candidate_parses_node(self):
        engine = CRUXpiderEngine()

        candidate = engine._openaire_relation_to_dataset_candidate(
            {
                "source": {"type": "publication", "title": "Paper"},
                "target": {
                    "type": "dataset",
                    "title": "Linked Dataset",
                    "publicationDate": "2024-01-01",
                    "authors": [{"name": "Alice"}],
                    "identifiers": [
                        {
                            "id": "10.5281/zenodo.1234",
                            "idScheme": "doi",
                            "idUrl": "https://doi.org/10.5281/zenodo.1234",
                        }
                    ],
                },
                "relType": {"name": "IsSupplementTo"},
            },
            "10.1000/test",
        )

        self.assertIsNotNone(candidate)
        self.assertEqual(candidate["source"], "openaire")
        self.assertEqual(candidate["doi"], "10.5281/zenodo.1234")
        self.assertEqual(candidate["url"], "https://doi.org/10.5281/zenodo.1234")
        self.assertEqual(candidate["year"], 2024)


if __name__ == "__main__":
    unittest.main()
