# CRUXpider Publish Checklist

## Repository

- Confirm `/Users/anthonyche/Desktop/CRUXpider` is the git root.
- Confirm the remote points to `git@github.com:crux-project/CRUXpider.git`.
- Confirm `.gitignore` excludes local environments, build artifacts, notebooks, CSV outputs, PDFs, and local reports.
- Confirm no API keys, passwords, personal emails, or local IP addresses remain in tracked files.

## Documentation

- Review [README.md](/Users/anthonyche/Desktop/CRUXpider/README.md) for public-facing wording.
- Keep the GitHub description:
  `Academic paper analysis tool powered by arXiv and OpenAlex, with related-paper discovery and code-search fallback for reproducible research.`
- Confirm [LICENSE](/Users/anthonyche/Desktop/CRUXpider/LICENSE) matches the license you want to publish under.
- Add screenshots or demo GIFs later if you want a stronger landing page.

## Functionality

- Install dependencies from `requirements.txt`.
- Set `PYALEX_EMAIL` before real usage.
- Verify `python app.py` starts locally.
- Verify `POST /api/search_paper` returns metadata.
- Verify `POST /api/find_relevant_papers` returns related works.
- Verify `POST /api/batch_process` returns a CSV download.

## Known Limits

- The legacy Papers with Code API is deprecated for this project because `paperswithcode.com/api/v1` redirects to Hugging Face.
- Repository discovery currently falls back to GitHub search instead of a first-party structured Papers with Code API.
- Real metadata quality still depends on arXiv and OpenAlex title matching.

## GitHub Release

- Push `main`.
- Add repository topics such as `flask`, `research-tools`, `arxiv`, `openalex`, `academic-search`, `paper-analysis`.
- Enable Issues.
- Add a short About description and website link if you deploy the app.
- Optionally create `v0.1.0` after the first public push.
