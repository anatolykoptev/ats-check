#!/usr/bin/env python3
"""Check a cover letter before it is sent.

Usage: check_letter.py <letter.md> [--min 250] [--max 320] [--master MASTER.md] [--facts FACTS.json]
(--master defaults to `master` in offersmith.toml or $OFFERSMITH_MASTER)
Exit 0 = clean, 1 = findings (one per line), 2 = the check itself cannot run (missing tool or source).

The letter is markdown: YAML frontmatter (name, salutation, closing, pdf, ...) and a body of plain paragraphs.
Beside it: <stem>.facts.json (the fact map), the PDF and <stem>.txt written by render_letter.sh.

What it checks
  words      body word count inside --min..--max
  dashes     no em-dash, no spaced en-dash, no double hyphen
  cliches    none of the kill-list's phrases (docs/kill-list.txt, or $OFFERSMITH_KILL_LIST; text inside double
             quotes is exempt, it is somebody else's wording)
  off-limits no phrase from the claim guard's "Never mention" section; no claim the guard rejects
  fact map   every number in the body (digits, or a number word such as "ten" or "twice") lies inside the
             text of a fact-map entry; every entry is still present in the letter, cites master ids that
             exist or an artifact file that exists; for an entry that cites ids, every digit in it appears in the
             cited master bullets or metric rows (or in its artifact, when it names one as well)
  render     the PDF exists, is one page and is not older than the letter; the .txt exists, is ASCII,
             is not older than the letter and carries every body paragraph

What it cannot check: whether a number backed by an artifact matches that artifact, and whether a sentence
with no number is true. Those entries are listed under "read yourself".

Master ids are loaded with the master-resume skill's own patterns (skills/master-resume/scripts/check_master.py,
imported by path), so the id grammar and the claim-guard parser live in one place.
"""
import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
KILL_LIST = os.environ.get("OFFERSMITH_KILL_LIST") or os.path.join(ROOT, "docs", "kill-list.txt")
CHECK_MASTER = os.path.join(ROOT, "skills", "master-resume", "scripts", "check_master.py")
KILL_FLOOR = 35          # fewer parsed terms than this means the source changed shape
KILL_CANARIES = ("passionate about", "leverage", "i am thrilled to apply", "i look forward to hearing")
NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")
NUM_WORD = re.compile(
    r"\b(?:two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|twenty|thirty|forty|fifty|hundred|"
    r"thousand|million|billion|dozen|twice|doubled?|tripled?|half)\b", re.I)
DASH = re.compile(r"—|\s–\s|(?<=\w)\s?--\s?(?=\w)")
NEVER_HEAD = re.compile(r"^#{1,6}\s*(?:never mention|off-limits)", re.I)


def die(msg: str) -> None:
    print(f"cannot check: {msg}", file=sys.stderr)
    sys.exit(2)


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace(" ", " ")).strip()


def pandoc(md: str, *args: str) -> str:
    try:
        return subprocess.run(["pandoc", md, "-f", "markdown-smart", *args],
                              check=True, capture_output=True, text=True).stdout
    except (OSError, subprocess.CalledProcessError) as e:
        die(f"pandoc failed on {md}: {e}")


def read_letter(md: str):
    tpl = os.path.join(os.path.dirname(os.path.abspath(__file__)), "meta-json.tpl")
    if not os.path.exists(tpl):
        die(f"template missing: {tpl}")
    try:
        meta = json.loads(pandoc(md, "-t", "plain", f"--template={tpl}"))
    except json.JSONDecodeError:
        die(f"frontmatter of {md} is not YAML metadata")
    paras = [norm(p) for p in pandoc(md, "-t", "plain", "--wrap=none").split("\n\n") if norm(p)]
    return meta, paras


def kill_list(path: str) -> list[str]:
    """The kill-list: one phrase per line in docs/kill-list.txt, `#` comments."""
    if not os.path.exists(path):
        die(f"kill-list not found: {path} (set OFFERSMITH_KILL_LIST)")
    terms: list[str] = []
    for raw in open(path, encoding="utf-8").read().splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        t = norm(raw.lower().replace("-", " ").replace("’", "'")).strip(" .,!?:;…")
        if t and t not in terms:
            terms.append(t)
    missing = [c for c in KILL_CANARIES if c not in terms]
    if len(terms) < KILL_FLOOR or missing:
        die(f"kill-list {path} has {len(terms)} terms (floor {KILL_FLOOR}), missing {missing}: "
            "fix the file, do not skip the check")
    return terms


