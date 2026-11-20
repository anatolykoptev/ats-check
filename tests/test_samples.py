"""B1: the term list is a draw. --samples N extracts N times, keeps what recurs and reports the spread.
Also the LLM path through cli.analyze, which every other e2e test skips with --no-llm."""
import json
import shutil
import subprocess
import sys
import types
from pathlib import Path

import pytest

from ats_check import ai, cli, jd_reqs, llm
from mk import bank

G, V = jd_reqs.load_synonyms()
FX = Path(__file__).parent / "fixtures"
JD_TEXT = (FX / "jd.txt").read_text() + "- filler line so the text differs from other tests\n"


def req(term, imp="required", kind="skill", aliases=()):
    return {"term": term, "aliases": list(aliases), "kind": kind, "importance": imp}


FILL = [req(f"filler{i}", "mentioned") for i in range(6)]   # >= 5 requirements per sample; recurs in every sample


def sample(*reqs, years=None):
    return {"title": "Engineer", "location": "SF", "requirements": [*reqs, *FILL], "knockouts": {"years": years or []}}


SAMPLES = [
    sample(req("Python"), req("Go"), req("Kafka", "preferred"), req("Teamwork", "required", "soft"), years=[{"min": 5, "area": "python"}]),
    sample(req("Python", aliases=["Python3"]), req("Go"), req("Kafka", "required"), req("Teamwork", "required", "skill")),
    sample(req("Python"), req("Rust"), req("Kafka", "preferred"), req("Teamwork", "required", "soft")),
    sample(req("Python"), req("Go"), req("Elixir", "required")),
    sample(req("python", aliases=["Python3", "Python 3"]), req("Go", "required"), req("Kafka", "preferred")),
]


class Runner:
    def __init__(self, samples=SAMPLES):
        self.samples, self.calls = samples, []

    def __call__(self, prompt, model, timeout=300):
        self.calls.append(prompt)
        return json.dumps(self.samples[(len(self.calls) - 1) % len(self.samples)])


@pytest.fixture()
def cache(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "CACHE", tmp_path)
    return tmp_path


def test_consensus_keeps_terms_in_at_least_half_of_the_samples(cache):
    r = Runner()
    jd = jd_reqs.extract(JD_TEXT, True, G, V, runner=r, safe=True, samples=5)
    terms = {x.term.lower(): x for x in jd.requirements}
    assert len(r.calls) == 5 and jd.n_samples == 5 and len(jd.samples) == 5      # a distinct draw per sample
    assert "python" in terms and "go" in terms and "kafka" in terms              # 5/5, 4/5, 4/5 (needs ceil(5/2) = 3)
    assert "teamwork" in terms                                                  # 3/5
    assert not {"rust", "elixir"} & set(terms)                                  # 1/5 each: a draw, not a requirement
    assert terms["python"].votes == 5 and terms["go"].votes == 4


def test_consensus_unions_aliases_and_votes_importance_and_softness_by_majority(cache):
    jd = jd_reqs.extract(JD_TEXT, True, G, V, runner=Runner(), safe=True, samples=5)
    t = {x.term.lower(): x for x in jd.requirements}
    assert {"Python3", "Python 3"} <= set(t["python"].aliases)       # union of the aliases the samples emitted
    assert t["kafka"].importance == "preferred"               # 3 preferred vs 1 required
    assert t["go"].importance == "required"
    assert t["teamwork"].kind == "soft"                       # 2 of 3 samples said soft


def test_one_sample_is_the_old_behaviour_and_two_samples_keep_the_union(cache):
    r = Runner()
    jd = jd_reqs.extract(JD_TEXT, True, G, V, runner=r, safe=True, samples=1)
    assert len(r.calls) == 1 and {x.term for x in jd.requirements} >= {"Python", "Kafka"}
    two = jd_reqs.consensus([jd_reqs.from_llm_json(SAMPLES[0], G), jd_reqs.from_llm_json(SAMPLES[2], G)])
    assert {"Go", "Rust"} <= {x["term"] for x in two["requirements"]}      # ceil(2/2) = 1: nothing is dropped


