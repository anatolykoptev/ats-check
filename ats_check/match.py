"""Layer 3: match requirements against what the machine parsed, with placement weights and a truth column."""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field

from . import fields as fd
from . import negation
from .master import Master, claim_core
from .forms import _is_acronym, is_expansion
from .jd_reqs import IMPORTANCE_W, JD, Requirement, expand_forms

PLACEMENT_W = {"current_role": 1.0, "headline": 0.8, "summary": 0.7, "recent_role": 0.7, "projects": 0.6,
               "older_role": 0.5, "other": 0.5, "skills": 0.4, "education": 0.3}
STUFF_LIMIT = 3


def _last_token_rx(tok: str, whole: str) -> str:
    """Last word of a form with plural<->singular tolerance both ways ('guardrails' ~ 'guardrail',
    'AI assistant' ~ 'AI assistants', 'company' ~ 'companies')."""
    esc = re.escape(tok)
    if len(whole) <= 3 or whole.isupper() or not tok[-1:].isalpha():
        return esc
    low = tok.lower()
    if low.endswith("ies") and len(tok) > 4:
        return re.escape(tok[:-3]) + "(?:y|ies)"
    if low.endswith("y") and len(tok) > 3 and low[-2] not in "aeiou":
        return re.escape(tok[:-1]) + "(?:y|ies)"
    if low.endswith(("sses", "xes", "ches", "shes")):
        return re.escape(tok[:-2]) + "(?:es)?"
    if low.endswith("s") and len(tok) > 3 and not low.endswith(("ss", "us", "is")):
        return re.escape(tok[:-1]) + "s?"
    return esc + "(?:s|es)?"


def form_regex(form: str, proper: bool = False) -> re.Pattern:
    """`proper`: a product / proper noun matched in the MASTER: case-sensitive, and not the head of a
    hyphenated compound modifier ('OpenAI-compatible' is not 'OpenAI')."""
    raw = [p for p in re.split(r"[\s\-–]+", form.strip()) if p]
    parts = [re.escape(p) for p in raw[:-1]] + [_last_token_rx(raw[-1], form)]
    body = r"[\s\-–]*".join(parts)
    core = form[:-1] if form.endswith("s") else form
    case_sensitive = proper or form.isupper() or core.isupper() or len(form) <= 2 or (len(form) <= 3 and form[0].isupper() and form.lower() in {"go", "ml", "ai"})
    guard = r"(?!-[A-Za-z])" if proper else ""
    if form == "Go":   # the language, not 'Go-to-Market' / 'go to market'
        guard += r"(?!-to-|\s+to\s+market)"
    # not inside a hyphenated compound prefix ('auto-identity-remove'), a path or a handle
    return re.compile(rf"(?<![\w/@])(?<!\w-){body}(?![\w]){guard}(?!/\w)", 0 if case_sensitive else re.I)


# Single words that name a product, a language or a place and are ALSO ordinary words in prose
# ('cursor' = a caret, 'French' in a PR title): a lowercase or title-case master mention is not the thing.
KNOWN_PROPER = {"cursor", "windsurf", "copilot", "codex", "devin", "claude", "gemini", "notion", "linear", "figma", "zoom", "teams",
                "french", "german", "spanish", "russian", "chinese", "japanese", "korean", "italian", "portuguese", "arabic", "hindi",
                "greek", "dutch", "polish", "turkish", "ukrainian", "hebrew", "english", "linkedin", "github", "gitlab", "openai",
                "anthropic", "mercury", "slack", "jira", "asana", "hubspot", "stripe", "shopify", "wordpress", "drupal"}


def proper_forms(rq: Requirement, forms: list[str], groups) -> set[str]:
    """Forms matched case-sensitively in the MASTER: products and proper nouns, never a Title-Cased generic word
    ('Embeddings', 'Monitoring', 'Guardrails' must match 'pgvector embeddings' in lowercase prose).
    A form is proper when it has an inner capital, a digit or a symbol (OpenAI, LinkedIn, Next.js, K8s), when the
    requirement is a tool/certification, or when it is a known product/language name. A first form of a synonym group
    is a generic concept spelled the way a recruiter types it, never proper."""
    if rq.kind in ("soft", "domain"):
        return set()
    generic = {g[0].lower() for g in groups if g}
    out = set()
    for f in forms:
        if not re.fullmatch(r"[A-Z][A-Za-z0-9.+#]{2,}", f) or f.isupper() or f.lower() in generic:
            continue
        if re.search(r"[a-z][A-Z]|\d|[.+#]", f) or rq.kind in ("tool", "certification") or f.lower() in KNOWN_PROPER:
            out.add(f)
    return out


