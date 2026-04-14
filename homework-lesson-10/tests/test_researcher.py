"""Research Agent tests — Groundedness GEval + deterministic sanity checks."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from deepeval import assert_test
from deepeval.test_case import LLMTestCase

from tests.metrics import groundedness_metric

_HERE = Path(__file__).parent
with (_HERE / "golden_dataset.json").open(encoding="utf-8") as _f:
    _GOLDEN = json.load(_f)

# Groundedness is only meaningful when retrieval_context is reliable —
# that's our happy_path set, which is fully covered by the local corpus.
_GROUNDED_IDS = [g["id"] for g in _GOLDEN if g["category"] == "happy_path"]

_SOURCES_RE = re.compile(r"^\s*#{1,6}\s*(Sources?|References?)\b", re.MULTILINE | re.IGNORECASE)


def _load_fixture(fixtures_dir: Path, golden_id: str) -> dict:
    with (fixtures_dir / "researcher" / f"{golden_id}.json").open(encoding="utf-8") as f:
        return json.load(f)


@pytest.mark.parametrize("golden_id", _GROUNDED_IDS, ids=_GROUNDED_IDS)
def test_research_grounded(golden_id: str, fixtures_dir: Path) -> None:
    fixture = _load_fixture(fixtures_dir, golden_id)
    ctx = fixture.get("retrieval_context") or []
    if not ctx:
        pytest.skip(f"{golden_id}: no retrieval_context — nothing to ground against")
    case = LLMTestCase(
        input=fixture["input"],
        actual_output=fixture["findings"],
        retrieval_context=ctx,
    )
    assert_test(case, [groundedness_metric(threshold=0.7)])


def test_research_has_sources_section(fixtures_dir: Path) -> None:
    """Happy/edge researcher findings must include a Sources/References section."""
    problems: list[str] = []
    for g in _GOLDEN:
        if g["category"] == "failure_case":
            continue
        fx = _load_fixture(fixtures_dir, g["id"])
        findings = fx.get("findings") or ""
        if not _SOURCES_RE.search(findings):
            problems.append(f"{g['id']}: missing '## Sources' / '## References' heading")
    assert not problems, "\n".join(problems)
