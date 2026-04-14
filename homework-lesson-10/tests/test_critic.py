"""Critic Agent tests — Critique Quality GEval + verdict consistency."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from deepeval import assert_test
from deepeval.test_case import LLMTestCase

from tests.metrics import critique_quality_metric

_HERE = Path(__file__).parent
with (_HERE / "golden_dataset.json").open(encoding="utf-8") as _f:
    _GOLDEN = json.load(_f)

# Critic is evaluated on researcher findings — failure_case findings are
# refusals, which don't carry a meaningful critique.
_CRITIC_IDS = [g["id"] for g in _GOLDEN if g["category"] in ("happy_path", "edge_case")]


def _load_fixture(fixtures_dir: Path, golden_id: str) -> dict:
    with (fixtures_dir / "critic" / f"{golden_id}.json").open(encoding="utf-8") as f:
        return json.load(f)


@pytest.mark.parametrize("golden_id", _CRITIC_IDS, ids=_CRITIC_IDS)
def test_critique_quality(golden_id: str, fixtures_dir: Path) -> None:
    fixture = _load_fixture(fixtures_dir, golden_id)
    case = LLMTestCase(
        input=fixture["input"],
        actual_output=json.dumps(fixture["critique"], indent=2, ensure_ascii=False),
    )
    assert_test(case, [critique_quality_metric(threshold=0.7)])


def test_verdict_consistency(fixtures_dir: Path) -> None:
    """APPROVE → empty revision_requests; REVISE → at least one."""
    problems: list[str] = []
    for g in _GOLDEN:
        if g["category"] == "failure_case":
            continue
        fx = _load_fixture(fixtures_dir, g["id"])
        crit = fx["critique"]
        verdict = crit["verdict"]
        requests = crit.get("revision_requests", [])
        if verdict == "APPROVE" and requests:
            problems.append(
                f"{g['id']}: verdict APPROVE but revision_requests is non-empty ({len(requests)})"
            )
        if verdict == "REVISE" and not requests:
            problems.append(f"{g['id']}: verdict REVISE but revision_requests is empty")
    assert not problems, "\n".join(problems)
