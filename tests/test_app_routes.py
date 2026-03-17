import io
import unittest
from unittest.mock import patch

from app import app


class AppRoutesTestCase(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()

    def test_search_requires_title(self):
        response = self.client.post("/api/search_paper", json={})
        self.assertEqual(response.status_code, 400)

    @patch("app.engine.analyze_single_paper")
    def test_search_paper_returns_json(self, mock_analyze):
        mock_analyze.return_value = {
            "title": "Attention Is All You Need",
            "journal": "NeurIPS",
            "journal_conference": "NeurIPS",
            "pdf_url": "https://arxiv.org/pdf/1706.03762.pdf",
            "categories": ["cs.CL", "cs.LG"],
            "ai_related": "YES",
            "datasets": [{"name": "WMT", "source": "datacite", "score": 0.81, "evidence": ["Public metadata links this dataset to the paper."]}],
            "dataset_candidates": [{"name": "WMT", "source": "datacite", "score": 0.81, "evidence": ["Public metadata links this dataset to the paper."]}],
            "methods": [],
            "repository_url": "https://github.com/search?q=attention&type=repositories",
            "warnings": [],
            "confidence": 0.95,
            "matched_sources": ["arxiv", "semantic_scholar"],
            "identifiers": {"arxiv": "1706.03762"},
            "source_status": {
                "paperswithcode_legacy_api": False,
                "paperswithcode_redirect_target": "https://huggingface.co/papers/trending",
                "arxiv": True,
                "openalex": True,
                "semantic_scholar": True,
                "crossref": True,
                "datacite": True,
                "github_api": True,
                "github_search_fallback": True,
            },
        }

        response = self.client.post(
            "/api/search_paper",
            json={"title": "Attention Is All You Need"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["title"], "Attention Is All You Need")
        self.assertEqual(payload["ai_related"], "YES")
        self.assertEqual(payload["confidence"], 0.95)

    @patch("app.engine.find_relevant_papers")
    def test_relevant_papers_route(self, mock_find_relevant):
        mock_find_relevant.return_value = [
            {
                "title": "BERT",
                "authors": ["Jacob Devlin"],
                "year": 2018,
                "url": "https://arxiv.org/abs/1810.04805",
                "score": 0.88,
                "sources": ["semantic_scholar"],
                "reasons": ["Recommended by Semantic Scholar."],
                "groups": ["strong-follow-up"],
            }
        ]

        with patch("app.engine.group_relevant_papers", return_value={"strong_follow_up": mock_find_relevant.return_value}):
            response = self.client.post(
                "/api/find_relevant_papers",
                json={"title": "Attention Is All You Need", "max_papers": 1},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["papers"][0]["title"], "BERT")
        self.assertIn("grouped_papers", payload)

    @patch("app.engine.analyze_single_paper")
    def test_batch_process_returns_csv(self, mock_analyze):
        mock_analyze.return_value = {
            "title": "Test Paper",
            "journal": "N/A",
            "journal_conference": "N/A",
            "pdf_url": "",
            "categories": [],
            "ai_related": "NO",
            "datasets": [],
            "dataset_candidates": [],
            "methods": [],
            "repository_url": "N/A",
            "warnings": [],
            "confidence": 0.51,
            "matched_sources": [],
            "identifiers": {},
            "source_status": {},
        }

        response = self.client.post(
            "/api/batch_process",
            data={"file": (io.BytesIO(b"Test Paper\n"), "papers.csv")},
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "text/csv")

    @patch("app.engine.get_source_status")
    def test_status_route(self, mock_status):
        mock_status.return_value = {
            "paperswithcode_legacy_api": False,
            "paperswithcode_redirect_target": "https://huggingface.co/papers/trending",
            "arxiv": True,
            "openalex": True,
            "semantic_scholar": True,
            "crossref": True,
            "datacite": True,
            "github_api": True,
            "github_search_fallback": True,
        }
        response = self.client.get("/api/status")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertIn("github_search_fallback", payload)
        self.assertIn("semantic_scholar_available", payload)
        self.assertIn("crossref_available", payload)
        self.assertIn("datacite_available", payload)

    @patch("app.engine.get_source_status")
    def test_health_route(self, mock_status):
        mock_status.return_value = {
            "paperswithcode_legacy_api": False,
            "paperswithcode_redirect_target": "https://huggingface.co/papers/trending",
            "arxiv": True,
            "openalex": True,
            "semantic_scholar": True,
            "crossref": True,
            "datacite": True,
            "github_api": True,
            "github_search_fallback": True,
        }
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["status"], "healthy")
        self.assertIn("semantic_scholar", payload["services"])
        self.assertIn("crossref", payload["services"])
        self.assertIn("datacite", payload["services"])


if __name__ == "__main__":
    unittest.main()
