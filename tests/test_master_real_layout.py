"""The truth column against the example master layout (master + sibling claim guard), not a hand-written string.
Hazard lines are in the fixture on purpose: Rules, keyword banks, PR-title tables, headers and the guard's own text
must never become evidence."""
from pathlib import Path

import pytest

from ats_check import cli, fields as fd, jd_reqs as jr, match as m, master as mm

LAYOUT = Path(__file__).parent / "fixtures" / "real_layout"
MASTER = LAYOUT / "Jane Example — master resume.md"
FX = Path(__file__).parent / "fixtures"
G, _ = jr.load_synonyms()


def analyze(reqs, years=None, extra=()):
    """cli.analyze on the real layout; the guard is found next to the master by name (no --guard)."""
    args = cli.build_parser().parse_args(["--resume", str(FX / "clean.pdf"), "--jd", str(FX / "jd.txt"), "--master", str(MASTER), "--no-llm", *extra])
    orig = cli.jd_reqs.extract
    cli.jd_reqs.extract = lambda *a, **k: jr.JD(requirements=reqs, knockouts={"years": years or []})
    try:
        d = cli.analyze(args)
    finally:
        cli.jd_reqs.extract = orig
    return {r["term"]: r for r in d["requirements"]}, d


BARE = "Jane Q. Example\nEngineer\nSan Francisco, CA · j@example.com\nSKILLS\nPython, Go, Docker\n"


def direct(reqs, years=None):
    """Matcher on a resume that mentions none of the terms; master and guard loaded as the CLI does."""
    jd = jr.JD(requirements=reqs, knockouts={"years": years or []})
    return {r.term: r for r in m.match(jd, fd.parse(BARE), mm.load_files(MASTER), G)}


def R(term, kind="skill", imp="required"):
    return jr.Requirement(term, [], kind, imp)


def test_the_claim_guard_next_to_the_master_is_loaded_and_rejects(tmp_path):
    res, d = analyze([R("software engineering"), R("post-quantum cryptography"), R("Nimbus"), R("MAU")],
                     years=[{"min": 5, "area": "software engineering"}])
    assert res["software engineering"]["status"] == "rejected"
    assert res["post-quantum cryptography"]["status"] == "rejected"
    assert res["MAU"]["status"] == "rejected"
    assert all(r["status"] != "add_it" for r in res.values())
    assert not any("no claim guard" in w for w in d["jd"]["warnings"])


def test_missing_guard_is_a_loud_warning(tmp_path):
    only = tmp_path / "Solo — master resume.md"
    only.write_text(MASTER.read_text())
    m_ = mm.load_files(only)
    assert any("no claim guard" in w for w in m_.warnings)


@pytest.mark.parametrize("term,kind", [
    ("Cursor", "tool"),          # 'text appears at the cursor' (a caret) and Rule 3
    ("Communication", "skill"),  # 'real-time communications' in Rule 3
    ("French", "skill"),         # a PR title: 'default the admin UI to English instead of French'
    ("LinkedIn", "tool"),        # the header
    ("Head of Marketing", "title"),
    ("B2B", "skill"),            # 'B2B contractor' in the header
    ("CSS", "skill"), ("Unicode", "skill"), ("Cyrillic", "skill"),   # keyword bank
    ("OpenAI", "tool"), ("OpenAI API", "tool"),                      # 'OpenAI-compatible API'
    ("autonomous agents", "skill"),                                 # keyword bank only
    ("group calls", "skill"),                                       # a wording rule that FORBIDS the claim
    ("Nimbus", "tool"),                                           # wording rule
])
def test_words_outside_evidence_are_never_add_it(term, kind):
    r = direct([R(term, kind)])[term]
    assert r.status in ("gap", "rejected"), (term, r.status, r.master_evidence)


@pytest.mark.parametrize("term,kind,ev", [
    ("AI agents", "skill", "AI agents through an MCP"),            # an id bullet
    ("MCP", "skill", "MCP server"),
    ("pgvector", "tool", "pgvector"),
    ("English", "skill", "English (professional working proficiency)"),   # the guard's own write-instead wording; Skills row
])
def test_id_bullets_and_skills_rows_still_support(term, kind, ev):
    r = direct([R(term, kind)])[term]
    assert r.status == "add_it" and ev in r.master_evidence, (term, r.status, r.master_evidence)


def test_support_is_exactly_id_bullets_and_skills_rows():
    mm_ = mm.load_files(MASTER)
    assert {l.kind for l in mm_.support} == {"bullet", "skills"}
    assert all(("agentic AI" not in l.text and "B2B" not in l.text and "Head of Marketing" not in l.text and "French" not in l.text) for l in mm_.support)
    assert len(mm_.guard) == 5 and mm_.guard[0].phrases[:2] == ["350K MAU", "350k visitors a month"]
