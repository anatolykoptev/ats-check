"""Negation scope in a master line. A master line that denies a term must not count as support for
it (a quiet safety net; the term then simply stays a gap):  "GCP, Azure and Kubernetes not yet",
"Hubspot: no hands-on work yet as of 2026-01-01", "has NOT worked in Hubspot", "Java: none".
Scope is the term's own clause: an item list after a cue, an item list before "not yet", or a
"TERM: none" tail.  A cue governs only items that START with the term, so "never claim Hubspot
CRM" covers Hubspot (and the compound) but not the bare word CRM, and a qualifier such as
"never bare AWS" restricts the wording instead of denying AWS. """
from __future__ import annotations

import re

CUE = re.compile(r"\b(?:not|never|no|none|without|neither|nor|lacks?|avoid|doesn'?t|don'?t|didn'?t|hasn'?t|haven'?t|cannot|can'?t|isn'?t|aren'?t|wasn'?t|weren'?t|zero(?=\s+(?-i:[A-Z])))\b", re.I)
NOT_A_CUE_FOLLOWER = re.compile(r"\s+(?:only|just|merely|to mention|least)\b", re.I)
BOUND = re.compile(r"\.(?=\s|$)|;|:| — | – |\bbut\b|\bhowever\b|\n|$", re.I)
FILLER = re.compile(r"(?:(?:claim|claims|write|writing|use|using|used|list|say|add|put|mention|worked|work|working|have|has|had|having|done|run|ran|built|build|touched|experience|experienced|exposure|with|in|on|at|any|a|an|the|as|of|to|be|been|is|are|was|were|it|ever|yet|production|hands-on|professional|commercial|yet)\s+)*", re.I)
SEP = re.compile(r"\s*(?:,|/|\bor\b|\band\b|\bnor\b)\s*", re.I)
LEAD = re.compile(r"[\s\"'“”‘’`(\[*_]*(?:(?:a|an|the|any)\s+)?[\"'“”‘’`*_]*")
NOT_YET = re.compile(r"\b(?:are |is |have |has |do |does )?(?:not|none|no)\s+yet\b", re.I)
SENT_BOUND = re.compile(r"[;:]|\.(?=\s|$)|\n")
TAIL = re.compile(r"((?:[\w+#.\-/]+\s+){0,2}[\w+#.\-/]+)\s*(?::|=|—|–)\s*(?:none|no|never|not|n/a|zero)\b", re.I)


def analyze(line: str) -> tuple[dict[int, str], list[tuple[int, int]]]:
    """-> ({item_start_offset: item_text} governed by a negation cue, [(start, end)] of 'TERM: none' tails)"""
    starts: dict[int, str] = {}
    for cm in CUE.finditer(line):
        if NOT_A_CUE_FOLLOWER.match(line, cm.end()):
            continue
        a = cm.end()
        end = BOUND.search(line, a).start()
        seg = line[a:end]
        fm = FILLER.match(seg.lstrip())
        base = a + (len(seg) - len(seg.lstrip())) + fm.end()
        pos = base
        rest = line[base:end]
        bounds = [0] + [m.end() for m in SEP.finditer(rest)]
        ends = [m.start() for m in SEP.finditer(rest)] + [len(rest)]
        for b, e in zip(bounds, ends):
            item = rest[b:e]
            lm = LEAD.match(item)
            off = base + b + lm.end()
            text = item[lm.end():].strip()
            if text:
                starts[off] = text
    # "GCP, Azure and Kubernetes not yet": every item of the list in front of the cue
    for ym in NOT_YET.finditer(line):
        cut = max([m.end() for m in SENT_BOUND.finditer(line, 0, ym.start())] or [0])
        seg = line[cut:ym.start()]
        bounds = [0] + [m.end() for m in SEP.finditer(seg)]
        for b in bounds:
            lm = LEAD.match(seg[b:])
            text = seg[b + lm.end():].strip()
            if text and len(text.split()) <= 4:
                starts[cut + b + lm.end()] = text
    tails = [(m.start(1), m.end(1)) for m in TAIL.finditer(line)]
    return starts, tails


_ANALYSIS: dict[str, tuple] = {}


def _analysis(line: str):
    got = _ANALYSIS.get(line)
    if got is None:
        got = _ANALYSIS[line] = analyze(line)
    return got


def is_negated(line: str, a: int) -> bool:
    """Is a term match starting at offset `a` of `line` inside a negated clause?"""
    starts, tails = _analysis(line)
    text = starts.get(a)
    if text is not None and "dependenc" not in " ".join(text.split()[:4]).lower():
        return True
    return any(s <= a < e for s, e in tails)



# Words that may follow the term inside a denied item without making it a different thing:
# "never claim Hubspot CRM" denies Hubspot, "no Kubernetes in production" denies Kubernetes,
# but "events, not website visitors" does not deny "website" (it denies "website visitors").
DENY_REST = {"crm", "platform", "api", "apis", "cloud", "experience", "work", "knowledge", "background", "skills", "skill",
             "development", "engineering", "in", "on", "with", "at", "for", "of", "as", "to", "and", "or", "any", "yet",
             "production", "hands", "commercial", "professional", "beyond", "outside", "ever", "before", "so", "far"}


def denies(line: str, a: int, b: int) -> bool:
    """Does the match at [a, b) of `line` sit in a clause that denies the TERM ITSELF?"""
    starts, tails = _analysis(line)
    if any(s <= a < e for s, e in tails):
        return True
    text = starts.get(a)
    if text is None or "dependenc" in " ".join(text.split()[:4]).lower():
        return False
    rest = re.findall(r"[\w+#.]+", text[b - a:].lower())
    return all(w in DENY_REST or re.fullmatch(r"[\d\-.]+", w) for w in rest)
