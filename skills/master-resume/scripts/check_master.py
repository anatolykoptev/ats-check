#!/usr/bin/env python3
"""Lint a master resume against the master-resume skill's invariants.

Usage: check_master.py [MASTER.md]   (default: `master` from offersmith.toml or $OFFERSMITH_MASTER)
Exit 0 = clean, 1 = findings, 2 = no master to check. Prints one line per finding.

Absence notes are detected with Offersmith's own negation module (ats_check/negation.py, loaded by path from the
plugin root), so the lint and the truth column share ONE cue list: whatever the ATS check reads as a denial, the
master must not contain.
"""
import importlib.util
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
SIDECARS = ("claim guard", "provenance", "change log", "open questions")
ID = r"[A-Z]+(?:-[A-Z]+)?-\d{2,}"
ID_BULLET = re.compile(rf"^\s*[-*]\s+\*\*({ID})\*\*")
ID_ANY = re.compile(rf"\b({ID})\b")
BANK_HEAD = re.compile(r"## \d+\. (Experience|Projects|Open source)")
# explicit meta-notes that are absence notes in any phrasing (not word cues: those come from negation.py)
META = re.compile(r"\b(?:not claimed|do not claim|never claim|not supported|NEGATED)\b", re.I)
SENT_START = re.compile(r"(?:^|[.;:]\s+)(?=[A-Za-z])")
WORD = re.compile(r"[A-Za-z][A-Za-z0-9+#.]*")


def _load(name: str, rel: str):
    p = os.path.join(ROOT, *rel.split("/"))
    if not os.path.exists(p):
        return None
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod      # dataclasses look their module up here
    spec.loader.exec_module(mod)
    return mod


def load_negation():
    return _load("offersmith_negation", "ats_check/negation.py")


def default_master():
    cfg = _load("offersmith_config", "ats_check/config.py")
    return str(cfg.load().master or "") if cfg else ""


def absence(text: str, neg, full: bool = True) -> bool:
    """Is this line an absence note ('Java: none', 'Has NOT worked in Hubspot', 'No Kubernetes experience')?
    A denied item must NAME something (a Capitalised or CamelCase word that does not merely start the
    sentence, or an ALLCAPS acronym); 'no work lost on rollback' and 'module never used upstream' deny nothing."""
    text = re.sub(rf"^\s*[-*]\s+(?:\*\*{ID}\*\*\s*)?", "", text)
    if META.search(text):
        return True
    starts, tails = neg.analyze(text)
    if tails:
        return True
    if not full:      # prose and tables: only the explicit forms ('X: none', 'not supported'); a quoted PR title or a
        return False  # qualifier like '(events, not site visitors)' is not a note about what he lacks
    sentence_words = {m.end() for m in SENT_START.finditer(text)}
    for off, item in starts.items():
        for m in list(WORD.finditer(item))[:2]:      # the head of the denied item, not the rest of its clause
            tok, pos = m.group(0), off + m.start()
            if (tok.isupper() and len(tok) >= 2) or re.search(r"[a-z][A-Z]", tok):
                return True
            if tok[0].isupper() and pos not in sentence_words:
                return True
    return False


def guard_phrases(path: str) -> list[str]:
    """Quoted claims (else the claim cell) in the 'Claims not supported' table of the sibling claim guard."""
    if not os.path.exists(path):
        return []
    out, on = [], False
    for ln in open(path, encoding="utf-8").read().splitlines():
        if ln.startswith("#"):
            on = bool(re.search(r"claims? not supported", ln, re.I))
            continue
        if on and ln.lstrip().startswith("|") and not re.fullmatch(r"[\s|:\-]+", ln):
            cell = ln.strip().strip("|").split("|")[0].strip()
            if cell.lower() == "claim":
                continue
            q = re.findall(r"[\"“]([^\"”]+)[\"”]", cell)
            out += q or [cell]
    return [p for p in out if len(p) >= 6]