@dataclass
class Hit:
    line: int
    form: str
    placement: str


@dataclass
class ReqResult:
    term: str
    aliases: list[str]
    kind: str
    importance: str
    hits: list[Hit] = field(default_factory=list)
    count: int = 0
    placements: list[str] = field(default_factory=list)
    best: str = ""
    score: float = 0.0
    flags: list[str] = field(default_factory=list)
    forms_present: list[str] = field(default_factory=list)
    forms_missing: list[str] = field(default_factory=list)
    master_hit: bool = False
    master_usage: bool = False
    master_evidence: str = ""
    soft: bool = False
    votes: int = 0
    master_negated: str = ""
    status: str = "gap"   # ok | add_it | add_form | gap
    achievable: float = 0.0


def classify_lines(P: fd.Parsed) -> list[str]:
    """Placement label for every cleaned line index."""
    n = len(P.lines)
    lab = ["other"] * n
    for i in range(min(P.profile_end, n)):
        lab[i] = "headline"
    year_now = dt.date.today().year
    for s in P.sections:
        base = {"summary": "summary", "skills": "skills", "education": "education", "projects": "projects"}.get(s.canon, "other")
        for i in range(s.start, min(s.end, n)):
            lab[i] = base
    ex = P.section("experience")
    if ex:
        for k, e in enumerate(P.entries):
            label = "current_role" if k == 0 or e.current else (
                "recent_role" if _end_year(e) >= year_now - 3 else "older_role")
            for i in range(e.first_line, min(e.last_line + 1, n)):
                lab[i] = label
    return lab


def _end_year(e: fd.Entry) -> int:
    m = re.search(r"\d{4}", e.end or "")
    return int(m.group(0)) if m else (dt.date.today().year if e.current else 0)


def find_all(forms: list[str], text: str, proper: frozenset | set = frozenset()) -> list[tuple[int, int, str]]:
    spans = []
    for f in forms:
        for m in form_regex(f, f in proper).finditer(text):
            spans.append((m.start(), m.end(), f))
    spans.sort(key=lambda s: (s[0], -(s[1] - s[0])))
    out, last = [], -1
    for a, b, f in spans:           # drop overlapping matches (alias inside a longer form)
        if a >= last:
            # "Model Context Protocol (MCP)" is ONE mention, not two
            if out and _is_acronym(f) and not _is_acronym(out[-1][2]) and text[out[-1][1]:a].strip() == "(" and text[b:b + 1] == ")":
                last = b
                continue
            out.append((a, b, f))
            last = b
    return out


SOFT_RX = re.compile(r"communicat|collaborat|mentor|stakeholder|continuous learning|learning agility|independen|self-?starter|teamwork|team player|leadership|problem[- ]solving|adaptab|ownership|curiosity|initiative|interpersonal|presentation skills|negotiat|time management|critical thinking|attention to detail|growth mindset|mindset|ambiguity|work ethic|proactive", re.I)


def is_soft(rq: Requirement) -> bool:
    return rq.kind == "soft" or bool(SOFT_RX.search(rq.term))


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def asserts_rejected_claim(rq: Requirement, forms: list[str], claim: str, jd: JD) -> bool:
    """A guard row covers one CLAIM, not every word in it. A years claim ('7+ years of software
    engineering') is asserted only by a requirement whose JD asks for years of that area; a metric
    ('350K MAU') only by the requirement that names it ('MAU'); an unqualified claim
    ('post-quantum cryptography') by a requirement that IS that phrase."""
    if not find_all(forms, claim):
        return False
    if re.search(r"\d", claim):
        if re.search(r"years?", claim, re.I):
            for y in (jd.knockouts or {}).get("years") or []:
                if find_all(forms, str(y.get("area") or "")):
                    return True
            return False
        core = _norm(claim_core(claim))
        return bool(core) and any(_norm(f) == core for f in forms)
    return len(claim.split()) <= len(rq.term.split()) + 2


