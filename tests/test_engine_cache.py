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

    def test_extract_methods_does_not_match_rag_inside_radiograph(self):
        engine = CRUXpiderEngine()
        methods, _ = engine._extract_methods_and_datasets(
            ["Chest radiograph diagnosis with clinical labels"]
        )

        self.assertNotIn("rag", methods)

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

    def test_build_research_profile_infers_ai4science_metadata(self):
        engine = CRUXpiderEngine()
        profile = engine._build_research_profile(
            title="Perovskite bandgap prediction with graph neural networks",
            categories=["materials informatics"],
            methods=["graph neural network"],
            datasets=[{"name": "Materials Project", "mapping_status": "linked_dataset", "url": "https://example.com"}],
            repository_candidates=[{"name": "repo", "url": "https://github.com/example/repo"}],
            abstract_text="This work studies materials property prediction for perovskite crystals.",
        )

        self.assertIn("materials", profile["domains"])
        self.assertIn("property prediction", profile["tasks"])
        self.assertIn("graph neural network", profile["method_families"])
        self.assertIn("AI4Science", profile["community_fit"])
        self.assertEqual(profile["reproducibility_level"], "high")

    def test_build_research_profile_keeps_materials_profile_focused(self):
        engine = CRUXpiderEngine()
        profile = engine._build_research_profile(
            title="Perovskite bandgap prediction with graph neural networks",
            categories=["materials informatics"],
            methods=["graph neural network"],
            datasets=[],
            repository_candidates=[],
            abstract_text="This work studies perovskite crystals and materials property prediction.",
        )

        self.assertEqual(profile["domains"][0], "materials")
        self.assertNotIn("biology", profile["domains"])
        self.assertNotIn("medicine", profile["domains"])

    def test_build_research_profile_infers_medicine_from_radiology_context(self):
        engine = CRUXpiderEngine()
        profile = engine._build_research_profile(
            title="Chest radiograph diagnosis with transformer models",
            categories=["medical imaging"],
            methods=["transformer"],
            datasets=[{"name": "CheXpert", "mapping_status": "linked_dataset", "url": "https://example.com"}],
            repository_candidates=[],
            abstract_text="A clinical radiology benchmark for disease diagnosis from patient chest X-rays.",
        )

        self.assertIn("medicine", profile["domains"])
        self.assertIn("bio", profile["community_fit"])
        self.assertIn("diagnosis", profile["tasks"])

    def test_build_research_profile_infers_chemistry_tasks(self):
        engine = CRUXpiderEngine()
        profile = engine._build_research_profile(
            title="Retrosynthesis planning for reaction prediction with graph models",
            categories=["chemistry"],
            methods=["graph neural network"],
            datasets=[],
            repository_candidates=[],
            abstract_text="We study reaction prediction and retrosynthesis planning for organic chemistry.",
        )

        self.assertIn("chemistry", profile["domains"])
        self.assertEqual(profile["domains"][0], "chemistry")
        self.assertIn("retrosynthesis", profile["tasks"])
        self.assertIn("reaction prediction", profile["tasks"])

    def test_build_research_profile_infers_biology_tasks(self):
        engine = CRUXpiderEngine()
        profile = engine._build_research_profile(
            title="Single-cell gene expression modeling with transformers",
            categories=["bioinformatics"],
            methods=["transformer"],
            datasets=[],
            repository_candidates=[],
            abstract_text="We model transcriptomics and genomic signals from single-cell experiments.",
        )

        self.assertIn("biology", profile["domains"])
        self.assertIn("genomics", profile["tasks"])

    def test_aggregate_research_profiles_prefers_query_domain(self):
        engine = CRUXpiderEngine()
        aggregated = engine._aggregate_research_profiles(
            [
                {
                    "domains": ["chemistry", "medicine"],
                    "tasks": ["drug discovery"],
                    "method_families": ["graph neural network"],
                    "artifact_profile": ["dataset"],
                    "community_fit": ["AI4Science", "chem", "bio"],
                    "reproducibility_level": "medium",
                },
                {
                    "domains": ["biology", "medicine"],
                    "tasks": ["drug discovery"],
                    "method_families": ["graph neural network"],
                    "artifact_profile": ["code"],
                    "community_fit": ["AI4Science", "bio"],
                    "reproducibility_level": "low",
                },
            ],
            query_profile={
                "domains": ["chemistry"],
                "tasks": ["drug discovery"],
                "method_families": [],
                "artifact_profile": [],
                "community_fit": ["AI4Science", "chem"],
            },
        )

        self.assertEqual(aggregated["domains"][0], "chemistry")
        self.assertIn("chem", aggregated["community_fit"])
        self.assertNotIn("materials", aggregated["community_fit"])

    def test_explore_research_assets_topic_returns_asset_finder_shape(self):
        engine = CRUXpiderEngine()
        representative = {
            "title": "MatBench discovery",
            "year": 2024,
            "confidence": 0.8,
            "citation_count": 10,
            "repository_candidates": [{"name": "repo", "url": "https://github.com/example/repo", "score": 0.9}],
            "datasets": [{"name": "materials project", "mapping_status": "linked_dataset", "url": "https://example.com/dataset"}],
            "research_profile": {
                "domains": ["materials"],
                "tasks": ["benchmarking"],
                "method_families": ["graph neural network"],
                "artifact_profile": ["dataset", "benchmark", "code"],
                "community_fit": ["AI4Science", "materials"],
                "reproducibility_level": "medium",
                "summary": "materials + benchmarking + graph neural network + reproducibility medium",
            },
            "landing_page_url": "https://example.com/paper",
        }

        with patch.object(engine, "_search_openalex_free_text", return_value=[{"title": "MatBench discovery", "citation_count": 10}]), patch.object(
            engine, "analyze_single_paper", return_value=representative
        ):
            result = engine.explore_research_assets("materials benchmark", mode="topic", max_papers=3)

        self.assertEqual(result["mode"], "topic")
        self.assertIn("asset_brief", result)
        self.assertIn("benchmark_assets", result)
        self.assertNotIn("representative_papers", result)
        self.assertGreaterEqual(result["total_assets"], 1)

    def test_explore_research_assets_area_returns_route_map_shape(self):
        engine = CRUXpiderEngine()
        representative = {
            "title": "Single-cell atlas modeling",
            "year": 2024,
            "confidence": 0.8,
            "citation_count": 10,
            "repository_candidates": [],
            "datasets": [],
            "research_profile": {
                "domains": ["biology"],
                "tasks": ["genomics"],
                "method_families": ["transformer"],
                "artifact_profile": [],
                "community_fit": ["AI4Science", "bio"],
                "reproducibility_level": "low",
                "summary": "biology + genomics + transformer + reproducibility low",
            },
            "landing_page_url": "https://example.com/paper",
        }

        with patch.object(engine, "_search_openalex_free_text", return_value=[{"title": "Single-cell atlas modeling", "citation_count": 10}]), patch.object(
            engine, "analyze_single_paper", return_value=representative
        ):
            result = engine.explore_research_assets("single-cell biology", mode="area", max_papers=3)

        self.assertEqual(result["mode"], "area")
        self.assertIn("research_brief", result)
        self.assertIn("representative_papers", result)
        self.assertIn("subdirection_layers", result)

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