def find_cliches(body: str, terms: list[str]) -> list[str]:
    text = re.sub(r'"[^"]*"|“[^”]*”', " ", body)      # quoted wording belongs to someone else
    text = norm(text.lower().replace("-", " ").replace("’", "'"))
    hits = []
    for t in terms:
        if " " in t:
            pat = rf"(?<![a-z0-9]){re.escape(t)}(?![a-z0-9])"
        else:      # a single word also matches its inflections, including the dropped final e (leverage, leveraging)
            stem = t[:-1] if t.endswith("e") and len(t) > 4 else t
            pat = rf"(?<![a-z0-9]){re.escape(stem)}[a-z]*(?![a-z0-9])"
        if re.search(pat, text):
            hits.append(t)
    return hits


def never_mention(guard_file: str) -> list[str]:
    """Phrases under the claim guard's "Never mention" heading, one per bullet (backticks and quotes stripped)."""
    if not os.path.exists(guard_file):
        return []
    out, on = [], False
    for ln in open(guard_file, encoding="utf-8").read().splitlines():
        if ln.startswith("#"):
            on = bool(NEVER_HEAD.match(ln))
        elif on and re.match(r"\s*[-*]\s+\S", ln):
            p = re.sub(r"^\s*[-*]\s+", "", ln).strip().strip("`\"“”").strip()
            if p:
                out.append(p)
    return out


def load_master(path: str, guard_arg: str = ""):
    if not os.path.exists(CHECK_MASTER):
        die(f"master-resume checker not found: {CHECK_MASTER}")
    spec = importlib.util.spec_from_file_location("check_master", CHECK_MASTER)
    cm = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cm)
    explicit_master = bool(path)
    path = path or cm.default_master()
    if not path:
        die("no master resume: pass --master, or set master in offersmith.toml (or $OFFERSMITH_MASTER)")
    if not os.path.exists(path):
        die(f"master resume not found: {path}")
    ids, in_bank = {}, False
    for line in open(path, encoding="utf-8").read().splitlines():
        if line.startswith("## "):
            in_bank = bool(cm.BANK_HEAD.match(line))
        m = cm.ID_BULLET.match(line) if in_bank else None
        if m:
            ids[m.group(1)] = line
        m = re.match(r"\|\s*(M-\d{2,})\s*\|", line)
        if m:
            ids[m.group(1)] = line
    if not ids:
        die(f"no bullet ids found in {path}")
    folder, base = os.path.split(path)
    stem = base.rsplit(" — ", 1)[0] if " — " in base else ""
    sibling = os.path.join(folder, f"{stem} — claim guard.md")
    guard_file = guard_arg or ("" if explicit_master else cm.default_guard()) or sibling
    if guard_file != sibling and not os.path.exists(guard_file):
        die(f"claim guard not found: {guard_file}")
    return guard_file, ids, cm.guard_phrases(guard_file), never_mention(guard_file)


ID_TOKEN = re.compile(r"\b[A-Z]+(?:-[A-Z]+)?-\d{2,}\b")      # DEV-40, P-EXT-01, M-01: labels, not evidence


def phrase_in(phrase: str, text: str) -> bool:
    """The phrase as a whole, case-insensitive: '6,000+' is not inside '16,000+'."""
    return re.search(r"(?<![\w,.])" + re.escape(phrase) + r"(?!\w)", text, re.I) is not None


