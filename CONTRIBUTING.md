# Contributing to CRUXpider

CRUXpider is an open-source project under the MIT License. Anyone can contribute through issues, discussions, forks, and pull requests.

## Before You Start

- Use Python 3.10 or newer.
- Prefer the local bootstrap script:

```bash
./start.sh
```

- For tests only:

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
./.venv/bin/python -m unittest discover -s tests -v
```

## What We Need Help With

- Better paper resolution and metadata matching
- Smarter related-paper ranking
- Better repository discovery and reproducibility signals
- Frontend UX polish
- Tests, docs, and deployment hardening

## Pull Request Guidelines

- Keep changes focused.
- Add or update tests when behavior changes.
- Document new environment variables in [README.md](/Users/anthonyche/Desktop/CRUXpider/README.md) and [.env.example](/Users/anthonyche/Desktop/CRUXpider/.env.example).
- If you add a new external source, explain its reliability, limits, and fallback behavior.

## Development Notes

- `app.py` is the main Flask entrypoint.
- `cruxpider_engine.py` contains paper resolution, ranking, and source integration logic.
- `tests/` contains the route-level regression tests used in CI.

## Reporting Issues

When opening an issue, include:

- input title or CSV sample
- expected result
- actual result
- stack trace or response payload if available
- Python version and OS
