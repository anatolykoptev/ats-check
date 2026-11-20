from pathlib import Path

import pytest

from ats_check import health

FIX = Path(__file__).parent / "fixtures"
_cache: dict = {}


@pytest.fixture(scope="session")
def run_health():
    def _run(name: str):
        if name not in _cache:
            _cache[name] = health.run(FIX / f"{name}.pdf")
        return _cache[name]
    return _run
