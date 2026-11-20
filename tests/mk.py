"""Builders for masters in the REAL layout (id bullets under Experience, Skills table, claim guard)."""


def bank(*bullets: str, skills: str = "", section: str = "## 4. Experience") -> str:
    """A master whose bullets carry ids, as a real master does."""
    body = "\n".join(f"- **KPE-{i + 1:02d}** {b}" for i, b in enumerate(bullets))
    out = f"# Master\n\n{section}\n### Role\n{body}\n"
    if skills:
        out += f"\n## 3. Skills\n| Group | Allowed wording | Evidence |\n|---|---|---|\n| Tools | {skills} | KPE-01 |\n"
    return out


def guard(*rows: tuple[str, str, str]) -> str:
    """A claim guard: (claim, reason, write instead) rows."""
    t = "# Claim guard\n\n## Claims not supported\n| Claim | Status and reason | Write instead |\n|---|---|---|\n"
    return t + "".join(f"| {c} | {r} | {w} |\n" for c, r, w in rows)
