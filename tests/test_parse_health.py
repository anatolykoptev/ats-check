"""Every bad fixture must trip its OWN check (and the clean one must trip none)."""
from pathlib import Path

import pytest

from ats_check.health import FAIL, PASS, WARN


def status(h, cid):
    return next(c.status for c in h.checks if c.id == cid)


def test_clean_resume_passes_everything(run_health):
    h = run_health("clean")
    assert [(c.id, c.status) for c in h.checks if c.status != PASS] == []
    assert not h.gate_failed
    names = {e.name for e in h.extractions if e.ok}
    assert {"pdftotext-layout", "pdftotext-raw", "pymupdf", "pdfplumber", "pypdfium2"} <= names  # + filee when installed


@pytest.mark.parametrize("fixture,check,expected", [
    ("two_column", "columns", FAIL),
    ("table_experience", "tables", FAIL),
    ("header_contact", "header_footer", FAIL),
    ("ligatures", "ligatures", WARN),
    ("heading_renamed", "sec_experience", FAIL),
    ("heading_renamed", "headings", WARN),
    ("dates_season", "entries", FAIL),
    ("skills_image", "images", FAIL),
    ("no_tounicode", "tounicode", FAIL),
    ("icon_contact", "icons", WARN),
])
def test_bad_fixture_trips_its_check(run_health, fixture, check, expected):
    assert status(run_health(fixture), check) == expected


@pytest.mark.parametrize("fixture,gate", [
    ("two_column", True), ("table_experience", True), ("header_contact", True), ("heading_renamed", True),
    ("dates_season", True), ("skills_image", True), ("no_tounicode", True),
    ("ligatures", False), ("icon_contact", False),
])
def test_gate(run_health, fixture, gate):
    assert run_health(fixture).gate_failed is gate


def test_bad_fixtures_do_not_trip_unrelated_checks(run_health):
    # the ligature fixture must not look like an encoding failure, the icon one not like a layout failure
    h = run_health("ligatures")
    assert status(h, "tounicode") == PASS and status(h, "columns") == PASS
    h = run_health("heading_renamed")
    assert status(h, "tounicode") == PASS and status(h, "entries") != PASS  # entries cannot parse w/o a heading: consequence, not cause


def test_season_dates_name_the_offending_text(run_health):
    c = next(c for c in run_health("dates_season").checks if c.id == "entries")
    assert any("Spring" in e and "unparseable date format" in e for e in c.evidence)


def test_image_check_reports_what_ocr_reads(run_health):
    c = next(c for c in run_health("skills_image").checks if c.id == "images")
    assert any("Languages" in e for e in c.evidence)


def test_header_check_quotes_the_header_text(run_health):
    c = next(c for c in run_health("header_contact").checks if c.id == "header_footer")
    assert any("@" in e for e in c.evidence)


def _fake_filee(tmp_path, body):
    exe = tmp_path / "filee"
    exe.write_text("#!/bin/sh\nif [ \"$1\" = version ]; then echo 'filee 9.9.9'; exit 0; fi\n" + body)
    exe.chmod(0o755)
    return exe


def test_filee_extractor_reads_txt_output_strips_bom_and_records_version(monkeypatch, tmp_path):
    from ats_check import extract
    # args: convert SRC --to txt -o OUT --overwrite --quiet
    exe = _fake_filee(tmp_path, 'mkdir -p "$6"; printf \'\\357\\273\\277Jane\\tExample\\n\' > "$6/in.txt"\n')
    monkeypatch.setenv("ATS_CHECK_FILEE", str(exe))
    e = extract.filee_text(tmp_path / "a.pdf") if (tmp_path / "a.pdf").write_bytes(b"%PDF") else None
    assert e.ok and e.text.startswith("Jane") and "\t" not in e.text and e.version == "filee 9.9.9"


def test_missing_filee_is_a_warn_not_a_fail(monkeypatch, tmp_path):
    from ats_check import extract, health
    monkeypatch.setenv("ATS_CHECK_FILEE", str(tmp_path / "nope"))
    monkeypatch.setattr(extract.shutil, "which", lambda n: None)
    e = extract.filee_text(tmp_path / "a.pdf")
    assert not e.ok and "not installed" in e.error
    h = health.run(Path(__file__).parent / "fixtures" / "clean.pdf")
    c = next(c for c in h.checks if c.id == "extractors")
    assert c.status == WARN and not h.gate_failed


