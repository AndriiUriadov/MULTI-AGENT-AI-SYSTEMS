"""Planner Agent tests — Plan Quality GEval + deterministic sanity checks."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from deepeval import assert_test
from deepeval.test_case import LLMTestCase

from tests.metrics import plan_quality_metric

_HERE = Path(__file__).parent
with (_HERE / "golden_dataset.json").open(encoding="utf-8") as _f:
    _GOLDEN = json.load(_f)

# Failure cases don't have a valid plan to grade — skip from GEval.
_GRADED_IDS = [g["id"] for g in _GOLDEN if g["category"] in ("happy_path", "edge_case")]


def _load_fixture(fixtures_dir: Path, golden_id: str) -> dict:
    path = fixtures_dir / "planner" / f"{golden_id}.json"
    if not path.exists():
        pytest.skip(f"{golden_id}: planner fixture missing — see README 'Known weak spots'")
    with path.open(encoding="utf-8") as f:
        return json.load(f)


@pytest.mark.parametrize("golden_id", _GRADED_IDS, ids=_GRADED_IDS)
def test_plan_quality(golden_id: str, fixtures_dir: Path) -> None:
    fixture = _load_fixture(fixtures_dir, golden_id)
    case = LLMTestCase(
        input=fixture["input"],
        actual_output=json.dumps(fixture["plan"], indent=2, ensure_ascii=False),
    )
    assert_test(case, [plan_quality_metric(threshold=0.7)])


def test_plan_has_concrete_queries(fixtures_dir: Path) -> None:
    """Every graded plan must have a non-empty list of non-trivial queries."""
    problems: list[str] = []
    for g in _GOLDEN:
        if g["category"] == "failure_case":
            continue
        path = fixtures_dir / "planner" / f"{g['id']}.json"
        if not path.exists():
            continue
        with path.open(encoding="utf-8") as f:
            fx = json.load(f)
        plan = fx["plan"]
        assert plan is not None, f"{g['id']}: plan is None"
        queries = plan.get("search_queries", [])
        if not queries:
            problems.append(f"{g['id']}: empty search_queries")
            continue
        for q in queries:
            if len(q.strip()) < 10:
                problems.append(f"{g['id']}: vague query {q!r}")
    assert not problems, "\n".join(problems)


def test_plan_sources_are_valid(fixtures_dir: Path) -> None:
    """sources_to_check must only contain allowed literals."""
    allowed = {"knowledge_base", "web"}
    for g in _GOLDEN:
        if g["category"] == "failure_case":
            continue
        path = fixtures_dir / "planner" / f"{g['id']}.json"
        if not path.exists():
            continue
        with path.open(encoding="utf-8") as f:
            fx = json.load(f)
        sources = fx["plan"].get("sources_to_check", [])
        assert sources, f"{g['id']}: empty sources_to_check"
        for s in sources:
            assert s in allowed, f"{g['id']}: unknown source {s!r}"
