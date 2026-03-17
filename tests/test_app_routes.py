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

    @patch("app.analyzer.analyze_single_paper")
    def test_search_paper_returns_json(self, mock_analyze):
        mock_analyze.return_value = {
            "title": "Attention Is All You Need",
            "journal": "NeurIPS",
            "journal_conference": "NeurIPS",
            "pdf_url": "https://arxiv.org/pdf/1706.03762.pdf",
            "categories": ["cs.CL", "cs.LG"],
            "ai_related": "YES",
            "datasets": [],
            "methods": [],
            "repository_url": "https://github.com/search?q=attention&type=repositories",
            "warnings": [],
            "source_status": {
                "paperswithcode_legacy_api": False,
                "paperswithcode_redirect_target": "https://huggingface.co/papers/trending",
                "arxiv": True,
                "openalex": True,
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

    @patch("app.analyzer.find_relevant_papers")
    def test_relevant_papers_route(self, mock_find_relevant):
        mock_find_relevant.return_value = [
            {
                "title": "BERT",
                "authors": ["Jacob Devlin"],
                "year": 2018,
                "url": "https://arxiv.org/abs/1810.04805",
            }
        ]

        response = self.client.post(
            "/api/find_relevant_papers",
            json={"title": "Attention Is All You Need", "max_papers": 1},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["papers"][0]["title"], "BERT")

    @patch("app.analyzer.analyze_single_paper")
    def test_batch_process_returns_csv(self, mock_analyze):
        mock_analyze.return_value = {
            "title": "Test Paper",
            "journal": "N/A",
            "journal_conference": "N/A",
            "pdf_url": "",
            "categories": [],
            "ai_related": "NO",
            "datasets": [],
            "methods": [],
            "repository_url": "N/A",
            "warnings": [],
            "source_status": {},
        }

        response = self.client.post(
            "/api/batch_process",
            data={"file": (io.BytesIO(b"Test Paper\n"), "papers.csv")},
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "text/csv")

    def test_status_route(self):
        response = self.client.get("/api/status")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertIn("github_search_fallback", payload)


if __name__ == "__main__":
    unittest.main()