def guard_hit(rq: Requirement, forms: list[str], master: Master | None, jd: JD) -> tuple[str, bool]:
    """(guard row, exact) this requirement asserts, or ('', False). A row whose own 'write instead' wording
    contains the requirement ('English (professional working proficiency)') allows it. `exact`: the requirement IS
    the guarded claim (same phrase, or a years/metric claim it names); a looser hit ('cryptography' inside
    'post-quantum cryptography') rejects only when the master has no real support for the requirement."""
    for row in (master.guard if master else []):
        if find_all(forms, row.instead):
            continue
        for p in row.phrases:
            if asserts_rejected_claim(rq, forms, p, jd):
                exact = bool(re.search(r"\d", p)) or any(_norm(f) == _norm(p) for f in forms)
                return row.claim, exact
    return "", False


UBIQUITOUS = {"api", "apis", "rest", "aws", "sql", "ux", "ui", "ai", "ml", "ci", "ci/cd", "sdk", "json", "html", "css", "it"}


def snippet(line: str, span: tuple[int, int], width: int = 70) -> str:
    a, b = max(0, span[0] - width), min(len(line), span[1] + width)
    return ("…" if a else "") + line[a:b].strip() + ("…" if b < len(line) else "")


def segments(P: fd.Parsed) -> list[tuple[str, list[tuple[int, int]]]]:
    """Text blocks to match over: a bullet, header or sentence that wraps across PDF lines is joined, so
    'speech\nmodels' matches 'speech models'. -> [(text, [(offset_in_text, line_index)])]."""
    starts = {e.first_line for e in P.entries} | {s.start for s in P.sections} | {s.start - 1 for s in P.sections}
    after_header = {e.first_line + 1 for e in P.entries}
    rows = {i for s in P.sections if s.canon in ("skills", "education") for i in range(s.start, s.end)}   # one row per line
    out: list[tuple[str, list[tuple[int, int]]]] = []
    text, offs = "", []
    for i, line in enumerate(P.lines):
        cont = (bool(offs) and i not in starts and i not in after_header and i not in rows and not fd.is_bullet(line)
                and i >= P.profile_end and not re.search(r"[.;:!?]$", P.lines[i - 1]))
        if cont:
            text += " "
        elif offs:
            out.append((text, offs))
            text, offs = "", []
        offs.append((len(text), i))
        text += line
    if offs:
        out.append((text, offs))
    return out


def _line_at(offs: list[tuple[int, int]], pos: int) -> int:
    line = offs[0][1]
    for o, i in offs:
        if o <= pos:
            line = i
    return line


