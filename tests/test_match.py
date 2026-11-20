import pytest

from ats_check import fields as fd
from ats_check import jd_reqs as jr
from ats_check import match as m
from ats_check.master import load as load_master
from mk import bank, guard

RESUME = """Jane Q. Example
Senior AI Platform Engineer
San Francisco, CA · jane@example.com
SUMMARY
Builds agents and Model Context Protocol (MCP) servers.
EXPERIENCE
Senior AI Engineer, Acme  Jan 2022 – Present
• Shipped an MCP server for coding agents.
• Built evaluation sets with pgvector.
Software Engineer, Globex  Mar 2015 – Dec 2017
• Owned a Kubernetes billing service.
SKILLS
Python, Go, Docker, SQL, Terraform
"""
MASTER = bank("Led Terraform migrations for 40 services.", "Wrote SQL reporting for finance teams.", "Salesforce Agentforce pilot with Slack.")
G, _ = jr.load_synonyms()


def run(reqs, master=MASTER, text=RESUME, guard_text=None):
    jd = jr.JD(requirements=reqs)
    P = fd.parse(text)
    return {r.term: r for r in m.match(jd, P, load_master(master, guard_text) if master else None, G)}


def R(term, imp="required", aliases=()):
    return jr.Requirement(term, list(aliases), "skill", imp)


def test_acronym_and_spelled_form_both_present_is_one_mention_and_no_missing_form():
    r = run([R("Model Context Protocol", aliases=["MCP"])])["Model Context Protocol"]
    assert r.status == "ok" and r.forms_missing == []
    assert r.count == 2  # 'Model Context Protocol (MCP)' is ONE mention + the bullet


def test_only_one_form_present_is_reported_as_add_the_other_form():
    text = RESUME.replace("Model Context Protocol (MCP) servers", "MCP servers")
    r = run([R("Model Context Protocol", aliases=["MCP"])], text=text)["Model Context Protocol"]
    assert r.status == "add_form" and r.forms_missing == ["Model Context Protocol"]


def test_acronym_group_from_yaml_matches_even_if_jd_lists_only_the_long_form():
    r = run([R("Kubernetes")])["Kubernetes"]
    assert r.hits and r.best == "older_role"
    text = RESUME.replace("Kubernetes", "K8s")
    r = run([R("Kubernetes")], text=text)["Kubernetes"]
    assert r.hits and r.status == "add_form"


def test_placement_weights_current_role_beats_skills_beats_nothing():
    res = run([R("pgvector"), R("Docker"), R("Rust")])
    assert res["pgvector"].best == "current_role" and res["Docker"].best == "skills"
    assert res["pgvector"].score > res["Docker"].score > res["Rust"].score == 0.0
    assert any("Skills only" in f for f in res["Docker"].flags)


def test_older_role_weighs_less_than_current():
    res = run([R("Kubernetes"), R("evaluation")])
    assert res["Kubernetes"].best == "older_role"
    assert res["evaluation"].score > res["Kubernetes"].score


def test_stuffing_detector_caps_score():
    text = RESUME.replace("• Built evaluation sets with pgvector.", "• Built pgvector search. pgvector indexes. pgvector tuning. pgvector pgvector.")
    r = run([R("pgvector")], text=text)["pgvector"]
    assert r.count > m.STUFF_LIMIT and r.score <= 0.5
    assert any(f.startswith("stuffing") for f in r.flags)


def test_truth_column_add_it_vs_gap():
    res = run([R("Terraform"), R("Agentforce"), R("Tableau")])
    # Terraform is in the resume skills -> ok
    assert res["Terraform"].status == "ok"
    # Agentforce is in the master only -> true, add it
    assert res["Agentforce"].status == "add_it" and res["Agentforce"].master_hit
    # Tableau in neither -> gap, never add
    assert res["Tableau"].status == "gap" and not res["Tableau"].master_hit


def test_truth_column_without_master_never_says_add_it():
    res = run([R("Agentforce")], master=None)
    assert res["Agentforce"].status == "gap"


