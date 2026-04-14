"""Tool-correctness tests for Planner / Researcher / Supervisor.

Compares the names of tools actually called against the expected list from
the golden dataset. Arguments are deliberately not compared — they are too
brittle for a non-deterministic LLM.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from deepeval import assert_test
from deepeval.test_case import LLMTestCase, ToolCall

from tests.metrics import tool_correctness_metric

_HERE = Path(__file__).parent
with (_HERE / "golden_dataset.json").open(encoding="utf-8") as _f:
    _GOLDEN = json.load(_f)


def _to_toolcalls(raw: list[dict]) -> list[ToolCall]:
    return [
        ToolCall(name=t["name"], input_parameters=t.get("input_parameters") or {})
        for t in raw or []
    ]


def _load(fixtures_dir: Path, subdir: str, golden_id: str) -> dict:
    path = fixtures_dir / subdir / f"{golden_id}.json"
    if not path.exists():
        pytest.skip(f"{golden_id}: {subdir} fixture missing — see README 'Known weak spots'")
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _pick(category: str, expected_tool: str) -> str:
    """First golden id that has `expected_tool` among `expected_tools`."""
    for g in _GOLDEN:
        if g["category"] != category:
            continue
        if expected_tool in (g.get("expected_tools") or []):
            return g["id"]
    raise RuntimeError(f"No {category} golden with expected tool {expected_tool!r}")


def test_planner_tools(fixtures_dir: Path) -> None:
    """On a happy-path KB query, the planner must call knowledge_search or web_search."""
    golden_id = _pick("happy_path", "knowledge_search")
    fx = _load(fixtures_dir, "planner", golden_id)
    case = LLMTestCase(
        input=fx["input"],
        actual_output=json.dumps(fx["plan"], ensure_ascii=False),
        tools_called=_to_toolcalls(fx["tools_called"]),
        expected_tools=[ToolCall(name="knowledge_search"), ToolCall(name="web_search")],
    )
    assert_test(case, [tool_correctness_metric()])


def test_researcher_tools(fixtures_dir: Path) -> None:
    """On a happy-path KB query, the researcher must use knowledge_search."""
    golden_id = _pick("happy_path", "knowledge_search")
    fx = _load(fixtures_dir, "researcher", golden_id)
    case = LLMTestCase(
        input=fx["input"],
        actual_output=fx["findings"],
        tools_called=_to_toolcalls(fx["tools_called"]),
        expected_tools=[ToolCall(name="knowledge_search")],
    )
    assert_test(case, [tool_correctness_metric()])


def test_supervisor_saves_on_approve(fixtures_dir: Path) -> None:
    """E2E: a happy-path approved run must end with a save_report call."""
    golden_id = _pick("happy_path", "knowledge_search")
    fx = _load(fixtures_dir, "e2e", golden_id)
    case = LLMTestCase(
        input=fx["input"],
        actual_output=fx["final_report"] or "<no report>",
        tools_called=_to_toolcalls(fx["all_tools_called"]),
        expected_tools=[ToolCall(name="save_report")],
    )
    assert_test(case, [tool_correctness_metric()])


@pytest.mark.parametrize(
    "golden_id",
    [g["id"] for g in _GOLDEN if g["category"] == "failure_case"],
    ids=[g["id"] for g in _GOLDEN if g["category"] == "failure_case"],
)
def test_failure_case_does_not_save(golden_id: str, fixtures_dir: Path) -> None:
    """Out-of-domain / refused inputs should not trigger save_report."""
    fx = _load(fixtures_dir, "e2e", golden_id)
    called = [t["name"] for t in fx.get("all_tools_called") or []]
    assert "save_report" not in called, (
        f"{golden_id}: save_report was called on a failure case — "
        f"tool sequence: {called}"
    )