def main(path: str) -> int:
    text = open(path, encoding="utf-8").read()
    lines = text.splitlines()
    out = []
    neg = load_negation()
    if neg is None:
        out.append("cannot find ats_check/negation.py under the plugin root: absence notes cannot be checked")

    # 1. sidecars exist next to the master
    folder, base = os.path.split(path)
    stem = base.rsplit(" — ", 1)[0] if " — " in base else ""
    for s in SIDECARS:
        f = os.path.join(folder, f"{stem} — {s}.md")
        if not os.path.exists(f):
            out.append(f"sidecar missing: {f}")
    guard_file = os.path.join(folder, f"{stem} — claim guard.md")

    # 2. bullets in the bank sections carry a unique id; no absence notes; no em-dash; role codes
    in_bank, in_rules, in_skills_sec, ids, seen, bodies = False, False, False, set(), {}, {}
    block, block_prefixes, block_of_prefix, bank_bullets = "", {}, {}, []
    for n, line in enumerate(lines, 1):
        if line.startswith("## "):
            in_bank = bool(BANK_HEAD.match(line))
            in_rules = line.strip() == "## Rules"
            block = ""
        if line.startswith("### "):
            block = line[4:].strip()
        if line.startswith("## "):
            in_skills_sec = bool(re.match(r"## \d+\. Skills", line))
        if neg and not in_rules:
            bullet = bool(re.match(r"\s*[-*]\s", line))
            if line.lstrip().startswith("|"):
                hit = any(absence(c, neg, full=in_skills_sec) for c in line.strip().strip("|").split("|"))
            else:
                hit = absence(line, neg, full=bullet)
            if hit:
                out.append(f"L{n} absence note: {line[:120]}")
        if not in_bank or not re.match(r"\s*[-*]\s", line):
            continue
        m = ID_BULLET.match(line)
        if not m:
            out.append(f"L{n} bullet without id: {line[:100]}")
            continue
        i = m.group(1)
        if i in seen:
            out.append(f"L{n} duplicate id {i} (first at L{seen[i]})")
        seen[i] = n
        ids.add(i)
        bodies[i] = line
        bank_bullets.append((n, i, block, line))
        if "—" in line:
            out.append(f"L{n} em-dash in bullet {i}")

    # role-code registry: derived from the master's own role blocks. Within one `###` block every bullet shares
    # a code (KPE-.. in the Product Engineer role); one code never spans two blocks.
    by_block: dict[str, list] = {}
    for n, i, blk, _ in bank_bullets:
        by_block.setdefault(blk, []).append((n, i))
    for blk, items in by_block.items():
        pref = [re.sub(r"-\d+$", "", i) for _, i in items]
        top = max(set(pref), key=pref.count)
        for (n, i), p in zip(items, pref):
            if p != top:
                out.append(f"L{n} id {i} does not use its role block's code {top} ('{blk[:40]}')")
        block_of_prefix.setdefault(top, []).append(blk)
    for p, blks in block_of_prefix.items():
        if len(blks) > 1:
            out.append(f"role code {p} is used by {len(blks)} blocks: {'; '.join(b[:30] for b in blks)}")

    # 3. metrics bank: every id token in Home resolves; each value appears in its home bullet; tokens resolve
    metrics = {}
    headings = " ".join(l.lower() for l in lines if l.startswith("#"))
    for n, line in enumerate(lines, 1):
        m = re.match(r"\|\s*(M-\d{2,})\s*\|", line)
        if not m:
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        home, value = cells[-1], cells[1] if len(cells) > 1 else ""
        metrics[m.group(1)] = home
        toks = ID_ANY.findall(home)
        for pfx, lo, hi in re.findall(r"\b([A-Z]+(?:-[A-Z]+)?)-(\d{2,}) to (?:[A-Z]+(?:-[A-Z]+)?)-(\d{2,})\b", home):
            toks += [f"{pfx}-{k:02d}" for k in range(int(lo) + 1, int(hi)) if f"{pfx}-{k:02d}" in ids]   # 'FE-02 to FE-05'
        for t in toks:
            if t not in ids:
                out.append(f"L{n} {m.group(1)} home {t} is not a bullet id")
        if not toks:
            nm = re.fullmatch(r"(.+?) block", home, re.I)
            known = (re.fullmatch(r"Section \d+", home) or re.fullmatch(r"summary of \S+", home)
                     or (nm and nm.group(1).lower() in headings))
            if not known:
                out.append(f"L{n} {m.group(1)} home '{home[:40]}' is neither a bullet id nor a known place")
        else:
            raw_body = " ".join(bodies.get(t, "") for t in toks)
            body = raw_body.replace(",", "")
            if m.group(1) in raw_body:      # the home bullet cites the bank row: the number lives there, once
                continue
            for num in re.findall(r"\d[\d,]*(?:\.\d+)?", value):
                if len(num) == 1:      # a lone digit may be written as a word ('three fixes')
                    continue
                if num.replace(",", "") not in body:
                    out.append(f"L{n} {m.group(1)} value {num} does not appear in its home bullet {', '.join(toks)}")
    for tok in sorted(set(re.findall(r"\{(M-\d{2,})\}", text))):
        if tok not in metrics:
            out.append(f"token {{{tok}}} has no Metrics bank row")

    # 4. every evidence id cited in a keyword bank or the Skills table exists
    in_skills = False
    for n, line in enumerate(lines, 1):
        if line.startswith("## "):
            in_skills = bool(re.match(r"## \d+\. Skills", line))
        if "Keyword bank" in line or (in_skills and line.startswith("|")):
            for ref in ID_ANY.findall(line):
                if not ref.startswith("M-") and ref not in ids:
                    kind = "keyword bank" if "Keyword bank" in line else "Skills evidence"
                    out.append(f"L{n} {kind} cites unknown id {ref}")

    # 5. a claim the guard rejects must not sit in a bank bullet
    for phrase in guard_phrases(guard_file):
        for n, i, _, line in bank_bullets:
            if phrase.lower() in line.lower():
                out.append(f"L{n} bullet {i} contains a claim the guard rejects: {phrase[:60]}")

    for f in out:
        print(f)
    print(f"{len(ids)} bullet ids, {len(metrics)} metrics, {len(out)} findings")
    return 1 if out else 0


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else default_master()
    if not target or not os.path.isfile(target):
        print(f"cannot check: no master resume (pass a path, or set master in offersmith.toml): {target or '(unset)'}",
              file=sys.stderr)
        sys.exit(2)
    sys.exit(main(target))
