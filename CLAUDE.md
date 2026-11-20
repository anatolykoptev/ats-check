# CLAUDE.md

Python 3.13 project run through `uv` (`pyproject.toml`, `uv.lock`); entry `./offersmith` (`./honest-ats` and `./ats-check` are symlinks to it); packaged as a Claude Code plugin (`.claude-plugin/`, `skills/`). Tests: `uv run pytest`; mutation proof: `uv run python tests/mutate.py`.

- Never add a real resume, master or job description to the repository. Fixtures are about the made-up candidate Jane Q. Example; `examples/` holds a synthetic master set, resume and letter.
- A change to matching, scoring gates or the truth column needs a test that fails without it; `tests/mutate.py` lists the call sites that must stay guarded.
- LLM layers go through `llm.py` only (sandbox flags and the canary check live there); tests mock the runner.
- Keep dependencies at current stable versions in `uv.lock`.
- Index of documents: [docs/INDEX.md](docs/INDEX.md).
- Skills reference scripts only through `${CLAUDE_SKILL_DIR}` or `${CLAUDE_PLUGIN_ROOT}`; `tests/test_plugin.py` checks that each referenced path exists and that every shipped script is named by a skill.
- Skill scripts load `ats_check/negation.py` and `ats_check/config.py` by path from the plugin root and need only the standard library under `python3 -I`.
- Check `claude plugin validate .` after editing a manifest or a SKILL.md.
