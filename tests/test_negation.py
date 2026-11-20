"""The master states what is NOT true; the truth column must read that as a prohibition."""
import pytest

from ats_check import fields as fd
from ats_check import jd_reqs as jr
from ats_check import match as m
from ats_check import negation
from ats_check.master import load as load_master
from mk import bank

G, _ = jr.load_synonyms()
RESUME = "Jane Q. Example\nEngineer\nSan Francisco, CA · j@example.com\nSKILLS\nPython, Go, Docker\n"

# phrasings taken from the real master and from the coordinator's review
LANGS = ('- **Languages and platforms:** C++ (audio engine on whisper.cpp), never as a standalone senior skill; Java: none. '
         'Cloud and tools: "Oracle Cloud (OCI), Docker Compose" may go in Skills; OCI is the only cloud he runs production on, '
         'so never write GCP, Azure or Kubernetes. AWS: write it narrowly as "AWS (SES email delivery)", never bare "AWS".')
SF = ('- Uses CRM daily for ad sales and has NOT worked in Salesforce (candidate note): never claim Salesforce CRM.')


def no_support(r):
    """A denying master line is no support: an ordinary gap, never add_it."""
    return r.status == "gap" and not r.master_hit and r.achievable == 0.0


def wrap(text: str) -> str:
    """Each master line becomes an id bullet: absence notes are only seen when they sit in evidence."""
    return bank(*[l.lstrip("- ").strip() for l in text.splitlines() if l.strip()])


def status(term, master, aliases=()):
    jd = jr.JD(requirements=[jr.Requirement(term, list(aliases), "skill", "required")])
    r = m.match(jd, fd.parse(RESUME), load_master(wrap(master)), G)[0]
    return r


@pytest.mark.parametrize("term", ["Java", "GCP", "Azure", "Kubernetes", "Salesforce"])
def test_negated_terms_are_prohibitions_never_support(term):
    r = status(term, LANGS + "\n" + SF)
    assert no_support(r), (term, r.status)


def test_crm_stays_usable_while_salesforce_is_prohibited_in_the_same_sentence():
    assert status("CRM", SF).status == "add_it"
    assert no_support(status("Salesforce", SF))
    assert no_support(status("Salesforce CRM", SF))


def test_negation_beats_a_loose_positive_mention_elsewhere():
    r = status("Kubernetes", "- Deployed Kubernetes clusters for fun.\n" + LANGS)
    assert no_support(r)


def test_terms_before_the_cue_or_qualified_by_it_are_not_negated():
    assert status("OCI", LANGS).status == "add_it"          # precedes "never write GCP..."
    assert status("whisper.cpp", LANGS).status == "add_it"  # not in a negated item
    assert status("AWS", LANGS).status == "add_it"          # 'never bare "AWS"' restricts wording, not the claim
    assert status("C++", LANGS).status == "add_it"          # 'never as a standalone senior skill' is a qualifier


def test_not_only_is_not_a_negation():
    assert status("Rust", "- Not only Rust but Go services in production.").status == "add_it"
    assert status("Elixir", "- Not only Rust and Elixir services in production.").status == "add_it"


def test_resume_that_asserts_a_negated_term_gets_a_removal_fix():
    jd = jr.JD(requirements=[jr.Requirement("Docker", [], "skill", "required")])
    master = load_master(wrap("- Docker: none."))
    r = m.match(jd, fd.parse(RESUME), master, G)[0]
    assert r.hits and any(f.startswith("conflict") for f in r.flags)
    from ats_check import score
    fixes = score.build_fixes(type("H", (), {"checks": []})(), [r], [])
    assert fixes[0]["kind"] == "conflict" and "Confirm" in fixes[0]["action"]


@pytest.mark.parametrize("line,term_at,expect", [
    ("Java: none.", 0, True),
    ("never write GCP, Azure or Kubernetes", 12, True),
    ("never write GCP, Azure or Kubernetes", 17, True),
    ("never write GCP, Azure or Kubernetes", 26, True),
    ("OCI is the only cloud, so never write GCP", 0, False),
])
def test_scope_offsets(line, term_at, expect):
    assert negation.is_negated(line, term_at) is expect


def test_no_x_dependency_is_not_a_claim_negation():
    assert status("AWS", "- no AWS dependency in his own repos, so write it narrowly.").status == "add_it"


DATED = ("- Salesforce: no hands-on work yet as of 2026-01-01 (candidate). Java: no work yet as of 2026-01-01. "
         "As of 2026-11-19 OCI is the only cloud he runs production on; GCP, Azure and Kubernetes not yet.")


@pytest.mark.parametrize("term", ["Salesforce", "Java", "GCP", "Azure", "Kubernetes"])
def test_dated_denials_are_no_support(term):
    assert no_support(status(term, DATED)), term


def test_dated_denials_leave_sibling_terms_usable():
    assert status("OCI", DATED).status == "add_it"


def test_current_master_has_no_denial_lines_so_absent_terms_are_plain_gaps():
    r = status("Salesforce", "- Built things in Go.")
    assert r.status == "gap" and not r.master_negated


def test_report_wording_has_no_ban_vocabulary(tmp_path):
    from pathlib import Path
    from ats_check import cli
    fx = Path(__file__).parent / "fixtures"
    jd = tmp_path / "jd.txt"
    jd.write_text("Engineer\nSF\n\nMinimum Qualifications\n- Salesforce and Kubernetes and Python\n- Haskell\n")
    master = tmp_path / "m.md"
    master.write_text(wrap(DATED) + "\n## Rejected claims\n| \"Haskell wizardry\" | no | none |\n")
    out = tmp_path / "out"
    cli.main(["--resume", str(fx / "clean.pdf"), "--jd", str(jd), "--master", str(master), "--no-llm", "--out", str(out)])
    low = (out / "report.md").read_text().lower()
    for banned in ("negated", "never add", "prohibit", "do not add", "not yet per master", "rejected in master"):
        assert banned not in low, banned
    assert "gap, not added until the master records it" in low


def test_a_denied_longer_phrase_does_not_deny_the_word_it_starts_with():
    # 'not website visitors' denies website VISITORS; a real bullet still supports 'website'
    master = "- Built the website in Astro.\n- Reached 40,000 event attendees (events, not website visitors)."
    assert status("website", master).status == "add_it"


def test_zero_before_a_capitalised_name_is_a_denial_but_zero_as_a_number_is_not():
    assert no_support(status("Salesforce", "- Zero Salesforce work."))
    assert status("Rust", "- Cut errors to zero in Rust services.").status == "add_it"


def test_a_denial_of_a_compound_does_not_deny_its_last_word_when_that_word_is_not_the_item_start():
    # documented: a cue governs items that START with the term; 'Qq CRM' is denied, the bare word CRM is not
    assert status("CRM", "- never claim Qq CRM.").status == "add_it"
