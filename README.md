<p align="center">
  <img src="docs/assets/banner.svg" alt="CRUXpider banner" width="100%">
</p>

<p align="center">
  <a href="./LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-0f766e.svg"></a>
  <img alt="Python 3.10+" src="https://img.shields.io/badge/python-3.10%2B-1d4ed8.svg">
  <img alt="Flask" src="https://img.shields.io/badge/backend-Flask-111827.svg">
  <img alt="Status" src="https://img.shields.io/badge/status-public%20release-f59e0b.svg">
</p>

# CRUXpider

Academic paper analysis from titles, with arXiv metadata, OpenAlex related-paper discovery, and repository search fallback for reproducibility workflows.

## Highlights

- `Single paper analysis`: venue, PDF, categories, AI signal, and code-search fallback
- `Related papers`: OpenAlex-based literature expansion
- `CSV batch mode`: title list in, enriched CSV out
- `Web UI + JSON API`: simple to use locally or extend in other tooling
- `Graceful degradation`: keeps working when external sources are incomplete

## Data Sources

- `arXiv`
  Primary source for title lookup, categories, and PDF links.
- `OpenAlex`
  Source for venue metadata and related works.
- `GitHub Search`
  Repository fallback when structured paper-to-code metadata is not available.

## Papers with Code Status

As of March 17, 2026, requests to `https://paperswithcode.com/api/v1/...` redirect to [Hugging Face Papers](https://huggingface.co/papers/trending). For CRUXpider, that means the legacy Papers with Code API is no longer treated as a reliable machine API.

Instead of failing hard, CRUXpider now:

- detects the redirect,
- reports source status through the API,
- falls back to GitHub repository search links.

This keeps the tool usable even though the old integration path has effectively disappeared.

## Quick Start

### 1. Create an environment

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment variables

```bash
cp .env.example .env
```

Set values as needed:

```bash
CRUXPIDER_HOST=0.0.0.0
CRUXPIDER_PORT=5003
CRUXPIDER_SECRET_KEY=change-me
PYALEX_EMAIL=your_email@example.com
CRUXPIDER_REQUEST_TIMEOUT=12
CRUXPIDER_MAX_BATCH_SIZE=50
```

`PYALEX_EMAIL` is recommended because OpenAlex behaves better when requests include a contact email.

### 3. Start the app

```bash
python app.py
```

Open [http://127.0.0.1:5003](http://127.0.0.1:5003).

## API Overview

### Endpoints

- `POST /api/search_paper`
- `POST /api/find_relevant_papers`
- `POST /api/batch_process`
- `GET /api/status`
- `GET /api/health`

### Example request

```bash
curl -X POST http://127.0.0.1:5003/api/search_paper \
  -H "Content-Type: application/json" \
  -d '{"title": "Attention Is All You Need"}'
```

### Example response shape

```json
{
  "title": "Attention Is All You Need",
  "journal_conference": "NeurIPS",
  "pdf_url": "https://arxiv.org/pdf/1706.03762.pdf",
  "categories": ["cs.CL", "cs.LG"],
  "ai_related": "YES",
  "datasets": [],
  "methods": [],
  "repository_url": "https://github.com/search?q=Attention+Is+All+You+Need&type=repositories",
  "warnings": []
}
```

## Running Tests

```bash
python -m unittest discover -s tests -v
```

The current test suite focuses on route-level behavior and response contracts for the main Flask API.

## Project Structure

```text
CRUXpider/
├── app.py                  # Main Flask application
├── app_integrated.py       # Compatibility entrypoint
├── CRUXpider.py            # Legacy CLI-oriented logic
├── config.py               # Environment-driven settings
├── templates/              # HTML templates
├── static/                 # Frontend assets
├── tests/                  # Route-level tests
└── requirements.txt
```

## Design Notes

- `Simple deployment`
  The app is intentionally lightweight and can run locally, behind Gunicorn, or in Docker.
- `Open-source safe defaults`
  Secrets are environment-based, and local artifacts are excluded by `.gitignore`.
- `Research workflow first`
  The UX is optimized around entering titles and getting actionable metadata back quickly.

## Known Limitations

- Paper title matching is heuristic and depends on external metadata quality.
- Repository discovery is currently a search fallback, not a verified paper-to-code mapping.
- Some fields may be empty when arXiv or OpenAlex does not expose the needed metadata.

## Roadmap

- Improve title matching and ranking quality.
- Add stronger repository extraction beyond GitHub search fallback.
- Add structured caching and request metrics.
- Add screenshot/demo assets for the repository homepage.

## Release

For the first public release checklist, see [PUBLISH_CHECKLIST.md](/Users/anthonyche/Desktop/CRUXpider/PUBLISH_CHECKLIST.md).

For the GitHub release draft, see [GITHUB_RELEASE_v0.1.0.md](/Users/anthonyche/Desktop/CRUXpider/GITHUB_RELEASE_v0.1.0.md).

## License

This project is released under the MIT License. See [LICENSE](/Users/anthonyche/Desktop/CRUXpider/LICENSE).