def match(jd: JD, P: fd.Parsed, master: Master | None, groups) -> list[ReqResult]:
    labels = classify_lines(P)
    support = master.support if master else []
    segs = segments(P)
    out: list[ReqResult] = []
    for rq in jd.requirements:
        forms = expand_forms(rq, groups)
        proper = proper_forms(rq, forms, groups)
        r = ReqResult(rq.term, rq.aliases, rq.kind, rq.importance, soft=is_soft(rq), votes=rq.votes)
        present_forms: dict[str, int] = {}
        for text, offs in segs:
            for a, b, f in find_all(forms, text):
                pl = labels[_line_at(offs, a)]
                r.hits.append(Hit(_line_at(offs, a), f, pl))
                present_forms[f.lower()] = present_forms.get(f.lower(), 0) + 1
        r.count = len(r.hits)
        r.placements = sorted({h.placement for h in r.hits}, key=lambda p: -PLACEMENT_W[p])
        r.forms_present = [f for f in forms if any(form_regex(f).search(t) for t, _ in segs)]
        if r.hits:
            r.best = r.placements[0]
            r.score = round(min(1.0, PLACEMENT_W[r.best] + 0.1 * (len(r.placements) - 1)), 3)
            specific = sum(1 for h in r.hits if len(h.form) > 3)   # 'AI', 'ML', 'UX' are not stuffable keywords
            if specific > STUFF_LIMIT:
                r.flags.append(f"stuffing: '{rq.term}' appears {specific}x (limit {STUFF_LIMIT})")
                r.score = min(r.score, 0.5)
            if set(r.placements) == {"skills"}:
                r.flags.append("listed in Skills only, not used in any role")
            present = set(r.forms_present)
            missing = []
            jd_forms = {x.lower() for x in rq.forms}
            for f in forms:
                # only forms the JD itself uses are worth adding; ubiquitous acronyms (API, AWS, SQL) never need spelling out
                if f in present or f.lower() not in jd_forms or any(x.lower() in UBIQUITOUS for x in present | {f}):
                    continue
                if any(is_expansion(f, g) or is_expansion(g, f) for g in present):
                    missing.append(f)
            uniq: list[str] = []
            for f in missing:   # 'Large Language Model' and '... Models' are one missing form
                if not any(f.lower().rstrip("s") == u.lower().rstrip("s") for u in uniq):
                    uniq.append(f)
            r.forms_missing = uniq[:2]
        # truth column: support only from id bullets and Skills rows (master.load)
        mh, neg_line = [], ""
        for i, sl in enumerate(support):
            l = sl.text
            spans = find_all(forms, l, proper)
            deny = next(((a, b) for a, b, _ in spans if negation.denies(l, a, b)), None)
            if deny and not neg_line:
                neg_line = snippet(l, deny)
            if any(not negation.is_negated(l, a) for a, _, _ in spans):
                mh.append(i)
        r.master_negated = neg_line
        # a line that denies the term itself beats any loose positive mention: no support
        r.master_hit = bool(mh) and not neg_line
        r.master_usage = r.master_hit and any(support[i].kind == "bullet" for i in mh)
        if r.master_hit:
            l0 = support[next((i for i in mh if support[i].kind == "bullet"), mh[0])].text   # quote a bullet before a Skills row
            r.master_evidence = snippet(l0, next((a, b) for a, b, _ in find_all(forms, l0, proper) if not negation.is_negated(l0, a)))
        rej, rej_exact = guard_hit(rq, forms, master, jd)
        if r.hits:
            r.status = "add_form" if r.forms_missing else "ok"
            if neg_line:
                r.flags.append(f"conflict: the resume has a term a master line denies: {neg_line}")
        elif neg_line:
            r.status = "gap"
        elif rej and (rej_exact or not r.master_hit):
            r.status = "rejected"
            r.master_hit, r.master_usage, r.master_evidence = False, False, rej[:140]
        elif r.master_hit:
            r.status = "add_it"
        else:
            r.status = "gap"
        r.achievable = round(r.score if r.hits else (0.7 if r.master_hit else 0.0), 3)
        if r.hits and r.best in ("skills", "education") and r.master_usage:
            r.achievable = max(r.achievable, 0.7)
        out.append(r)
    return out


def coverage(results: list[ReqResult]) -> dict:
    """Hard requirements only (skills, tools, titles, domains, certifications): that is what
    recruiter keyword search runs on. Soft skills are reported separately and carry no weight."""
    hard = [r for r in results if not r.soft]
    soft = [r for r in results if r.soft]

    def cov(sel, attr="score"):
        tot = sum(IMPORTANCE_W[r.importance] for r in sel)
        return round(100 * sum(IMPORTANCE_W[r.importance] * getattr(r, attr) for r in sel) / tot) if tot else None
    req = [r for r in hard if r.importance == "required"]
    evidenced = [r for r in soft if any(h.placement in ("current_role", "recent_role", "older_role") for h in r.hits)]
    return {"overall": cov(hard), "overall_achievable": cov(hard, "achievable"),
            "required": cov(req), "required_achievable": cov(req, "achievable"),
            "found": sum(1 for r in hard if r.hits), "total": len(hard),
            "required_found": sum(1 for r in req if r.hits), "required_total": len(req),
            "soft_total": len(soft), "soft_evidenced": len(evidenced)}