def digits(s: str) -> set[str]:
    return {n.replace(",", "").rstrip(".") for n in NUM.findall(ID_TOKEN.sub(" ", s))}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("letter")
    ap.add_argument("--min", type=int, default=250)
    ap.add_argument("--max", type=int, default=320)
    ap.add_argument("--master", default="")
    ap.add_argument("--guard", default="", help="claim guard (default: `guard` in offersmith.toml when the master comes from it, else the sibling file)")
    ap.add_argument("--facts", default="")
    a = ap.parse_args()
    for tool in ("pandoc", "pdfinfo"):
        if not shutil.which(tool):
            die(f"missing tool: {tool}")
    md = os.path.abspath(a.letter)
    if not os.path.exists(md):
        die(f"no such letter: {md}")
    folder, stem = os.path.dirname(md), os.path.splitext(os.path.basename(md))[0]
    raw = open(md, encoding="utf-8").read()
    meta, paras = read_letter(md)
    body = " ".join(paras)
    out, read_yourself = [], []

    # words
    words = len(body.split())
    if not a.min <= words <= a.max:
        out.append(f"body is {words} words, must be {a.min} to {a.max}")

    # dashes (frontmatter included: the header and sign-off are printed too)
    for n, line in enumerate(raw.splitlines(), 1):
        if line.strip() != "---" and DASH.search(line):
            out.append(f"L{n} em-dash or dash used as one: {line.strip()[:70]}")

    # cliches, off-limits wording, claim guard
    for t in find_cliches(body, kill_list(KILL_LIST)):
        out.append(f"cliche from the kill-list: '{t}'")
    guard_file, ids, guard, never = load_master(a.master, a.guard)
    if not os.path.exists(guard_file):
        out.append(f"claim guard not found: {guard_file} (off-limits wording and rejected claims were not checked)")
    # everything printed is checked, not only the body: the header, subject, recipient and sign-off go out too
    printed = " ".join(str(x) for v in meta.values() for x in (v if isinstance(v, list) else [v]) if x is not None)
    seen = body + " " + printed
    for phrase in never:
        if re.search(rf"(?<![A-Za-z0-9]){re.escape(phrase)}(?![A-Za-z0-9])", seen, re.I):
            out.append(f"wording the guard says never to mention: '{phrase}'")
    for phrase in guard:
        if phrase_in(phrase, seen):
            out.append(f"contains a claim the guard rejects: {phrase[:60]}")

    # fact map
    facts_path = a.facts or os.path.join(folder, f"{stem}.facts.json")
    spans = []
    if not os.path.exists(facts_path):
        out.append(f"fact map missing: {facts_path}")
        entries = []
    else:
        try:
            entries = json.load(open(facts_path, encoding="utf-8"))
            assert isinstance(entries, list) and all(isinstance(e, dict) for e in entries)
        except (json.JSONDecodeError, AssertionError):
            out.append(f"fact map is not a JSON list of objects: {facts_path}")
            entries = []
    for k, e in enumerate(entries, 1):
        text = norm(str(e.get("text", "")))
        e_ids, art = e.get("ids") or [], e.get("artifact") or ""
        art_text = ""
        at = body.find(text) if text else -1
        if at < 0:
            out.append(f"fact map entry {k} is not in the letter (edited after mapping?): {text[:60]}")
            continue
        spans.append((at, at + len(text)))
        if not e_ids and not art:
            out.append(f"fact map entry {k} cites no master id and no artifact: {text[:60]}")
        for i in e_ids:
            if i not in ids:
                out.append(f"fact map entry {k}: unknown master id {i}")
        if art:
            art_path = art if os.path.isabs(art) else os.path.join(folder, art)
            if not os.path.exists(art_path):
                out.append(f"fact map entry {k}: artifact not found: {art}")
            else:
                read_yourself.append(f"entry {k} rests on {art}: {text[:70]}")
                if e_ids:      # mixed evidence: a digit may come from the artifact, but it has to be in one of the two
                    art_text = open(art_path, encoding="utf-8", errors="replace").read()
        if e_ids and all(i in ids for i in e_ids):
            have = digits(" ".join(ids[i] for i in e_ids) + " " + art_text)
            for n in sorted(digits(text) - have):
                out.append(f"fact map entry {k}: {n} is not in {', '.join(e_ids)}: {text[:50]}")
    for m in list(NUM.finditer(body)) + list(NUM_WORD.finditer(body)):
        if not any(s <= m.start() and m.end() <= e for s, e in spans):
            ctx = body[max(0, m.start() - 30):m.end() + 30]
            out.append(f"number with no fact-map entry: {m.group(0).rstrip(',.')} in '...{ctx}...'")

    # render: PDF and plain text
    pdf = os.path.join(folder, meta.get("pdf") or f"{stem}.pdf")
    txt = os.path.join(folder, f"{stem}.txt")
    if not os.path.exists(pdf):
        out.append(f"PDF missing: {pdf} (run render_letter.sh)")
    else:
        info = subprocess.run(["pdfinfo", pdf], capture_output=True, text=True).stdout
        m = re.search(r"^Pages:\s+(\d+)", info, re.M)
        pages = int(m.group(1)) if m else 0
        if pages != 1:
            out.append(f"PDF has {pages} pages, must be 1")
        if os.path.getmtime(pdf) < os.path.getmtime(md):
            out.append("PDF is older than the letter: render again")
    if not os.path.exists(txt):
        out.append(f"plain-text version missing: {txt} (run render_letter.sh)")
    else:
        t = open(txt, encoding="utf-8").read()
        bad = sorted({c for c in t if ord(c) > 126})
        if bad:
            out.append(f"plain-text version has non-ASCII characters: {' '.join(repr(c) for c in bad[:8])}")
        if os.path.getmtime(txt) < os.path.getmtime(md):
            out.append("plain-text version is older than the letter: render again")
        flat = norm(t)
        for p in paras:
            if p not in flat:
                out.append(f"plain-text version lacks a paragraph of the letter: {p[:60]}")

    for f in out:
        print(f)
    if read_yourself:
        print("read yourself (the checker cannot compare a number with an artifact):")
        for r in read_yourself:
            print(f"  {r}")
    print(f"{words} body words, {len(entries)} fact-map entries, {len(out)} findings")
    return 1 if out else 0


if __name__ == "__main__":
    sys.exit(main())
