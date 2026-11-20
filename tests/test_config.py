"""offersmith.toml and the OFFERSMITH_* variables: precedence flag > environment > file, and loud errors."""
import json
from pathlib import Path

import pytest

from ats_check import cli, config
from ats_check import jd_reqs as jr
from mk import bank

FX = Path(__file__).parent / "fixtures"


def write(tmp_path, text, name="offersmith.toml"):
    f = tmp_path / name
    f.write_text(text, encoding="utf-8")
    return f


def test_file_values_resolve_relative_to_the_file(tmp_path, monkeypatch):
    f = write(tmp_path, 'master = "m/Jane — master resume.md"\nout_dir = "~/reports"\nworkday_base = "https://x.wd1.myworkdayjobs.com/S"\n')
    monkeypatch.setenv("OFFERSMITH_CONFIG", str(f))
    c = config.load()
    assert c.master == tmp_path / "m" / "Jane — master resume.md"
    assert c.out_dir == Path("~/reports").expanduser()
    assert c.workday_base == "https://x.wd1.myworkdayjobs.com/S" and c.source == f


def test_environment_beats_the_file(tmp_path, monkeypatch):
    monkeypatch.setenv("OFFERSMITH_CONFIG", str(write(tmp_path, 'master = "a.md"\n')))
    monkeypatch.setenv("OFFERSMITH_MASTER", str(tmp_path / "b.md"))
    assert config.load().master == tmp_path / "b.md"


def test_legacy_workday_variable_is_still_read(monkeypatch):
    monkeypatch.setenv("ATS_CHECK_WORKDAY_BASE", "https://y.wd5.myworkdayjobs.com/T")
    assert config.load().workday_base == "https://y.wd5.myworkdayjobs.com/T"


def test_cwd_file_is_found_when_no_env_pins_one(tmp_path, monkeypatch):
    monkeypatch.delenv("OFFERSMITH_CONFIG")
    write(tmp_path, 'guard = "g.md"\n')
    assert config.load(cwd=tmp_path).guard == tmp_path / "g.md"


@pytest.mark.parametrize("text,msg", [
    ('mastr = "x"\n', "unknown key"),
    ("master = 3\n", "must be a string"),
    ("master = \n", "not valid TOML"),
])
def test_a_bad_file_is_an_error_naming_the_file(tmp_path, monkeypatch, text, msg):
    f = write(tmp_path, text)
    monkeypatch.setenv("OFFERSMITH_CONFIG", str(f))
    with pytest.raises(config.ConfigError, match=msg):
        config.load()


def test_a_pinned_but_missing_file_is_an_error(tmp_path, monkeypatch):
    monkeypatch.setenv("OFFERSMITH_CONFIG", str(tmp_path / "nope.toml"))
    with pytest.raises(config.ConfigError, match="missing file"):
        config.load()


def run_cli(tmp_path, monkeypatch, extra=()):
    orig = cli.jd_reqs.extract
    cli.jd_reqs.extract = lambda *a, **k: jr.JD(requirements=[jr.Requirement(term="Terraform", importance="required")])
    try:
        return cli.main(["--resume", str(FX / "clean.pdf"), "--jd", str(FX / "jd.txt"), "--no-llm", *extra])
    finally:
        cli.jd_reqs.extract = orig


def test_cli_takes_master_and_out_dir_from_the_file(tmp_path, monkeypatch):
    m = tmp_path / "Jane — master resume.md"
    m.write_text(bank("Led Terraform migrations for 40 services."))
    f = write(tmp_path, f'master = "{m}"\nout_dir = "{tmp_path / "reports"}"\n')
    monkeypatch.setenv("OFFERSMITH_CONFIG", str(f))
    assert run_cli(tmp_path, monkeypatch) == 0
    d = json.loads((tmp_path / "reports" / "clean" / "report.json").read_text())
    assert d["inputs"]["master"] == str(m)
    assert [r["status"] for r in d["requirements"]] == ["add_it"]


def test_cli_flag_beats_the_file(tmp_path, monkeypatch):
    f = write(tmp_path, f'out_dir = "{tmp_path / "reports"}"\n')
    monkeypatch.setenv("OFFERSMITH_CONFIG", str(f))
    assert run_cli(tmp_path, monkeypatch, ["--out", str(tmp_path / "flag")]) == 0
    assert (tmp_path / "flag" / "report.json").exists() and not (tmp_path / "reports").exists()


def test_cli_exits_2_on_a_bad_config(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("OFFERSMITH_CONFIG", str(write(tmp_path, "bogus = 1\n")))
    assert run_cli(tmp_path, monkeypatch) == 2
    assert "unknown key" in capsys.readouterr().err