# ------------------------------------------------------------------ knock-outs
def knockouts(jd: JD, P: fd.Parsed, resume_text: str, master: Master | None, groups=()) -> list[dict]:
    master_text = (master.usable_text + "\n" + "\n".join(master.education)) if master else None
    k = jd.knockouts or {}
    out: list[dict] = []
    for y in k.get("years") or []:
        try:
            mn = int(y.get("min", 0))
        except (TypeError, ValueError):
            continue
        out.append(_years_gate(P, mn, str(y.get("area") or ""), groups))
    d = k.get("degree")
    if d and d.get("required"):
        have = bool(P.education)
        inm = bool(master_text and fd.DEGREE.search(master_text))
        out.append({"kind": "degree", "requirement": f"{d.get('level', 'degree')} required",
                    "status": "ok" if have else ("add_it" if inm else "risk"),
                    "note": "degree line parsed" if have else ("degree present in master, absent from resume" if inm else "no degree in resume or master")})
    loc = k.get("location")
    if loc and loc.get("text"):
        city = (P.location.split(",")[0].strip().lower() if P.location else "")
        same = bool(city) and city in (loc["text"] + " " + jd.location).lower()
        out.append({"kind": "location", "requirement": loc["text"][:120], "status": "ok" if same else "review",
                    "note": f"resume location {P.location or 'not parsed'}" + ("" if same else "; check onsite/relocation fit")})
    for key, label in (("clearance", "clearance"), ("work_auth", "work authorization")):
        if k.get(key):
            out.append({"kind": label, "requirement": str(k[key])[:140], "status": "review",
                        "note": "answer truthfully in the application; the resume rarely carries this"})
    for c in k.get("certifications") or []:
        forms = [str(c)]
        hit = bool(find_all(forms, resume_text))
        inm = bool(master_text and find_all(forms, master_text))
        out.append({"kind": "certification", "requirement": str(c), "status": "ok" if hit else ("add_it" if inm else "risk"),
                    "note": "present" if hit else ("in master, add it" if inm else "absent from resume and master")})
    return out


AREA_FILLER = re.compile(r"^(?:(?:professional|relevant|hands-on|progressive|practical|industry|proven|direct|working)\s+)+", re.I)


def _years_gate(P: fd.Parsed, mn: int, area: str, groups) -> dict:
    """'N+ years of <area>' is measured on the entries that are about <area>, never on the career
    span: a 2009 events job is not software-development experience."""
    now = dt.date.today().year
    req = f"{mn}+ years {area}".strip()
    if not any(re.search(r"\d{4}", e.start or "") for e in P.entries):
        return {"kind": "years", "requirement": req, "status": "unknown", "note": "no parseable job dates to compute experience"}
    core = AREA_FILLER.sub("", area.strip())
    if not core:      # 'N+ years of experience' with no area: the whole career counts
        starts = [int(re.search(r"\d{4}", e.start).group(0)) for e in P.entries if re.search(r"\d{4}", e.start or "")]
        span = now - min(starts)
        return {"kind": "years", "requirement": req, "status": "review" if span >= mn else "risk",
                "note": f"career span {span}y {'>=' if span >= mn else '<'} {mn}y" + ("; relevance of the years is a human call" if span >= mn else " required")}
    # 'Solutions Engineering, technical consulting or solution design' is a list of alternatives
    forms: list[str] = []
    for part in re.split(r"\s*,\s*|\s+or\s+", core):
        part = AREA_FILLER.sub("", part.strip())
        forms += [f for f in expand_forms(Requirement(part), groups) if part and f not in forms]
    rows = []
    for e in P.entries:
        text = " ".join(P.lines[e.first_line + 1: e.last_line + 1])   # the bullets, not the header or its dates
        m = re.search(r"\d{4}", e.start or "")
        if m and find_all(forms, text):
            rows.append((int(m.group(0)), _end_year(e), e.title or e.header))
    if not rows:
        return {"kind": "years", "requirement": req, "status": "review",
                "note": f"cannot tell the years of '{core}': no dated entry mentions it; a human call (do not assume the career span)"}
    first, last = min(r[0] for r in rows), max(r[1] for r in rows)
    span = max(0, last - first) if last else now - first
    if span >= mn:
        return {"kind": "years", "requirement": req, "status": "ok", "note": f"entries mentioning '{core}' span {first}-{last or now} ({span}y)"}
    return {"kind": "years", "requirement": req, "status": "risk",
            "note": f"entries mentioning '{core}' span {first}-{last or now} ({span}y) < {mn}y required"}
