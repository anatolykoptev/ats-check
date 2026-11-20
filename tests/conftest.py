import os
from pathlib import Path

import pytest

from ats_check import health

FIX = Path(__file__).parent / "fixtures"
# hermetic: the fifth extractor family is a stand-in, whatever `filee` the machine has (tests that set the variable themselves override it)
os.environ["ATS_CHECK_FILEE"] = str(Path(__file__).parent / "fake_filee")
_cache: dict = {}


@pytest.fixture(scope="session")
def run_health():
    def _run(name: str):
        if name not in _cache:
            _cache[name] = health.run(FIX / f"{name}.pdf")
        return _cache[name]
    return _run
