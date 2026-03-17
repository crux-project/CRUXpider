# Public Repo Audit

Audit date: March 17, 2026

## Scope

Tracked files in the public `CRUXpider` repository were reviewed for:

- hard-coded secrets,
- personal passwords,
- stale API tokens,
- local IP addresses,
- local environment artifacts,
- unnecessary large generated files.

## Result

No hard-coded passwords, legacy Papers with Code tokens, local IP addresses, or personal machine-specific runtime artifacts were found in tracked files at the time of this audit.

## Verified

- `.gitignore` excludes local environments, notebooks, CSV outputs, PDFs, and build artifacts.
- Public code paths use environment variables instead of embedded secrets.
- The tracked file set is limited to source code, templates, static assets, tests, and release documents.

## Remaining Operational Risks

- External metadata quality depends on arXiv and OpenAlex.
- GitHub search fallback is not equivalent to a structured paper-to-code database.
- Future contributors could still accidentally commit secrets if local discipline is poor, so secret scanning in GitHub settings is still recommended.

## Recommendation

Safe to keep public, with GitHub secret scanning and Dependabot enabled.