def test_consensus_list_is_persisted_per_jd_and_refresh_regenerates(cache, monkeypatch):
    r = Runner()
    first = jd_reqs.extract(JD_TEXT, True, G, V, runner=r, safe=True, samples=5)
    assert (cache / "jdset").exists() and not first.cached
    r2 = Runner([sample(req("Totally"), req("Different"))])
    again = jd_reqs.extract(JD_TEXT, True, G, V, runner=r2, safe=True, samples=5)
    assert again.cached and not r2.calls and [x.term for x in again.requirements] == [x.term for x in first.requirements]
    fresh = jd_reqs.extract(JD_TEXT, True, G, V, runner=r2, safe=True, samples=5, refresh=True)
    assert len(r2.calls) == 5 and not fresh.cached
    with monkeypatch.context() as mp:     # changed consensus logic must not reuse a list made by the old one
        mp.setattr(jd_reqs, "CONSENSUS_VERSION", "c-next")
        jd_reqs.extract(JD_TEXT, True, G, V, runner=Runner(), safe=True, samples=5)
    assert len(list((cache / "jdset").glob("*c-next*"))) == 1
    shutil.rmtree(cache / "llm")        # the stored list stands on its own, not on the per-sample cache
    r3 = Runner([sample(req("Other"))])
    assert jd_reqs.extract(JD_TEXT, True, G, V, runner=r3, safe=True, samples=5).cached and not r3.calls
    other = jd_reqs.extract(JD_TEXT + "x", True, G, V, runner=Runner(), safe=True, samples=5)   # another JD, another list
    assert not other.cached


def test_too_few_successful_samples_falls_back_loudly(cache):
    def flaky(prompt, model, timeout=300):
        flaky.n += 1
        if flaky.n > 1:
            raise llm.LLMError("rate limited")
        return json.dumps(SAMPLES[0])
    flaky.n = 0
    jd = jd_reqs.extract(JD_TEXT, True, G, V, runner=flaky, safe=True, samples=5)
    assert jd.source == "deterministic" and "extraction samples succeeded" in jd.warnings[0]


def test_oversized_extraction_is_warned_and_capped():
    d = {"requirements": [req(f"t{i}", "mentioned") for i in range(70)] + [req("Must", "required")]}
    jd = jd_reqs.from_llm_json(d, G)
    assert len(jd.requirements) == jd_reqs.MAX_REQUIREMENTS and jd.requirements[0].term == "Must"
    assert "71 requirements" in jd.warnings[0] and "15-45" in jd.warnings[0]
    assert not jd_reqs.from_llm_json({"requirements": [req(f"t{i}") for i in range(45)]}, G).warnings


# ---- CLI wiring: the LLM path that --no-llm e2e tests never execute
AI_JSON = {"grade": "B", "one_line": "ok", "top_reasons": ["a"], "would_move_up": ["b"], "risks": []}


@pytest.fixture()
def fake_claude(cache, monkeypatch):
    """Patch where the default runner is BOUND (llm.run_claude -> llm.subprocess.run); patching llm.run_claude would not
    reach cli.analyze (jd_reqs.extract and ai.screen bind it as a default argument at import) and would call the real claude."""
    calls = {"jd": 0, "ai": 0, "criteria": 0, "grade": 0, "prompts": []}
    order = iter(range(10 ** 6))

    def fake_run(argv, input=None, **kw):
        assert argv[0] == "claude"
        calls["prompts"].append(input)
        if "extract hiring requirements" in input:
            calls["jd"] += 1
            out = SAMPLES[next(order) % len(SAMPLES)]
        elif "screening criteria" in input:
            calls["criteria"] += 1
            out = {"criteria": [{"text": "Python", "level": "basic", "screenable": True}]}
        elif "qualification grader" in input:
            calls["grade"] += 1
            out = {"results": [{"id": "c1", "status": "not_met", "quote": ""}]}
        else:
            calls["ai"] += 1
            out = AI_JSON
        return subprocess.CompletedProcess(argv, 0, stdout=json.dumps({"result": json.dumps(out), "is_error": False}), stderr="")
    # a shim, not llm.subprocess.run: that is the global subprocess module, which the PDF extractors share
    monkeypatch.setattr(llm, "subprocess", types.SimpleNamespace(run=fake_run, TimeoutExpired=subprocess.TimeoutExpired))
    monkeypatch.setattr(llm, "self_check", lambda *a, **k: True)
    return calls