def test_skills_only_term_with_usage_in_master_is_upgradable():
    r = run([R("Terraform")])["Terraform"]
    assert r.best == "skills" and r.master_usage and r.achievable >= 0.7 > r.score


def test_whole_word_matching_does_not_hit_substrings():
    r = run([R("Go")])["Go"]
    assert r.hits  # skills list has 'Go'
    r = run([R("Go")], text=RESUME.replace("Python, Go,", "Python, Gopher,"))["Go"]
    assert not r.hits


def test_coverage_weights_required_above_preferred():
    res = list(run([R("pgvector", "required"), R("Rust", "preferred")]).values())
    c = m.coverage(res)
    assert c["required"] == 100 and c["overall"] == 60  # 3*1.0 / (3+2)


def test_years_knockout_uses_parsed_dates():
    P = fd.parse(RESUME)
    jd = jr.JD(knockouts={"years": [{"min": 5, "area": "ai"}, {"min": 30, "area": "x"}]})
    ko = m.knockouts(jd, P, RESUME, None, G)
    assert ko[0]["status"] == "review" and ko[1]["status"] == "review"   # no dated entry names these areas: a human call, never the total span


def test_synonym_that_is_not_an_expansion_is_not_a_missing_form():
    # Postgres / PostgreSQL are synonyms but neither abbreviates the other: no 'add the other form' nag
    text = RESUME.replace("Python, Go,", "Python, Postgres, Go,")
    r = run([R("PostgreSQL")], text=text)["PostgreSQL"]
    assert r.hits and r.status == "ok" and r.forms_missing == []


def test_only_forms_the_jd_uses_are_suggested():
    # JD says TypeScript; the resume has it. The 'TS' acronym from the yaml group is NOT a missing form.
    text = RESUME.replace("Python, Go,", "Python, TypeScript, Go,")
    r = run([R("TypeScript")], text=text)["TypeScript"]
    assert r.status == "ok" and r.forms_missing == []


def test_ubiquitous_acronyms_are_never_nagged():
    text = RESUME.replace("Python, Go,", "Python, AWS, Go,")
    r = run([R("AWS", aliases=["Amazon Web Services"])], text=text)["AWS"]
    assert r.status == "ok" and r.forms_missing == []


def test_add_it_carries_the_master_line_as_evidence():
    r = run([R("Agentforce")])["Agentforce"]
    assert r.status == "add_it" and "Agentforce pilot" in r.master_evidence


REAL_MASTER = bank("Built Agentforce agents for Slack.", "Shipped software engineering tooling.", "Reached 1,000 users in the beta.") + "\n## Open questions\n- Does Kubernetes appear anywhere?\n"
GUARD = guard(("7+ years of software engineering", "No engineering employment", "write the real years"),
              ("post-quantum cryptography", "flaw found", "write encrypted calls"),
              ("Example Portal \"350K MAU\"", "never measured", "12,345 clicks"),
              ("Fluent in English", "owner states working proficiency", "English (professional working proficiency)"),
              ("7 GitHub stars", "stars are not traction", "Link the repo"))


def run_ko(reqs, master=REAL_MASTER, years=None, guard_text=GUARD):
    jd = jr.JD(requirements=reqs, knockouts={"years": years or []})
    return {r.term: r for r in m.match(jd, fd.parse(RESUME), load_master(master, guard_text), G)}


def test_rejected_claim_is_flagged_only_when_the_requirement_asserts_that_claim():
    # JD asks "5+ years of software engineering": same claim as the rejected "7+ years of software engineering"
    r = run_ko([R("software engineering")], years=[{"min": 5, "area": "software engineering"}])["software engineering"]
    assert r.status == "rejected" and "7+ years" in r.master_evidence and not r.master_hit


def test_a_term_inside_a_rejected_claim_is_not_rejected_without_the_qualifier():
    # plain "software engineering" (no years ask) must fall through to the normal truth logic
    r = run_ko([R("software engineering")], master=bank("Planned the work."))["software engineering"]
    assert r.status == "gap"
    assert run_ko([R("software engineering")])["software engineering"].status == "add_it"   # a real bullet says it


