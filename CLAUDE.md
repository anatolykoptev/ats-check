# CLAUDE.md

Python 3.13 project run through `uv` (`pyproject.toml`, `uv.lock`); entry `./ats-check`. Tests: `uv run pytest`; mutation proof: `uv run python tests/mutate.py`.

- Never add a real resume, master or job description to the repository. Fixtures are about the made-up candidate Jane Q. Example; `examples/` holds a synthetic master and claim guard.
- A change to matching, scoring gates or the truth column needs a test that fails without it; `tests/mutate.py` lists the call sites that must stay guarded.
- LLM layers go through `llm.py` only (sandbox flags and the canary check live there); tests mock the runner.
- Keep dependencies at current stable versions in `uv.lock`.
- Index of documents: [docs/INDEX.md](docs/INDEX.md).
