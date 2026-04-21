"""Pytest configuration — make the project root importable."""

import os
import sys

# Add the project root (parent of tests/) to sys.path so `from config import ...`
# works when pytest is invoked from inside course-project/ or from the repo root.
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