def test_unqualified_rejected_phrase_rejects_the_same_phrase():
    assert run_ko([R("post-quantum cryptography")])["post-quantum cryptography"].status == "rejected"
    assert run_ko([R("cryptography")])["cryptography"].status == "rejected"  # the phrase minus a modifier is still that claim


def test_a_guard_metric_rejects_the_requirement_that_names_it_and_nothing_else():
    master = bank("Grew Example Portal to 350K MAU in a year.", "Built GitHub tooling.")
    assert run_ko([R("MAU")], master=master)["MAU"].status == "rejected"      # even though a bullet carries the words
    assert run_ko([R("GitHub")], master=master)["GitHub"].status == "add_it"  # '7 GitHub stars' does not reject GitHub


def test_guard_row_whose_write_instead_wording_names_the_term_does_not_reject_it():
    master = bank("Works in English.", skills="English (professional working proficiency)")
    assert run_ko([R("English")], master=master)["English"].status == "add_it"


def test_guard_rows_are_structure_never_evidence():
    # the guard text must not become support: "post-quantum cryptography" is written in it
    r = run_ko([R("Nimbus"), R("encrypted calls")], master=bank("Built things."))
    assert r["Nimbus"].status == "gap" and r["encrypted calls"].status == "gap"


def test_open_questions_are_not_evidence():
    res = run([R("Kubernetes2")], master=REAL_MASTER.replace("Does Kubernetes appear", "Does Kubernetes2 appear"))
    assert res["Kubernetes2"].status == "gap"
    assert run([R("users")], master=REAL_MASTER)["users"].status == "add_it"


def test_master_evidence_is_centred_on_the_match():
    long = bank("filler " * 40 + "built Agentforce pilots " + "tail " * 40)
    r = run([R("Agentforce")], master=long)["Agentforce"]
    assert "Agentforce" in r.master_evidence and len(r.master_evidence) < 200


def test_term_inside_a_hyphenated_name_or_path_is_not_a_match():
    text = RESUME.replace("Python, Go,", "Python, Go, github.com/org/identity-tools, auto-identity-remove,")
    assert not run([R("identity")], text=text)["identity"].hits
    assert run([R("evaluation")], text=RESUME.replace("Python, Go,", "Python, evaluation-driven, Go,"))["evaluation"].hits


def test_soft_skills_are_classified_and_excluded_from_coverage():
    reqs = [R("pgvector", "required"), R("Stakeholder Management", "required"), R("Mentoring", "required"),
            jr.Requirement("Curiosity", [], "soft", "required")]
    res = list(run(reqs, master=None).values())
    assert [r.soft for r in res] == [False, True, True, True]
    c = m.coverage(res)
    assert c["required"] == 100 and c["required_total"] == 1 and c["soft_total"] == 3   # hard-only denominator


def test_numeric_rejected_claim_does_not_reject_the_bare_short_term():
    g = guard(("5+ years Haskell", "not true", "state real years"))
    assert run_ko([R("Haskell")], master=bank("x"), guard_text=g)["Haskell"].status == "gap"
    assert run_ko([R("Haskell")], master=bank("x"), years=[{"min": 5, "area": "Haskell"}], guard_text=g)["Haskell"].status == "rejected"


# ---- matcher precision / recall tables (audit M2, M3)
def hit(term, text, aliases=(), kind="skill"):
    P = fd.parse("Jane Q. Example\nEngineer\nSan Francisco, CA · j@example.com\nSUMMARY\n" + text + "\nSKILLS\nPython\n")
    jd = jr.JD(requirements=[jr.Requirement(term, list(aliases), kind, "required")])
    return m.match(jd, P, None, G)[0]


