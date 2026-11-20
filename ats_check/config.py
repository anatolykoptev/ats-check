"""Where your files live: `offersmith.toml`, with environment overrides.

Lookup order for the file: $OFFERSMITH_CONFIG (when set it is the only candidate; empty means no file), then
./offersmith.toml, then ~/.config/offersmith/offersmith.toml.
Keys (all optional, `~` expands, a relative path is relative to the file that names it):

    master       = "~/offersmith/Your Name — master resume.md"
    guard        = ""                       # default: "<stem> — claim guard.md" next to the master
    out_dir      = "~/offersmith/out"       # reports go to <out_dir>/<resume stem>
    workday_base = "https://<tenant>.wdN.myworkdayjobs.com/<site>"

Environment wins over the file: OFFERSMITH_MASTER, OFFERSMITH_GUARD, OFFERSMITH_OUT, OFFERSMITH_WORKDAY_BASE
(ATS_CHECK_WORKDAY_BASE is still read). A command-line flag wins over both.

Standard library only: the skill scripts load this file by path under a bare `python3 -I`.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    import tomllib
except ImportError:  # Python < 3.11 under a bare interpreter
    tomllib = None

FILE_NAME = "offersmith.toml"
KEYS = ("master", "guard", "out_dir", "workday_base")
ENV = {"master": "OFFERSMITH_MASTER", "guard": "OFFERSMITH_GUARD", "out_dir": "OFFERSMITH_OUT",
       "workday_base": "OFFERSMITH_WORKDAY_BASE"}


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Config:
    master: Path | None = None
    guard: Path | None = None
    out_dir: Path | None = None
    workday_base: str | None = None
    source: Path | None = None      # the file the values came from, if any


def candidates(cwd: Path | None = None) -> list[Path]:
    env = os.environ.get("OFFERSMITH_CONFIG")
    if env is not None:
        if not env.strip():
            return []
        f = Path(env).expanduser()
        if not f.is_file():
            raise ConfigError(f"OFFERSMITH_CONFIG points at a missing file: {f}")
        return [f]
    return [(cwd or Path.cwd()) / FILE_NAME, Path("~/.config/offersmith").expanduser() / FILE_NAME]


def _path(raw: str, base: Path | None) -> Path:
    p = Path(raw).expanduser()
    return p if p.is_absolute() or base is None else (base / p)


def load(cwd: Path | None = None) -> Config:
    values: dict[str, str] = {}
    source = None
    for f in candidates(cwd):
        if not f.is_file():
            continue
        if tomllib is None:
            raise ConfigError(f"{f}: reading TOML needs Python 3.11 or newer (or set the OFFERSMITH_* variables)")
        try:
            data = tomllib.loads(f.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as e:
            raise ConfigError(f"{f}: not valid TOML: {e}") from e
        unknown = sorted(set(data) - set(KEYS))
        if unknown:
            raise ConfigError(f"{f}: unknown key(s) {', '.join(unknown)} (allowed: {', '.join(KEYS)})")
        for k in KEYS:
            if k in data:
                if not isinstance(data[k], str):
                    raise ConfigError(f"{f}: {k} must be a string")
                if data[k].strip():
                    values[k] = data[k].strip()
        source = f
        break
    base = source.parent if source else None
    cfg = {k: (_path(v, base) if k != "workday_base" else v) for k, v in values.items()}
    for k, var in ENV.items():
        v = os.environ.get(var, "").strip()
        if not v and k == "workday_base":
            v = os.environ.get("ATS_CHECK_WORKDAY_BASE", "").strip()
        if v:
            cfg[k] = Path(v).expanduser() if k != "workday_base" else v
    return Config(source=source, **cfg)


if __name__ == "__main__":      # `python3 -I ats_check/config.py` prints what would be used
    c = load()
    print(f"config file: {c.source or '(none)'}")
    for k in KEYS:
        print(f"{k}: {getattr(c, k) or '(unset)'}")
    sys.exit(0)
