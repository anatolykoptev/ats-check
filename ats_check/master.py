"""Master resume markdown -> what may be claimed. The truth column is only as honest as this split.

Support comes ONLY from structure the candidate wrote to be quoted:
  (a) id-carrying bullets `- **KPE-01** ...` under the Experience / Projects / Open source sections,
  (b) the "Allowed wording" cells of the Skills table.
Rules, variant keyword banks, cut procedures, tables of PR titles, headers and prose notes are
never evidence (a requirement word found there is a coincidence, not a fact the candidate can claim).

The claim guard (`<stem> — claim guard.md`, or the `Rejected claims` section of an older single-file
master) is parsed as STRUCTURE: its table rows become rejected claims, its text is never evidence.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

ID_BULLET = re.compile(r"^\s*[-*]\s+\*\*([A-Z]+(?:-[A-Z]+)?-\d{2,})\*\*\s*(.*)$")
HEAD = re.compile(r"^(#{1,6})\s+(.*)$")
BANK_HEAD = re.compile(r"experience|projects?|open source", re.I)
SKILLS_HEAD = re.compile(r"\bskills\b", re.I)
EDU_HEAD = re.compile(r"education", re.I)
GUARD_HEAD = re.compile(r"claims? not supported|metrics? not used|reject|do not (?:use|claim)|don'?t (?:use|claim)|never claim|forbidden|banned", re.I)
TAGS = re.compile(r"\s*(?:`[^`]*`\s*)+$")
QUOTED = re.compile(r"[\"“]([^\"”]+)[\"”]")
NUMERIC = re.compile(r"[\d][\d,.]*[+%]?[kKmMxX]?")


@dataclass
class Line:
    text: str
    kind: str      # bullet | skills
    ref: str = ""  # bullet id, or the skills group


@dataclass
class GuardRow:
    claim: str              # the cell as written
    phrases: list[str]      # the claims it lists (quoted phrases, else the whole cell)
    instead: str = ""       # the "write instead" cell: wording the guard itself allows


@dataclass
class Master:
    support: list[Line] = field(default_factory=list)
    guard: list[GuardRow] = field(default_factory=list)
    education: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def usable(self) -> list[str]:
        return [l.text for l in self.support]

    @property
    def usable_text(self) -> str:
        return "\n".join(self.usable)

    @property
    def rejected(self) -> list[str]:
        return [p for g in self.guard for p in g.phrases]


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _is_sep(line: str) -> bool:
    return bool(re.fullmatch(r"[\s|:\-]+", line.strip()))


def _phrases(cell: str) -> list[str]:
    q = [m.group(1).strip() for m in QUOTED.finditer(cell)]
    return q or [cell.strip().strip("`'")]


def parse_guard(text: str) -> list[GuardRow]:
    """Table rows under 'Claims not supported' / 'Metrics not used' / 'Rejected claims' headings.
    Prose, wording rules and every other section are ignored."""
    rows: list[GuardRow] = []
    mode, level, header = False, 0, None
    for ln in text.splitlines():
        h = HEAD.match(ln)
        if h:
            lv = len(h.group(1))
            if mode and lv <= level:
                mode = False
            if not mode and GUARD_HEAD.search(h.group(2)):
                mode, level = True, lv
            header = None
            continue
        if not mode or not ln.lstrip().startswith("|") or _is_sep(ln):
            continue
        cells = _cells(ln)
        if header is None:
            header = [c.lower() for c in cells]
            continue
        if not cells or not cells[0]:
            continue
        instead = ""
        for i, name in enumerate(header):
            if "write instead" in name and i < len(cells):
                instead = cells[i]
        rows.append(GuardRow(cells[0], _phrases(cells[0]), instead))
    return rows


def load(text: str, guard_text: str | None = None) -> Master:
    m = Master()
    h2 = ""
    in_bank = in_skills = in_edu = False
    skills_col = 1
    header_seen = False
    for ln in text.splitlines():
        h = HEAD.match(ln)
        if h:
            lv, title = len(h.group(1)), h.group(2)
            if lv <= 2:
                h2 = title
                in_bank = bool(BANK_HEAD.search(title))
                in_skills = bool(SKILLS_HEAD.search(title))
                in_edu = bool(EDU_HEAD.search(title))
                header_seen = False
            continue
        if in_bank:
            b = ID_BULLET.match(ln)
            if b:
                m.support.append(Line(TAGS.sub("", b.group(2)).strip(), "bullet", b.group(1)))
        elif in_skills and ln.lstrip().startswith("|") and not _is_sep(ln):
            cells = _cells(ln)
            if not header_seen:
                header_seen = True
                low = [c.lower() for c in cells]
                skills_col = next((i for i, c in enumerate(low) if "allowed wording" in c), 1)
                continue
            if skills_col < len(cells) and cells[skills_col]:
                m.support.append(Line(cells[skills_col], "skills", cells[0]))
        elif in_edu and ln.strip().startswith(("-", "*")):
            m.education.append(ln.strip(" -*"))
    m.guard = parse_guard(text) + (parse_guard(guard_text) if guard_text else [])
    if not m.support:
        m.warnings.append("master has no id-carrying bullets or Skills rows: the truth column has no evidence to offer")
    return m


def guard_path_for(master: Path) -> Path:
    """`<stem> — master resume.md` -> `<stem> — claim guard.md` next to it."""
    stem = master.name.rsplit(" — ", 1)[0] if " — " in master.name else master.stem
    return master.with_name(f"{stem} — claim guard.md")


def load_files(master: Path, guard: Path | None = None) -> Master:
    gp = guard or guard_path_for(master)
    guard_text = gp.read_text() if gp.exists() else None
    m = load(master.read_text(), guard_text)
    if guard_text is None:
        m.warnings.append(f"no claim guard loaded (looked for {gp.name}): rejected claims cannot be checked")
    return m


def claim_core(phrase: str) -> str:
    """A metric claim without its number: '350K MAU' -> 'MAU'."""
    return re.sub(r"\s+", " ", NUMERIC.sub("", phrase)).strip(" ,.;:/+-")