@pytest.mark.parametrize("term,text", [
    ("Golang", "Led Go-to-Market for a course launch."),
    ("Go", "Go to market fast."),
    ("OpenAI API", "Exposed engines through an OpenAI-compatible API."),
    ("Product Management", "Meetings at 5 PM daily."),
    ("Docker", "Loaded shipping containers at the port."),
    ("Vector Database", "Built retrieval with embeddings."),
    ("Technical Writing", "Kept documentation current."),
    ("Data Pipeline", "Studied data engineering blogs."),
    ("Agentic AI", "Read about agentic commerce trends."),
    ("REST", "Took a rest."),
])
def test_matcher_does_not_find_a_different_thing(term, text):
    assert not hit(term, text).hits


@pytest.mark.parametrize("term,text", [
    ("AI assistants", "Built an AI assistant for clients."),
    ("guardrails", "Added a guardrail for unsafe output."),
    ("agent", "Shipped tool-calling agents."),
    ("company", "Founded two companies."),
    ("Full-Stack Development", "Built full-stack development tooling."),
    ("Search Console", "Used Google Search\nConsole every week."),
])
def test_matcher_finds_plural_singular_and_wrapped_phrases(term, text):
    assert hit(term, text).hits


def test_wrapped_phrase_is_attributed_to_the_line_it_starts_on():
    text = RESUME.replace("• Shipped an MCP server for coding agents.", "• Shipped speech\nmodels for coding agents.")
    r = run([R("speech models")], text=text)["speech models"]
    assert r.hits and r.best == "current_role" and fd.parse(text).lines[r.hits[0].line].startswith("• Shipped speech")


def test_phrases_do_not_match_across_separate_bullets():
    text = RESUME.replace("• Built evaluation sets with pgvector.", "• Built evaluation sets with pgvector.\n• Models for ranking.")
    assert not run([R("pgvector Models")], text=text)["pgvector Models"].hits


def test_short_acronyms_are_not_stuffing_but_long_terms_are():
    r = hit("AI", " ".join(["AI"] * 11))
    assert r.count == 11 and not any(f.startswith("stuffing") for f in r.flags)
    assert any(f.startswith("stuffing") for f in hit("pgvector", "pgvector " * 5).flags)


def test_acronyms_are_case_sensitive_but_prose_is_not():
    assert not hit("REST", "took a rest").hits
    assert hit("REST", "built a REST service").hits
    assert hit("evaluation", "Evaluation sets").hits


# ---- round 2: generic Title-Cased terms vs lowercase master prose; guard precedence
GENERIC = ["Embeddings", "Monitoring", "Guardrails", "Observability", "Webhooks", "Authentication", "Prompting"]


def test_title_cased_generic_terms_match_lowercase_master_prose():
    master = bank("Built 768-dimension pgvector embeddings search with monitoring, guardrails, observability, webhooks, authentication and prompting.")
    res = run([R(t) for t in GENERIC], master=master)
    assert {t: r.status for t, r in res.items()} == {t: "add_it" for t in GENERIC}


def test_a_product_that_is_also_a_common_word_still_needs_its_own_case_whatever_the_kind():
    master = bank("Built dictation: text appears at the cursor.", "Defaulted the admin UI to the french locale.")
    for term in ("Cursor", "French"):
        for kind in ("skill", "tool"):
            assert run([jr.Requirement(term, [], kind, "required")], master=master)[term].status == "gap", (term, kind)
    assert run([R("Cursor")], master=bank("Used Cursor daily."))["Cursor"].status == "add_it"


def test_a_looser_guard_hit_does_not_discard_real_support_but_the_exact_claim_is_rejected():
    master = bank("Built cryptography tooling for key rotation.", "Shipped post-quantum cryptography demos.")
    g = guard(("post-quantum cryptography", "flaw found", "write encrypted calls"))
    res = run_ko([R("cryptography"), R("post-quantum cryptography")], master=master, guard_text=g)
    assert res["cryptography"].status == "add_it" and res["cryptography"].master_hit
    assert res["post-quantum cryptography"].status == "rejected"          # exact claim beats a bullet that says it


def test_write_instead_wording_lets_an_unsupported_term_stay_a_plain_gap():
    g = guard(("Fluent in English", "owner states working proficiency", "English (professional working proficiency)"))
    assert run_ko([R("English")], master=bank("Built things."), guard_text=g)["English"].status == "gap"   # not 'rejected'