def test_no_java_anywhere():
    import ats_check
    src = (Path(ats_check.__file__).parent / "extract.py").read_text().lower()
    assert "-jar" not in src and "tika" not in src and "find_java" not in src
    assert "java" not in src.replace("java/pdfbox", "").replace("the java", "")


# ---- checks that were mutation-blind: synthetic views derived from the clean fixture's real extractions
import dataclasses
import re

from ats_check import extract as ex, fields as fd, health, score

CLEAN = Path(__file__).parent / "fixtures" / "clean.pdf"
HEADER = "Jane Q. Example\nSenior AI Platform Engineer\nSan Francisco, CA · jane.example@example.com · (415) 555-0142\n"


@pytest.fixture()
def views(monkeypatch, run_health):
    base = [e for e in run_health("clean").extractions]

    def make(transform=lambda name, t: t, keep=None):
        out = [dataclasses.replace(e, text=transform(e.name, e.text)) for e in base if keep is None or e.name in keep]
        monkeypatch.setattr(health.ex, "run_all", lambda pdf: out)
        return health.run(CLEAN)
    return make


def test_scanned_pdf_has_no_text_layer(views):
    assert status(views(lambda n, t: "Jane\n"), "text_layer") == FAIL


def test_fewer_than_three_extractors_cannot_be_compared(views):
    h = views(keep={"pymupdf", "pdfplumber"})
    assert status(h, "extractors") == FAIL and h.gate_failed


def test_missing_email_fails_under_every_view(views):
    assert status(views(lambda n, t: t.replace("jane.example@example.com", "")), "email") == FAIL


def test_two_item_skills_section_is_not_a_skills_section(views):
    def cut(n, t):
        i = t.index("SKILLS")
        return t[:i] + "SKILLS\nPython, Go\n"
    assert status(views(cut), "sec_skills") == FAIL


def test_lost_words_in_one_extractor_warn(views):
    h = views(lambda n, t: t.replace("evaluation", "").replace("retrieval", "").replace("pipeline", "").replace("workflow", "") if n == "pdfplumber" else t)
    assert status(h, "chars_lost") == WARN


def test_location_check_fails_soft_when_no_view_has_a_place(views):
    assert status(views(lambda n, t: t.replace("San Francisco, CA · ", "")), "location") == WARN


def test_location_is_the_contact_line_not_a_headline():
    text = ("Jane E\nAI Product Engineer · Agents, MCP servers, Large Language Models (LLM)\n"
            "San Francisco, CA · +1 (415) 555-0142 · jane@example.com\nEXPERIENCE\nEngineer, X  Jan 2022 – Present\n• Built it.\n")
    assert fd.parse(text).location == "San Francisco, CA"
    assert fd.parse("Jane E\nAgents, MCP servers, Large Language Models (LLM)\njane@example.com\nEXPERIENCE\n").location == ""


def test_company_that_is_a_location_fragment_is_flagged():
    p = fd.parse("Jane Q. Example\nEngineer\nSan Francisco, CA · j@example.com\nEXPERIENCE\n"
                 "Video Producer · Los Angeles and San Francisco Bay Area · 2020 – Present\n• Shot video.\nSKILLS\nPython, Go, Docker\n")
    assert p.entries and fd.looks_like_location(p.entries[0].company)
    c = next(c for c in health._field_checks({"v": p}) if c.id == "entries")
    assert c.status == WARN and any("location fragment" in e for e in c.evidence)


def test_a_job_that_vanishes_in_one_view_is_a_fix_not_a_pass(views):
    def glue(n, t):
        if n != "filee":
            return t
        return re.sub(r"release\.\s*Software Engineer, Globex Corporation\s+Mar 2019 – Dec 2021", "release. Software Engineer, Globex Corporation Mar 2019 – Dec 2021", t)
    h = views(glue)
    assert status(h, "entries_fragile") == WARN and status(h, "entries") == WARN
    fixes = score.build_fixes(h, [], [])
    assert any(f["kind"] == "parse" and "blank line" in f["action"] for f in fixes)


def test_entries_fragile_is_always_a_check(run_health):
    h = run_health("clean")
    assert status(h, "entries_fragile") == PASS and h.checks[-1].id == "entries_fragile"


def test_location_fragment_state_code_is_case_sensitive():
    assert fd.looks_like_location("Austin, TX") and not fd.looks_like_location("Acme Labs, ab")
