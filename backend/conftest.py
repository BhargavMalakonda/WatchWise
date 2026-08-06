"""
conftest.py – project-root conftest.
Adds the backend directory to sys.path so that absolute imports like
  `from services.cache import ...`
work when pytest is run from the backend/ folder.
"""
import sys
from pathlib import Path

import pytest

# Ensure the backend/ directory is importable
sys.path.insert(0, str(Path(__file__).parent))


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """
    Clear slowapi's in-memory request counters before every test so that
    the 10/minute limit is never tripped by prior test runs in the same
    pytest session.
    """
    from core.security import limiter
    limiter._limiter.storage.reset()
    yield