def go(tmp_path, *extra, resume="clean.pdf"):
    jd = tmp_path / "jd.txt"
    jd.write_text(JD_TEXT)
    out = tmp_path / "out"
    rc = cli.main(["--resume", str(FX / resume), "--jd", str(jd), "--out", str(out), *extra])
    assert rc == 0
    return json.loads((out / "report.json").read_text()), (out / "report.md").read_text()


def test_cli_runs_the_llm_extraction_and_the_screener(tmp_path, fake_claude):
    d, md = go(tmp_path)
    assert d["jd"]["source"] == "llm" and d["jd"]["samples"] == 5 and fake_claude["jd"] == 5 and fake_claude["ai"] == 1
    assert d["ai"]["grade"] == "B" and d["verdict"]["ai_grade"] == "B"
    before = dict(fake_claude)
    go(tmp_path)                                   # second run: everything from the cache, nothing re-asked
    assert (fake_claude["jd"], fake_claude["ai"]) == (before["jd"], before["ai"])
    go(tmp_path, "--refresh")                      # --refresh must reach the extractor AND the screener
    assert fake_claude["jd"] == before["jd"] + 5 and fake_claude["ai"] == before["ai"] + 1


def test_cli_reports_the_median_and_the_range_of_required_coverage(tmp_path, fake_claude):
    d, md = go(tmp_path, "--samples", "5")
    c = d["coverage"]
    assert len(c["required_samples"]) == 5 and c["samples"] == 5
    assert c["required_range"] == [min(c["required_samples"]), max(c["required_samples"])]
    lo, hi = c["required_range"]
    assert c["required_median"] == round(sorted(c["required_samples"])[2])
    assert f"{c['required_median']}% median (range {lo}-{hi}% over 5 extracted term lists" in md
    assert "true additions are made (not a ceiling)" in md and "up to" not in md.split("## Top fixes")[0]


def test_report_prices_the_true_additions_not_the_current_coverage(tmp_path, fake_claude, monkeypatch):
    monkeypatch.setattr(sys.modules[__name__], "SAMPLES", [sample(req("Python"), req("Kafka"))])
    master = tmp_path / "m.md"
    master.write_text(bank("Led Kafka migrations for 40 services."))
    d, md = go(tmp_path, "--master", str(master))
    c = d["coverage"]
    assert c["required_achievable"] > c["required"]
    assert f"{c['required_achievable']}% if the listed true additions are made" in md


def test_no_llm_ignores_samples(tmp_path, fake_claude):
    d, md = go(tmp_path, "--no-llm", "--samples", "5")
    assert d["jd"]["source"] == "deterministic" and fake_claude["jd"] == 0 and "required_range" not in d["coverage"]


def test_the_screener_prompt_carries_both_texts(cache):
    seen = []

    def runner(prompt, model, timeout=300):
        seen.append(prompt)
        return json.dumps(AI_JSON)
    out = ai.screen("UNIQUE_JD_TOKEN", "UNIQUE_RESUME_TOKEN", runner=runner, safe=True)
    assert out["grade"] == "B" and "UNIQUE_RESUME_TOKEN" in seen[0] and "UNIQUE_JD_TOKEN" in seen[0]
