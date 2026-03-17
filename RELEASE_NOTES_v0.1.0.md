# CRUXpider v0.1.0

First public open-source release of CRUXpider.

## Highlights

- Introduced a clean public repository structure for `CRUXpider/`.
- Unified the main application entrypoint around the Flask app.
- Added environment-based configuration for open-source-safe deployment.
- Added route-level tests for the main API flows.
- Added an MIT license and publish checklist.

## What CRUXpider Does

- Analyze a paper from its title.
- Retrieve venue metadata and PDF links.
- Discover related papers via OpenAlex.
- Batch-process paper titles from CSV.
- Provide GitHub repository search fallbacks for reproducibility workflows.

## Important Change

The legacy Papers with Code API is no longer treated as a stable dependency for this project. As of March 17, 2026, `paperswithcode.com/api/v1` redirects to Hugging Face Papers, so CRUXpider now degrades gracefully and uses GitHub search fallback links instead of failing hard.

## Added

- Main Flask app cleanup and consolidation.
- Environment-driven config in `config.py`.
- `.env.example` for local setup.
- `MIT` license.
- `PUBLISH_CHECKLIST.md`.
- `tests/test_app_routes.py`.

## Changed

- Removed hard-coded secrets from the public code path.
- Standardized runtime defaults around port `5003`.
- Updated dependency pinning for stable installation.
- Reworked README for public open-source presentation.

## Verified

- Dependencies installed successfully in a clean Python 3.10 environment.
- Route-level tests passed:
  `python -m unittest discover -s tests -v`

## Known Limitations

- Repository links are currently search-based fallbacks, not authoritative paper-to-code mappings.
- Metadata completeness depends on arXiv and OpenAlex match quality.
- No packaged release binaries yet.

## Upgrade Notes

If you were using older local versions of this project:

- Start the app with `python app.py`.
- Set configuration through environment variables.
- Do not rely on the old Papers with Code API workflow.
