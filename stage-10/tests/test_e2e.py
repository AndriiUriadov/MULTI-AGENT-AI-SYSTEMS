"""End-to-end tests on the full golden dataset.

For happy_path + edge_case: run AnswerRelevancy + Correctness + CitationPresence
on the final_report from the saved e2e fixture.

For failure_case: check deterministically that the final_report contains an
explicit refusal / out-of-scope marker rather than a fabricated answer.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from deepeval import assert_test
from deepeval.test_case import LLMTestCase

from tests.metrics import (
    answer_relevancy_metric,
    citation_presence_metric,
    correctness_metric,
)

_HERE = Path(__file__).parent
with (_HERE / "golden_dataset.json").open(encoding="utf-8") as _f:
    _GOLDEN = json.load(_f)

_ALL_IDS = [g["id"] for g in _GOLDEN]
_BY_ID = {g["id"]: g for g in _GOLDEN}

_REFUSAL_MARKERS = (
    "cannot answer",
    "can't answer",
    "unable to answer",
    "out of scope",
    "outside the scope",
    "no information",
    "not in the knowledge base",
    "i don't have",
    "i do not have",
    "cannot provide",
    "can't provide",
    "cannot assist",
    "can't assist",
    "not able to",
    "refuse",
    "unable to help",
    "cannot help",
    "cannot fulfill",
    "can't fulfill",
    "i will not",
    "won't assist",
    "no real-time",
    "real-time data",
    "please provide",
    "please clarify",
    "could you clarify",
    "not meaningful",
    "empty input",
    "no query",
)


def _load_e2e(fixtures_dir: Path, golden_id: str) -> dict:
    path = fixtures_dir / "e2e" / f"{golden_id}.json"
    if not path.exists():
        pytest.skip(f"{golden_id}: e2e fixture missing — see README 'Known weak spots'")
    with path.open(encoding="utf-8") as f:
        return json.load(f)


@pytest.mark.parametrize("golden_id", _ALL_IDS, ids=_ALL_IDS)
def test_e2e_golden(golden_id: str, fixtures_dir: Path) -> None:
    golden = _BY_ID[golden_id]
    fx = _load_e2e(fixtures_dir, golden_id)
    final_report = fx.get("final_report") or ""

    if golden["category"] == "failure_case":
        lowered = final_report.lower()
        # An empty report is itself a valid refusal signal — the supervisor
        # never produced a save_report call.
        if not final_report.strip():
            return
        assert any(m in lowered for m in _REFUSAL_MARKERS), (
            f"{golden_id}: final report lacks any refusal marker — "
            f"first 200 chars: {final_report[:200]!r}"
        )
        return

    assert final_report.strip(), f"{golden_id}: empty final_report"
    case = LLMTestCase(
        input=golden["input"],
        actual_output=final_report,
        expected_output=golden["expected_output"],
    )
    assert_test(
        case,
        [
            answer_relevancy_metric(threshold=0.7),
            correctness_metric(threshold=0.6),
            citation_presence_metric(threshold=0.7),
        ],
    )
