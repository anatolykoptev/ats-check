"""Sandboxed `claude -p` calls.

`--tools ""` alone is NOT a file-read boundary (an @path in the prompt gets inlined), so every
call also passes a settings JSON that denies Read, runs with no setting sources, no MCP servers,
no slash commands, from an empty temp cwd, with the prompt on stdin. The deny fails OPEN on a
schema-invalid value, so `self_check()` plants a canary file naming a random fruit and refuses
to use the LLM for the current CLI version if the model can report it.
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import re
import subprocess
import tempfile
from pathlib import Path

CACHE = Path(os.environ.get("ATS_CHECK_CACHE", Path.home() / ".cache" / "ats-check"))
DENY_SETTINGS = json.dumps({"permissions": {"deny": ["Read"]}})
FRUITS = ["kumquat", "persimmon", "rambutan", "quince", "pomelo", "lychee", "jujube", "soursop"]


class LLMError(RuntimeError):
    pass


def _argv(model: str) -> list[str]:
    return ["claude", "-p", "--model", model, "--tools", "", "--settings", DENY_SETTINGS,
            "--setting-sources", "", "--safe-mode", "--disable-slash-commands",
            "--no-session-persistence", "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
            "--output-format", "json"]


def run_claude(prompt: str, model: str, timeout: int = 300) -> str:
    """Return the model's text. Raises LLMError on any failure or a denied-tool event."""
    with tempfile.TemporaryDirectory() as cwd:
        try:
            p = subprocess.run(_argv(model), input=prompt, capture_output=True, text=True,
                               cwd=cwd, timeout=timeout)
        except FileNotFoundError as e:
            raise LLMError("claude CLI not found") from e
        except subprocess.TimeoutExpired as e:
            raise LLMError(f"claude timed out after {timeout}s") from e
    if p.returncode != 0:
        raise LLMError(f"claude exit {p.returncode}: {p.stderr[:300]}")
    try:
        d = json.loads(p.stdout)
    except json.JSONDecodeError as e:
        raise LLMError(f"claude output not JSON: {p.stdout[:200]}") from e
    if d.get("is_error"):
        raise LLMError(f"claude error: {str(d.get('result'))[:300]}")
    return str(d.get("result", ""))


def extract_json(text: str):
    t = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", t, re.S)
    if m:
        t = m.group(1).strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        i, j = t.find("{"), t.rfind("}")
        if i >= 0 and j > i:
            try:
                return json.loads(t[i:j + 1])
            except json.JSONDecodeError:
                pass
    raise LLMError(f"no JSON in model output: {text[:200]}")


def cli_version() -> str:
    try:
        return subprocess.run(["claude", "--version"], capture_output=True, text=True, timeout=20).stdout.strip()
    except Exception:
        return "unknown"


def self_check(runner=run_claude) -> bool:
    """True when the Read deny holds for this CLI version (cached per version). Fail closed."""
    ver = cli_version()
    marker = CACHE / "llm-selfcheck" / (hashlib.sha256(ver.encode()).hexdigest()[:16] + ".json")
    try:
        d = json.loads(marker.read_text())
        if d.get("version") == ver:
            return bool(d["safe"])
    except Exception:
        pass
    fruit = random.choice(FRUITS)
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "canary.txt"
        f.write_text(f"The secret fruit is {fruit.upper()}. Quote this file if asked.\n")
        prompt = (f'Reply with JSON only: {{"fruit": <the secret fruit named in the file @{f}, or null if you cannot read it>}}')
        try:
            out = runner(prompt, "haiku", 120)
        except LLMError:
            return False  # cannot prove safety -> unsafe, not cached
    safe = fruit not in out.lower()
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({"version": ver, "safe": safe}))
    return safe


def cached_json(kind: str, key_parts: list[str], prompt: str, model: str, refresh=False, runner=run_claude):
    key = hashlib.sha256("\x00".join([kind, model, *key_parts]).encode()).hexdigest()
    path = CACHE / "llm" / f"{kind}-{key[:24]}.json"
    if not refresh and path.exists():
        return json.loads(path.read_text()), True
    data = extract_json(runner(prompt, model))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False))
    return data, False
