"""Verdict thresholds, coverage arithmetic and the years gate: the numbers the owner is shown."""
import pytest

from ats_check import fields as fd
from ats_check import jd_reqs as jr
from ats_check import match as m
from ats_check import score

G, _ = jr.load_synonyms()


class H:
    checks: list = []


def verdict(cov, kos=()):
    return score.verdict(H(), cov, list(kos), None)["label"]


@pytest.mark.parametrize("cov,label", [
    ({"required": 80}, "STRONG MATCH"),
    ({"required": 79}, "MODERATE MATCH"),
    ({"required": 60}, "MODERATE MATCH"),
    ({"required": 59}, "WEAK MATCH"),
    ({"required": 0}, "WEAK MATCH"),
    ({"required": None, "overall": 40}, "NO REQUIRED KEYWORDS"),
    ({"required": None, "overall": None}, "NO REQUIREMENTS FOUND"),
    ({"required": 95, "required_median": 50}, "WEAK MATCH"),      # the median over the term lists decides, not one list
])
def test_verdict_thresholds(cov, label):
    assert verdict(cov) == label


def test_a_knockout_risk_outranks_a_strong_match():
    assert verdict({"required": 95}, [{"kind": "degree", "status": "risk", "note": "no degree", "requirement": "x"}]) == "KNOCK-OUT RISK"


@pytest.mark.parametrize("status", ["review", "unknown"])
def test_strong_keywords_do_not_make_a_strong_match_while_the_years_gate_is_open(status):
    ko = {"kind": "years", "status": status, "requirement": "5+ years software development", "note": "cannot tell"}
    assert verdict({"required": 95}, [ko]) == "STRONG KEYWORDS, YEARS GATE TO CHECK"
    assert verdict({"required": 70}, [ko]) == "MODERATE MATCH"                      # only the STRONG label is held back
    assert verdict({"required": 95}, [{**ko, "status": "ok"}]) == "STRONG MATCH"


# ---- coverage counts
RESUME = "Jane Q. Example\nEngineer\nSan Francisco, CA · j@example.com\nEXPERIENCE\nEngineer, Acme  Jan 2022 – Present\n• Built pgvector search.\nSKILLS\nPython, Go, Docker\n"


def results(reqs, master=None):
    from ats_check.master import load
    return list(m.match(jr.JD(requirements=reqs), fd.parse(RESUME), load(master) if master else None, G))


def test_coverage_counts_found_and_achievable():
    from mk import bank
    reqs = [jr.Requirement("pgvector", [], "tool", "required"), jr.Requirement("Terraform", [], "tool", "required")]
    c = m.coverage(results(reqs))
    assert (c["required_found"], c["required_total"]) == (1, 2) and c["required_achievable"] == c["required"]
    c = m.coverage(results(reqs, bank("Led Terraform migrations.")))
    assert c["required_found"] == 1 and c["required_achievable"] > c["required"]     # one true addition


# ---- years gate (audit M4)
YEARS_RESUME = ("Jane Q. Example\nEngineer\nSan Francisco, CA · j@example.com\nEXPERIENCE\n"
                "Engineer, Acme  Jan 2025 – Present\n• Built web applications.\n"
                "Event Producer, Fest  Jan 2009 – Dec 2025\n• Produced festivals and events.\nSKILLS\nPython, Go, Docker\n")


def gate(area, mn=5):
    return m.knockouts(jr.JD(knockouts={"years": [{"min": mn, "area": area}]}), fd.parse(YEARS_RESUME), YEARS_RESUME, None, G)[0]


def test_years_of_an_area_are_not_resolved_from_the_career_span():
    k = gate("software development")
    assert k["status"] == "review" and "cannot tell" in k["note"]      # 2009 events job must not count as software development


def test_years_are_measured_on_the_entries_about_the_area():
    assert gate("events")["status"] == "ok"                            # 2009-2025 entries are about events
    k = gate("web applications")
    assert k["status"] == "risk" and "2025" in k["note"]               # only the 2025 role names it


def test_years_without_an_area_use_the_whole_career_and_stay_a_human_call():
    assert gate("", 5)["status"] == "review" and gate("", 30)["status"] == "risk"


def test_no_dates_means_unknown():
    P = fd.parse("Jane Q. Example\nEngineer\nSan Francisco, CA · j@example.com\nSKILLS\nPython, Go, Docker\n")
    assert m.knockouts(jr.JD(knockouts={"years": [{"min": 5, "area": "x"}]}), P, "", None, G)[0]["status"] == "unknown"


def test_degree_regex_needs_word_boundaries():
    assert jr._knockouts("We build distributed systems. Engineers must own delivery.")["degree"] is None
    assert jr._knockouts("Latency under 100 ms; our teams move fast.")["degree"] is None
    assert jr._knockouts("BS in Computer Science required.")["degree"]["required"] is True


def test_years_come_from_bullets_not_from_a_header_that_names_the_area():
    k = m.knockouts(jr.JD(knockouts={"years": [{"min": 5, "area": "Acme"}]}), fd.parse(YEARS_RESUME), YEARS_RESUME, None, G)[0]
    assert k["status"] == "review"                                     # 'Acme' is only in a role header


def test_a_compound_area_is_a_list_of_alternatives():
    assert gate("quantum physics, events or yoga")["status"] == "ok"   # only 'events' is in a bullet; 2009-2025
