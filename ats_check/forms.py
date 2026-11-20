"""Acronym / expansion helpers shared by the JD and match layers."""
import re

def _is_acronym(f: str) -> bool:
    return " " not in f.strip() and (f.isupper() or len(f) <= 4 and any(c.isupper() or c.isdigit() for c in f[1:]))


_SMALL = {"of", "as", "the", "and", "for", "to", "in"}


def is_expansion(short: str, long: str) -> bool:
    """True when `short` is an acronym / numeronym of `long` (MCP~Model Context Protocol, IaC~Infrastructure as Code, K8s~Kubernetes)."""
    if not _is_acronym(short) or _is_acronym(long):
        return False
    words = re.findall(r"[A-Z][a-z]*|[a-z]+|\d+", long.replace("-", " ").replace(".", " "))
    full = "".join(w[0] for w in words).lower()
    sig = "".join(w[0] for w in words if w.lower() not in _SMALL).lower()
    sh = re.sub(r"[^a-z0-9]", "", short.lower())
    num = long.replace(" ", "")
    return sh in (full, sig) or (len(num) > 3 and sh == f"{num[0].lower()}{len(num) - 2}{num[-1].lower()}")


