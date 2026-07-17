"""Shared pytest fixtures. No network/Discord/DB calls happen in this suite by
default — external services are exercised only in tests marked `integration`
(see README.md: 'Running the tests')."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
