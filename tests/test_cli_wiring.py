"""cli.analyze plumbing that no unit test sees: master warnings, synonym groups, knock-outs into fixes."""
import json
from pathlib import Path

from ats_check import cli, jd_reqs as jr
from mk import bank

FX = Path(__file__).parent / "fixtures"


def run(tmp_path, reqs=(), knockouts=None, master=None):
    argv = ["--resume", str(FX / "clean.pdf"), "--jd", str(FX / "jd.txt"), "--no-llm", "--out", str(tmp_path / "out")]
    if master:
        mp = tmp_path / "Solo — master resume.md"       # no sibling guard next to it
        mp.write_text(master)
        argv += ["--master", str(mp)]
    orig = cli.jd_reqs.extract
    cli.jd_reqs.extract = lambda *a, **k: jr.JD(requirements=list(reqs), knockouts=knockouts or {})
    try:
        assert cli.main(argv) == 0
    finally:
        cli.jd_reqs.extract = orig
    return json.loads((tmp_path / "out" / "report.json").read_text()), (tmp_path / "out" / "report.md").read_text()


def test_a_master_without_a_sibling_guard_warns_in_the_report(tmp_path):
    d, md = run(tmp_path, master=bank("Built things."))
    assert any("no claim guard" in w for w in d["jd"]["warnings"]) and "no claim guard" in md


def test_synonym_groups_reach_the_years_gate(tmp_path):
    # the resume says 'MCP server' in a 2022-Present role; the JD asks for 3+ years of 'Model Context Protocol'
    d, _ = run(tmp_path, knockouts={"years": [{"min": 3, "area": "Model Context Protocol"}]})
    assert d["knockouts"][0]["status"] == "ok"


def test_knockouts_reach_the_fix_list(tmp_path):
    d, _ = run(tmp_path, knockouts={"years": [{"min": 30, "area": ""}]})
    assert d["knockouts"][0]["status"] == "risk" and any(f["kind"] == "knockout" for f in d["fixes"])


def test_workday_req_without_a_base_is_a_usage_error(monkeypatch, capsys):
    monkeypatch.delenv("ATS_CHECK_WORKDAY_BASE", raising=False)
    argv = ["--resume", str(FX / "clean.pdf"), "--workday-req", "JR1", "--no-llm"]
    try:
        cli.main(argv)
        raise AssertionError("expected SystemExit")
    except SystemExit as e:
        assert e.code == 2
    assert "--workday-base" in capsys.readouterr().err
