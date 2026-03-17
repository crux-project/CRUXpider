# CRUXpider

CRUXpider is an academic paper analysis tool that takes a paper title and returns venue information, PDF links, AI-related tags, related papers, and a code search fallback for reproducibility workflows.

## What It Does

- Analyze a single paper title.
- Find related papers through OpenAlex.
- Batch-process a CSV of paper titles.
- Provide a web UI and JSON API for lightweight research workflows.

## Data Sources

- `arXiv` for paper metadata and PDF links.
- `OpenAlex` for venue information and related works.
- `GitHub Search` as the current repository fallback.

## Important Note About Papers with Code

As of March 17, 2026, requests to `https://paperswithcode.com/api/v1/...` redirect to `https://huggingface.co/papers/trending`, so the old Papers with Code API is no longer a reliable machine API for this project. CRUXpider now treats that source as deprecated and falls back to GitHub search links instead of failing hard.

## Quick Start

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python app.py
```

Open [http://127.0.0.1:5003](http://127.0.0.1:5003).

## Environment Variables

```bash
CRUXPIDER_HOST=0.0.0.0
CRUXPIDER_PORT=5003
CRUXPIDER_SECRET_KEY=change-me
PYALEX_EMAIL=your_email@example.com
CRUXPIDER_REQUEST_TIMEOUT=12
CRUXPIDER_MAX_BATCH_SIZE=50
```

`PYALEX_EMAIL` is recommended because OpenAlex requests are better-behaved when a contact email is provided.

## API Endpoints

- `POST /api/search_paper`
- `POST /api/find_relevant_papers`
- `POST /api/batch_process`
- `GET /api/status`
- `GET /api/health`

Example:

```bash
curl -X POST http://127.0.0.1:5003/api/search_paper \
  -H "Content-Type: application/json" \
  -d '{"title": "Attention Is All You Need"}'
```

## Project Structure

```text
CRUXpider/
├── app.py
├── app_integrated.py
├── CRUXpider.py
├── config.py
├── requirements.txt
├── templates/
└── static/
```

## Publishing Notes

Before pushing to GitHub:

- Keep the repository root at `CRUXpider/`, not your Desktop parent folder.
- Do not commit `venv/`, `build/`, `dist/`, notebooks, local PDFs, test scripts, or CSV outputs.
- Set secrets through environment variables only.
- Choose and add an open source license before making the repo public.

## License

This project is released under the MIT License. See [LICENSE](/Users/anthonyche/Desktop/CRUXpider/LICENSE).

## Basic Test Run

```bash
python -m unittest discover -s tests
```
