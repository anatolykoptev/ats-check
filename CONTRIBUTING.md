# Contributing

1. Open an issue for anything beyond a small fix.
2. Run `uv run pytest` before pushing (needs `pdftotext` from poppler). CI runs it on `ubuntu-24.04-arm`.
3. Add a test that fails without your change. Use synthetic data only: no real resumes or job descriptions.
4. One logical change per pull request; describe what changed, why, and how it was tested.

Security issues: see [SECURITY.md](SECURITY.md), not a public issue.
