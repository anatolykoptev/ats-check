#!/usr/bin/env python3
"""Mechanical checks for a resume written in the tailor-resume format.

Usage: check_resume.py <resume.md> [--master MASTER.md]
Exit 0 = clean, 1 = findings (one per line), 2 = cannot run.

Checks (the rules a script can decide; the gloss rule and the truth of each claim are yours to read):
  dashes        no em-dash
  first person  no I / my / me / we / our in a bullet
  verb first    every bullet starts with a past-tense action verb (list below; add your own with --verbs)
  length        a bullet is 6 to 22 words
  keyword soup  no line of 4+ comma-separated items without a verb (the Skills section is exempt)
  metric        the first number of a bullet lies within its first 80 characters
  pages         when <resume>.pdf (the `pdf:` frontmatter key) exists: at most 2 pages and not older than the markdown
  master        with --master: every number of 2+ digits in a bullet appears in the master (the bank is the only
                source of numbers; a number it lacks is a fabrication until proven otherwise)
"""
import argparse
import os
import re
import shutil
import subprocess
import sys

VERBS = ("Architected", "Designed", "Built", "Shipped", "Diagnosed", "Measured", "Replaced", "Wrote", "Refactored",
         "Deleted", "Reduced", "Migrated", "Led", "Owned", "Author", "Cut", "Added", "Defined", "Separated",
         "Implemented", "Hardened", "Integrated", "Gated", "Sustained", "Rebuilt", "Contributed", "Exposed", "Ran",
         "Operated", "Scaled", "Instrumented", "Directed", "Launched", "Maintained", "Created", "Developed",
         "Improved", "Increased", "Managed", "Negotiated", "Organized", "Produced", "Taught", "Automated")
NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")
FIRST = re.compile(r"\b(?:I|my|me|we|our)\b")


def frontmatter_and_body(text: str):
    m = re.match(r"---\n(.*?)\n---\n(.*)", text, re.S)
    return (m.group(1), m.group(2)) if m else ("", text)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("resume")
    ap.add_argument("--master", default="")
    ap.add_argument("--verbs", default="", help="extra allowed opening verbs, comma separated")
    a = ap.parse_args()
    if not os.path.isfile(a.resume):
        print(f"cannot check: no such resume: {a.resume}", file=sys.stderr)
        return 2
    text = open(a.resume, encoding="utf-8").read()
    front, body = frontmatter_and_body(text)
    verbs = VERBS + tuple(v.strip() for v in a.verbs.split(",") if v.strip())
    out = []
    section = ""
    bullets = []
    for n, line in enumerate(text.splitlines(), 1):
        if line.startswith("## "):
            section = line[3:].strip().lower()
        if "—" in line:
            out.append(f"L{n} em-dash: {line.strip()[:70]}")
        if line.startswith("- ") and section != "skills":
            bullets.append((n, line[2:].strip()))
        elif section != "skills" and line.count(",") >= 3 and not line.startswith("#") \
                and not re.search(r"\b(?:" + "|".join(verbs) + r")\b", line):
            out.append(f"L{n} keyword soup (4+ items, no verb): {line.strip()[:70]}")
    for n, b in bullets:
        if FIRST.search(b):
            out.append(f"L{n} first person in a bullet: {b[:60]}")
        if not b.startswith(verbs):
            out.append(f"L{n} bullet does not start with an action verb: {b[:60]}")
        w = len(b.split())
        if not 6 <= w <= 22:
            out.append(f"L{n} bullet is {w} words, must be 6 to 22: {b[:50]}")
        m = NUM.search(b)
        if m and m.start() > 80:
            out.append(f"L{n} first number sits past character 80: {b[:50]}")
    if a.master:
        if not os.path.isfile(a.master):
            print(f"cannot check: no such master: {a.master}", file=sys.stderr)
            return 2
        bank = {n.replace(",", "").rstrip(".") for n in NUM.findall(open(a.master, encoding="utf-8").read())}
        for n, b in bullets:
            for num in NUM.findall(b):
                flat = num.replace(",", "").rstrip(".")
                if len(flat) >= 2 and flat not in bank:      # a whole number, not a substring of another
                    out.append(f"L{n} number {num} is not in the master: {b[:50]}")
    pdfname = re.search(r"""^pdf:\s*(?:"([^"]+)"|'([^']+)'|(\S+))\s*$""", front, re.M)
    pdf = os.path.join(os.path.dirname(os.path.abspath(a.resume)),
                       next(g for g in pdfname.groups() if g) if pdfname else os.path.splitext(os.path.basename(a.resume))[0] + ".pdf")
    if os.path.exists(pdf):
        if not shutil.which("pdfinfo"):
            print("cannot check: pdfinfo (poppler) is not installed", file=sys.stderr)
            return 2
        info = subprocess.run(["pdfinfo", pdf], capture_output=True, text=True).stdout
        m = re.search(r"^Pages:\s+(\d+)", info, re.M)
        pages = int(m.group(1)) if m else 0
        if pages > 2:
            out.append(f"PDF has {pages} pages, must be at most 2")
        if os.path.getmtime(pdf) < os.path.getmtime(a.resume):
            out.append("PDF is older than the resume: render again")
    for f in out:
        print(f)
    print(f"{len(bullets)} bullets, {len(out)} findings")
    return 1 if out else 0


if __name__ == "__main__":
    sys.exit(main())
