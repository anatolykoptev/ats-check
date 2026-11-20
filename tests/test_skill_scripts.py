"""The skill scripts on the synthetic Jane Example set: clean on the example, one finding per seeded defect."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
EX = ROOT / "examples"
CHECK_MASTER = ROOT / "skills/master-resume/scripts/check_master.py"
CHECK_LETTER = ROOT / "skills/cover-letter/scripts/check_letter.py"
RENDER_LETTER = ROOT / "skills/cover-letter/scripts/render_letter.sh"
CHECK_RESUME = ROOT / "skills/tailor-resume/scripts/check_resume.py"
RENDER_RESUME = ROOT / "skills/tailor-resume/scripts/render_resume.sh"
MASTER_NAME = "Jane Example — master resume.md"


def need(*tools):
    """Skip a test locally when a tool is missing; in CI a missing tool is a failure, not a skip."""
    for t in tools:
        if not shutil.which(t):
            if os.environ.get("CI"):
                pytest.fail(f"{t} is required in CI")
            pytest.skip(f"{t} is not installed")


def py(script, *args):
    r = subprocess.run([sys.executable, "-I", str(script), *map(str, args)], capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


@pytest.fixture
def bank(tmp_path):
    for f in EX.glob("Jane Example — *.md"):
        shutil.copy(f, tmp_path / f.name)
    return tmp_path


def edit(path, old, new):
    t = path.read_text(encoding="utf-8")
    assert old in t, f"seed target not found: {old!r}"
    path.write_text(t.replace(old, new, 1), encoding="utf-8")


# ---- master-resume lint

def test_example_master_is_clean():
    rc, out = py(CHECK_MASTER, EX / MASTER_NAME)
    assert rc == 0 and "0 findings" in out, out


@pytest.mark.parametrize("old,new,finding", [
    ("- **KPE-01**", "- Java: no work yet as of 2026-01-01.\n- **KPE-01**", "absence note"),
    ("- **KPE-03** ", "- ", "bullet without id"),
    ("- **KPE-04**", "- **KPE-03**", "duplicate id KPE-03"),
    ("| P-EXT-01 |", "| P-EXT-91 |", "home P-EXT-91 is not a bullet id"),
    ("- **KPE-04** ", "- **KPE-04** — ", "em-dash in bullet KPE-04"),
    ("| Languages | Go, Python, TypeScript | KPE-08 |", "| Languages | Go, Python, TypeScript | KPE-88 |", "unknown id KPE-88"),
    ("| P-EXT-01 |", "| Nowhere |", "neither a bullet id nor a known place"),
    ("- **KPE-04** Built", "- **KPE-04** 350K MAU and post-quantum cryptography. Built", "contains a claim the guard rejects"),
    ("- **KPE-04**", "- **ZZZ-04**", "does not use its role block's code KPE"),
])
def test_lint_catches_each_seeded_defect(bank, old, new, finding):
    edit(bank / MASTER_NAME, old, new)
    rc, out = py(CHECK_MASTER, bank / MASTER_NAME)
    assert rc == 1 and finding in out, out


def test_a_number_that_left_its_home_bullet_is_caught(bank):
    m = bank / MASTER_NAME
    edit(m, "; its pages drew 12,345 Google Search clicks (M-01)", " (no longer cites its number)")
    rc, out = py(CHECK_MASTER, m)
    assert rc == 1 and "value 12,345 does not appear in its home bullet" in out, out


def test_an_edited_bank_value_is_caught_when_the_bullet_does_not_cite_the_row(bank):
    m = bank / MASTER_NAME
    edit(m, " (M-01)", "")
    edit(m, "| M-01 | 12,345 |", "| M-01 | 99,999 |")
    rc, out = py(CHECK_MASTER, m)
    assert rc == 1 and "value 99,999 does not appear in its home bullet" in out, out


def test_lint_catches_a_missing_sidecar(bank):
    (bank / "Jane Example — provenance.md").unlink()
    rc, out = py(CHECK_MASTER, bank / MASTER_NAME)
    assert rc == 1 and "sidecar missing" in out


@pytest.mark.parametrize("fact", ["Built a filter for banned keywords in ad copy.", "Staging cutover not yet done; 58 routes live.",
                                  "Cut errors to zero in Go services."])
def test_true_facts_that_only_look_like_absence_notes_stay_clean(bank, fact):
    edit(bank / MASTER_NAME, "- **KPE-01**", f"- **KPE-12** {fact}\n- **KPE-01**")
    rc, out = py(CHECK_MASTER, bank / MASTER_NAME)
    assert "absence note" not in out, out


def test_lint_reads_the_master_from_the_config(monkeypatch, tmp_path):
    cfg = tmp_path / "offersmith.toml"
    cfg.write_text(f'master = "{EX / MASTER_NAME}"\n', encoding="utf-8")
    monkeypatch.setenv("OFFERSMITH_CONFIG", str(cfg))
    rc, out = py(CHECK_MASTER)
    assert rc == 0 and "0 findings" in out, out


def test_lint_without_a_master_exits_2(monkeypatch):
    monkeypatch.setenv("OFFERSMITH_CONFIG", "")
    rc, out = py(CHECK_MASTER)
    assert rc == 2 and "no master resume" in out


# ---- tailor-resume

def test_example_resume_is_clean_against_the_master():
    rc, out = py(CHECK_RESUME, EX / "resume" / "resume.md", "--master", EX / MASTER_NAME)
    assert rc == 0, out


@pytest.mark.parametrize("old,new,finding", [
    ("- Built a knowledge graph on PostgreSQL and pgvector whose pages drew 12,345 Google Search clicks.",
     "- Built a knowledge graph on PostgreSQL and pgvector whose pages drew 54,321 Google Search clicks.", "54,321 is not in the master"),
    ("- Designed the Go services", "- I designed the Go services", "first person"),
    ("- Designed the Go services", "- Responsible for the Go services", "does not start with an action verb"),
    ("- Contributed a PostgreSQL graph backend upstream, merged.", "- Built it.", "must be 6 to 22"),
    ("BA, Example University, 2018", "BA — Example University, 2018", "em-dash"),
])
def test_resume_check_catches_each_seeded_defect(tmp_path, old, new, finding):
    f = tmp_path / "resume.md"
    shutil.copy(EX / "resume" / "resume.md", f)
    edit(f, old, new)
    rc, out = py(CHECK_RESUME, f, "--master", EX / MASTER_NAME)
    assert rc == 1 and finding in out, out


def test_resume_renders_to_a_pdf_the_ats_check_parses_cleanly(tmp_path):
    need("pandoc", "typst", "jq", "pdfinfo", "pdftotext")
    shutil.copy(EX / "resume" / "resume.md", tmp_path / "resume.md")
    r = subprocess.run([str(RENDER_RESUME), str(tmp_path / "resume.md")], capture_output=True, text=True)
    assert r.returncode == 0 and "pages: 1" in r.stdout, r.stdout + r.stderr
    rc, out = py(CHECK_RESUME, tmp_path / "resume.md", "--master", EX / MASTER_NAME)
    assert rc == 0, out
    from ats_check import cli
    jd = tmp_path / "jd.txt"
    jd.write_text("Engineer\nSan Francisco, CA\n\nMinimum Qualifications\n- Go and PostgreSQL\n", encoding="utf-8")
    assert cli.main(["--resume", str(tmp_path / "Jane_Example_Resume.pdf"), "--jd", str(jd), "--no-llm", "--out", str(tmp_path / "o")]) == 0
    md = (tmp_path / "o" / "report.md").read_text()
    assert "0 FAIL" in md and "FIX PARSING FIRST" not in md


# ---- cover-letter

@pytest.fixture
def letter(tmp_path):
    shutil.copytree(EX / "cover-letter", tmp_path / "l")
    return tmp_path / "l" / "cover-letter.md"


def run_letter(md, bank_dir=None):
    r = subprocess.run([str(RENDER_LETTER), str(md)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return py(CHECK_LETTER, md, "--master", (bank_dir or EX) / MASTER_NAME)


def test_example_letter_renders_to_one_page_and_passes(letter):
    need("pandoc", "typst", "jq", "pdfinfo")
    rc, out = run_letter(letter)
    assert rc == 0 and "0 findings" in out, out
    assert (letter.parent / "cover-letter.txt").read_text().isascii()


def add(md, sentence):
    t = md.read_text(encoding="utf-8").rstrip("\n")
    md.write_text(t + " " + sentence + "\n", encoding="utf-8")


@pytest.mark.parametrize("mutate,finding", [
    (lambda md, fm: edit(md, "a small test, not a ranking study", "a small test — not a ranking study"), "em-dash"),
    (lambda md, fm: edit(md, "Your posting asks", "I am thrilled to apply. Your posting asks"), "cliche from the kill-list: 'i am thrilled to apply'"),
    (lambda md, fm: add(md, "I leveraged Postgres for this."), "cliche from the kill-list: 'leverage'"),
    (lambda md, fm: add(md, "My last campaign reached 48,000 readers."), "number with no fact-map entry: 48,000"),
    (lambda md, fm: add(md, "I ran twelve campaigns."), "number with no fact-map entry: twelve"),
    (lambda md, fm: (edit(md, "12,345", "92,345"), edit(fm, "12,345", "92,345")), "92345 is not in P-EXT-01, M-01"),
    (lambda md, fm: edit(fm, '"KPE-08"', '"KPE-99"'), "unknown master id KPE-99"),
    (lambda md, fm: edit(md, "12,345", "12,346"), "is not in the letter (edited after mapping?)"),
    (lambda md, fm: edit(fm, "audit/results.md", "audit/none.md"), "artifact not found: audit/none.md"),
    (lambda md, fm: fm.unlink(), "fact map missing"),
    (lambda md, fm: add(md, "I am fluent in English."), "contains a claim the guard rejects"),
    (lambda md, fm: add(md, "Nimbus taught me a lot."), "wording the guard says never to mention: 'Nimbus'"),
    (lambda md, fm: add(md, "I do not need a visa."), "wording the guard says never to mention: 'visa'"),
    (lambda md, fm: add(md, "The cafe is a café."), "plain-text version has non-ASCII characters"),
])
def test_letter_check_catches_each_seeded_defect(letter, mutate, finding):
    need("pandoc", "typst", "jq", "pdfinfo")
    mutate(letter, letter.with_name("cover-letter.facts.json"))
    rc, out = run_letter(letter)
    assert rc == 1 and finding in out, out


def test_a_cliche_inside_a_quotation_is_not_a_finding(letter):
    need("pandoc", "typst", "jq", "pdfinfo")
    add(letter, 'Your posting asks for "world-class" content.')
    _, out = run_letter(letter)
    assert "cliche from the kill-list" not in out


def test_short_letter_and_stale_pdf(letter):
    need("pandoc", "typst", "jq", "pdfinfo")
    head, body = letter.read_text(encoding="utf-8").split("---\n", 2)[1:]
    letter.write_text("---\n" + head + "---\n" + body.strip().split("\n\n")[0] + "\n", encoding="utf-8")
    _, out = run_letter(letter)
    assert "words, must be 250 to 320" in out
    t = __import__("time").time() + 60
    os.utime(letter, (t, t))
    _, out = py(CHECK_LETTER, letter, "--master", EX / MASTER_NAME)
    assert "PDF is older than the letter" in out


def test_an_unreadable_kill_list_stops_the_check_instead_of_passing(letter, monkeypatch):
    need("pandoc", "typst", "jq", "pdfinfo")
    run_letter(letter)
    monkeypatch.setenv("OFFERSMITH_KILL_LIST", os.devnull)
    rc, out = py(CHECK_LETTER, letter, "--master", EX / MASTER_NAME)
    assert rc == 2 and "kill-list" in out


def test_letter_check_reads_the_master_from_the_config(letter, monkeypatch, tmp_path):
    need("pandoc", "typst", "jq", "pdfinfo")
    run_letter(letter)
    cfg = tmp_path / "offersmith.toml"
    cfg.write_text(f'master = "{EX / MASTER_NAME}"\n', encoding="utf-8")
    monkeypatch.setenv("OFFERSMITH_CONFIG", str(cfg))
    rc, out = py(CHECK_LETTER, letter)
    assert rc == 0, out
