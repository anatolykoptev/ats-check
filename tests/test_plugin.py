"""The Claude Code plugin packaging: manifests parse, every skill is well-formed, every script a skill names exists."""
import json
import re
import tomllib
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
SKILLS = sorted(p for p in (ROOT / "skills").iterdir() if p.is_dir())
EXPECTED = {"master-resume", "tailor-resume", "cover-letter", "ats-check", "application-answers"}
VAR = re.compile(r"\$\{(CLAUDE_SKILL_DIR|CLAUDE_PLUGIN_ROOT)\}/([\w./-]+)")


def frontmatter(skill: Path) -> dict:
    text = (skill / "SKILL.md").read_text(encoding="utf-8")
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    assert m, f"{skill.name}: SKILL.md has no YAML frontmatter"
    data = yaml.safe_load(m.group(1))
    assert isinstance(data, dict)
    return data


def test_the_shipped_skill_set_is_the_expected_one():
    assert {p.name for p in SKILLS} == EXPECTED


def test_plugin_manifest_is_valid_and_matches_the_project():
    m = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
    proj = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    assert re.fullmatch(r"[a-z][a-z0-9-]*", m["name"]) and m["name"] == proj["name"]
    assert m["version"] == proj["version"], "plugin.json and pyproject.toml disagree on the version"
    assert m["author"]["name"] and m["description"] and m["license"] == "Apache-2.0"
    for k in ("homepage", "repository"):
        assert m[k].startswith("https://github.com/anatolykoptev/offersmith")
    assert not (set(m) & {"skills", "commands", "agents", "hooks", "mcpServers"}), "components come from the default folders"


def test_marketplace_lists_this_plugin_from_the_repo_root():
    mk = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())
    plug = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
    assert mk["name"] and mk["owner"]["name"]
    entry = next(p for p in mk["plugins"] if p["name"] == plug["name"])
    assert entry["source"] == "./"
    assert (ROOT / entry["source"] / ".claude-plugin" / "plugin.json").is_file()


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.name)
def test_skill_frontmatter_is_valid(skill):
    fm = frontmatter(skill)
    assert fm["name"] == skill.name, "the skill name must equal its folder name"
    assert re.fullmatch(r"[a-z][a-z0-9-]{0,63}", fm["name"])
    d = fm["description"]
    assert isinstance(d, str) and 40 <= len(d) <= 1024
    assert "Use when" in d or "Use to" in d or "Use before" in d, "the description must say when to use the skill"


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.name)
def test_every_path_a_skill_references_exists(skill):
    text = (skill / "SKILL.md").read_text(encoding="utf-8")
    refs = VAR.findall(text)
    for var, rel in refs:
        base = skill if var == "CLAUDE_SKILL_DIR" else ROOT
        target = base / rel.rstrip(".")
        assert target.exists(), f"{skill.name} references ${{{var}}}/{rel}, which does not exist"


def test_the_skills_between_them_reference_every_shipped_script():
    referenced = set()
    for skill in SKILLS:
        for var, rel in VAR.findall((skill / "SKILL.md").read_text(encoding="utf-8")):
            referenced.add(((skill if var == "CLAUDE_SKILL_DIR" else ROOT) / rel).resolve())
    for script in (ROOT / "skills").glob("*/scripts/*"):
        if script.suffix in (".py", ".sh"):
            assert script.resolve() in referenced, f"{script.relative_to(ROOT)} ships but no SKILL.md names it"


def test_the_cli_names_and_the_python_scripts_agree():
    scripts = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["scripts"]
    assert set(scripts) == {"offersmith", "honest-ats", "ats-check"} and len(set(scripts.values())) == 1
    for name in scripts:
        assert (ROOT / name).exists(), f"root launcher {name} is missing"
    assert (ROOT / "offersmith").read_text().startswith("#!/usr/bin/env bash")
