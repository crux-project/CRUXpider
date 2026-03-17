Title: `CRUXpider v0.1.0 - First public open-source release`

Tag: `v0.1.0`

Short summary:

CRUXpider is now publicly available as an open-source academic paper analysis tool built around title-first research workflows. This release ships the cleaned public repository, Flask web app, JSON API, environment-based configuration, route-level tests, and graceful fallback behavior for the now-deprecated legacy Papers with Code API path.

Release body:

# CRUXpider v0.1.0

First public open-source release of CRUXpider.

## Highlights

- Cleaned and published `CRUXpider/` as a standalone open-source repository.
- Unified the main runtime around the Flask application.
- Added environment-based configuration and open-source-safe defaults.
- Added route-level tests for the core API flows.
- Added MIT licensing, publish guidance, and improved project documentation.

## What the project does

- Analyze a paper from its title.
- Retrieve venue metadata and PDF links.
- Discover related papers through OpenAlex.
- Batch-process paper titles from CSV.
- Provide GitHub repository search fallbacks for reproducibility-oriented workflows.

## Important note on Papers with Code

As of March 17, 2026, `paperswithcode.com/api/v1` redirects to Hugging Face Papers, so CRUXpider no longer treats that legacy API as a stable dependency. Instead, this release degrades gracefully and uses GitHub search fallback links rather than failing hard.

## Added

- Main Flask app cleanup and consolidation
- Environment-driven config in `config.py`
- `.env.example` for local setup
- MIT license
- Publish checklist
- Route-level tests
- Public-facing README refresh

## Verified

- Dependencies installed successfully in a clean Python 3.10 environment
- Tests passed with:

```bash
python -m unittest discover -s tests -v
```

## Known limitations

- Repository links are currently search-based fallbacks, not authoritative paper-to-code mappings.
- Metadata quality still depends on arXiv and OpenAlex title matching.
- This release does not yet include packaged binaries or hosted demo infrastructure.
