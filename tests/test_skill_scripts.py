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


# ---- review fixes: each test names the mutation that turns it red

def seed_bullet(bank, line):
    edit(bank / MASTER_NAME, "- **KPE-01**", f"{line}\n- **KPE-01**")


def test_a_metric_cited_by_its_bullet_must_not_be_contradicted_by_the_bank(bank):
    # mutation: check_master `if m.group(1) in raw_body:` branch back to a bare `continue`
    edit(bank / MASTER_NAME, "| M-01 | 12,345 |", "| M-01 | 99,999 |")
    rc, out = py(CHECK_MASTER, bank / MASTER_NAME)
    assert rc == 1 and "is cited by P-EXT-01, which carries 12345, but the bank value is 99,999" in out, out


def test_metrics_not_used_in_the_guard_are_rejected_in_master_bullets(bank):
    # mutation: check_master.guard_phrases regex back to "claims? not supported" only
    seed_bullet(bank, "- **KPE-12** Piloted the engines with 120 devices, 40 calls. `AP`")
    rc, out = py(CHECK_MASTER, bank / MASTER_NAME)
    assert rc == 1 and "contains a claim the guard rejects: 120 devices, 40 calls" in out, out


def test_a_configured_guard_is_the_one_the_master_lint_uses(bank, tmp_path, monkeypatch):
    # mutation: check_master.main ignores `guard` (guard_file back to the sibling path)
    other = tmp_path / "elsewhere"
    other.mkdir()
    (other / "guard.md").write_text("# g\n\n## Claims not supported\n| Claim | Why |\n|---|---|\n| \"knowledge graph\" | test |\n", encoding="utf-8")
    cfg = tmp_path / "offersmith.toml"
    cfg.write_text(f'master = "{bank / MASTER_NAME}"\nguard = "{other / "guard.md"}"\n', encoding="utf-8")
    monkeypatch.setenv("OFFERSMITH_CONFIG", str(cfg))
    rc, out = py(CHECK_MASTER)
    assert rc == 1 and "contains a claim the guard rejects: knowledge graph" in out, out


def test_resume_number_must_be_a_whole_number_of_the_master(tmp_path):
    # mutation: check_resume bank back to the comma-stripped text with `flat not in bank` (substring test)
    f = tmp_path / "resume.md"
    shutil.copy(EX / "resume" / "resume.md", f)
    edit(f, "- Built dictation: hold a key, speak, text appears at the cursor, in Python.", "- Built dictation for 234 customers: hold a key, speak, text appears at the cursor.")
    rc, out = py(CHECK_RESUME, f, "--master", EX / MASTER_NAME)
    assert rc == 1 and "number 234 is not in the master" in out, out


def test_a_quoted_pdf_name_is_still_checked(tmp_path):
    # mutation: check_resume pdfname back to `(\S+)` so the quotes stay in the file name and the stale PDF is never found
    need("pdfinfo")
    f = tmp_path / "resume.md"
    shutil.copy(EX / "resume" / "resume.md", f)
    edit(f, "pdf: Jane_Example_Resume.pdf", 'pdf: "Jane_Example_Resume.pdf"')
    (tmp_path / "Jane_Example_Resume.pdf").write_bytes(b"%PDF-1.4\n")
    t = __import__("time").time() + 60
    os.utime(f, (t, t))
    rc, out = py(CHECK_RESUME, f, "--master", EX / MASTER_NAME)
    assert rc == 1 and "PDF is older than the resume" in out, out


def letter_with_master_line(tmp_path, bank_line, sentence, entry_ids):
    shutil.copytree(EX / "cover-letter", tmp_path / "l")
    for fpath in EX.glob("Jane Example — *.md"):
        shutil.copy(fpath, tmp_path / fpath.name)
    edit(tmp_path / MASTER_NAME, "- **KPE-01**", f"{bank_line}\n- **KPE-01**")
    md = tmp_path / "l" / "cover-letter.md"
    add(md, sentence)
    facts = md.with_name("cover-letter.facts.json")
    edit(facts, "[\n", '[\n {"text": "%s", "ids": %s},\n' % (sentence, entry_ids.replace("'", '"')))
    return md


def test_a_bullet_id_is_not_numeric_evidence(tmp_path):
    # mutation: check_letter.digits() back to NUM.findall(s) without ID_TOKEN.sub
    need("pandoc", "typst", "jq", "pdfinfo")
    md = letter_with_master_line(tmp_path, "- **DEV-40** Built internal tooling. `AP`", "I served 40 customers.", "['DEV-40']")
    rc, out = run_letter(md, tmp_path)
    assert rc == 1 and "40 is not in DEV-40" in out, out


@pytest.mark.parametrize("word", ["leveraging", "orchestrating", "synergized"])
def test_dropped_e_inflections_of_a_kill_list_word_are_caught(letter, word):
    # mutation: check_letter.find_cliches single-word branch back to `{term}[a-z]*` (no dropped-e stem)
    need("pandoc", "typst", "jq", "pdfinfo")
    add(letter, f"I kept {word} Postgres.")
    rc, out = run_letter(letter)
    assert rc == 1 and "cliche from the kill-list" in out, out


def test_the_configured_guard_is_used_by_the_letter_check(letter, tmp_path, monkeypatch):
    # mutation: check_letter.load_master ignores guard_arg / cm.default_guard() (sibling path only)
    need("pandoc", "typst", "jq", "pdfinfo")
    run_letter(letter)
    g = tmp_path / "other-guard.md"
    g.write_text("# g\n\n## Never mention in a letter\n- Example Portal\n", encoding="utf-8")
    rc, out = py(CHECK_LETTER, letter, "--master", EX / MASTER_NAME, "--guard", g)
    assert rc == 1 and "wording the guard says never to mention: 'Example Portal'" in out, out
    rc, out = py(CHECK_LETTER, letter, "--master", EX / MASTER_NAME, "--guard", tmp_path / "missing.md")
    assert rc == 2 and "claim guard not found" in out


def test_never_mention_also_covers_the_printed_header_and_subject(letter):
    # mutation: check_letter `seen = body + " " + printed` back to `body`
    need("pandoc", "typst", "jq", "pdfinfo")
    edit(letter, "subject: Growth Engineer, Search and Answers", "subject: Growth Engineer, Nimbus partnership")
    rc, out = run_letter(letter)
    assert rc == 1 and "wording the guard says never to mention: 'Nimbus'" in out, out


def test_a_prohibited_number_is_not_matched_inside_a_longer_number(bank):
    # mutation: check_master / check_letter phrase_in back to a plain `phrase.lower() in text.lower()` substring test
    seed_bullet(bank, "- **KPE-12** Piloted the engines with 1120 devices, 40 calls. `AP`")
    rc, out = py(CHECK_MASTER, bank / MASTER_NAME)
    assert "contains a claim the guard rejects" not in out, out
