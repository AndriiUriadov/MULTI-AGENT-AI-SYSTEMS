"""
One-shot script that runs the hw-8 multi-agent system against the golden
dataset and stores the artefacts under tests/fixtures/, so pytest tests can
read them without re-invoking paid APIs every run.

Usage (from homework-lesson-10/):
    python tests/generate_fixtures.py
    python tests/generate_fixtures.py --only planner
    python tests/generate_fixtures.py --only e2e --id hp_rag_pipeline
    python tests/generate_fixtures.py --force

Fixture layout:
    tests/fixtures/planner/<id>.json      {input, plan, tools_called}
    tests/fixtures/researcher/<id>.json   {input, findings, retrieval_context, tools_called}
    tests/fixtures/critic/<id>.json       {input, critique, tools_called}
    tests/fixtures/e2e/<id>.json          {input, final_report, all_tools_called}
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Make the hw-10 project root importable when script is run as
# `python tests/generate_fixtures.py` from the project directory.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Silence HF/transformers noise before they get imported.
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("HF_HUB_VERBOSITY", "error")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")

from dotenv import load_dotenv

load_dotenv(_ROOT / ".env")
if not os.environ.get("OPENAI_API_KEY") and os.environ.get("API_KEY"):
    os.environ["OPENAI_API_KEY"] = os.environ["API_KEY"]

from langchain_core.messages import AIMessage, ToolMessage
from langgraph.types import Command

from agents.critic import critic_agent
from agents.planner import planner_agent
from agents.research import researcher_agent
from config import Settings
from supervisor import supervisor

settings = Settings()

GOLDEN_PATH = _ROOT / "tests" / "golden_dataset.json"
FIXTURES_ROOT = _ROOT / "tests" / "fixtures"
_RECURSION = settings.max_iterations * 2 + 1
_CRITIC_RECURSION = 31


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def extract_tool_calls(messages) -> list[dict]:
    """Pair each AIMessage.tool_call with its following ToolMessage output."""
    calls = []
    for i, msg in enumerate(messages):
        if isinstance(msg, AIMessage) and msg.tool_calls:
            for tc in msg.tool_calls:
                out = next(
                    (
                        m.content for m in messages[i + 1:]
                        if isinstance(m, ToolMessage) and m.tool_call_id == tc["id"]
                    ),
                    None,
                )
                calls.append({
                    "name": tc["name"],
                    "input_parameters": tc["args"],
                    "output": str(out) if out is not None else "",
                })
    return calls


def retrieval_context_from(messages) -> list[str]:
    """Collect deduplicated text from knowledge_search / read_url tool outputs."""
    ctx: list[str] = []
    seen: set[str] = set()
    for m in messages:
        if not isinstance(m, ToolMessage):
            continue
        if m.name not in ("knowledge_search", "read_url"):
            continue
        text = str(m.content).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        ctx.append(text)
    return ctx


def write_fixture(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def should_skip(path: Path, force: bool) -> bool:
    return path.exists() and not force


# ---------------------------------------------------------------------------
# Per-agent runners
# ---------------------------------------------------------------------------

def run_planner_fixture(example: dict, out_path: Path) -> None:
    result = planner_agent.invoke(
        {"messages": [{"role": "user", "content": example["input"]}]},
        config={"recursion_limit": _RECURSION},
    )
    messages = result.get("messages", [])
    plan_obj = result.get("structured_response")
    plan_json = plan_obj.model_dump() if plan_obj is not None else None
    write_fixture(out_path, {
        "id": example["id"],
        "input": example["input"],
        "plan": plan_json,
        "tools_called": extract_tool_calls(messages),
    })


def run_researcher_fixture(example: dict, out_path: Path) -> None:
    # Seed the researcher with the user's original request as a plain
    # instruction — same shape as what the Supervisor hands to research().
    instruction = example["input"]
    result = researcher_agent.invoke(
        {"messages": [{"role": "user", "content": instruction}]},
        config={"recursion_limit": _RECURSION},
    )
    messages = result.get("messages", [])
    findings = messages[-1].content if messages else ""
    write_fixture(out_path, {
        "id": example["id"],
        "input": instruction,
        "findings": str(findings),
        "retrieval_context": retrieval_context_from(messages),
        "tools_called": extract_tool_calls(messages),
    })


def run_critic_fixture(
    example: dict,
    out_path: Path,
    researcher_fixture_path: Path,
) -> None:
    # Critic is evaluated on the researcher's findings — not the raw user
    # input. If the researcher fixture is missing, skip (it'll be generated
    # on a later pass once researcher completes).
    if not researcher_fixture_path.exists():
        print(f"  [skip critic {example['id']}] researcher fixture missing")
        return
    with researcher_fixture_path.open(encoding="utf-8") as f:
        researcher = json.load(f)
    findings = researcher.get("findings", "")
    result = critic_agent.invoke(
        {"messages": [{"role": "user", "content": findings}]},
        config={"recursion_limit": _CRITIC_RECURSION},
    )
    messages = result.get("messages", [])
    critique_obj = result.get("structured_response")
    critique_json = critique_obj.model_dump() if critique_obj is not None else None
    write_fixture(out_path, {
        "id": example["id"],
        "input": findings,
        "critique": critique_json,
        "tools_called": extract_tool_calls(messages),
    })


def run_e2e_fixture(example: dict, out_path: Path) -> None:
    """Stream the supervisor end-to-end, auto-approving any HITL interrupts."""
    thread_config = {"configurable": {"thread_id": f"fixture-{example['id']}"}}
    all_messages: list = []
    inputs: object = {"messages": [{"role": "user", "content": example["input"]}]}

    while True:
        interrupted = False
        for chunk in supervisor.stream(inputs, thread_config):
            if "__interrupt__" in chunk:
                interrupt = chunk["__interrupt__"][0]
                inputs = Command(
                    resume={interrupt.id: {"decisions": [{"type": "approve"}]}}
                )
                interrupted = True
                break
            for node, update in chunk.items():
                if node.startswith("__"):
                    continue
                if isinstance(update, dict):
                    all_messages.extend(update.get("messages", []))
        if not interrupted:
            break

    # Final report = content passed to save_report (which is what HITL gates).
    final_report = ""
    for msg in all_messages:
        if isinstance(msg, AIMessage) and msg.tool_calls:
            for tc in msg.tool_calls:
                if tc["name"] == "save_report":
                    final_report = tc["args"].get("content", "") or final_report
    # Fallback: last AIMessage content if no save_report call was made.
    if not final_report:
        for msg in reversed(all_messages):
            if isinstance(msg, AIMessage) and msg.content and not msg.tool_calls:
                final_report = str(msg.content)
                break

    write_fixture(out_path, {
        "id": example["id"],
        "input": example["input"],
        "final_report": final_report,
        "all_tools_called": extract_tool_calls(all_messages),
    })


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

AGENTS = ("planner", "researcher", "critic", "e2e")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--only",
        choices=AGENTS,
        help="Generate fixtures only for the given agent.",
    )
    parser.add_argument(
        "--id",
        help="Generate fixtures only for the given golden-dataset id.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing fixture files.",
    )
    args = parser.parse_args()

    with GOLDEN_PATH.open(encoding="utf-8") as f:
        dataset = json.load(f)
    if args.id:
        dataset = [ex for ex in dataset if ex["id"] == args.id]
        if not dataset:
            raise SystemExit(f"No golden example with id={args.id!r}")

    targets = (args.only,) if args.only else AGENTS

    for example in dataset:
        ex_id = example["id"]
        print(f"\n=== {ex_id} ({example['category']}) ===")

        if "planner" in targets:
            path = FIXTURES_ROOT / "planner" / f"{ex_id}.json"
            if should_skip(path, args.force):
                print(f"  [skip planner] {path.name} exists")
            else:
                print(f"  planner → {path.name}")
                run_planner_fixture(example, path)

        if "researcher" in targets:
            path = FIXTURES_ROOT / "researcher" / f"{ex_id}.json"
            if should_skip(path, args.force):
                print(f"  [skip researcher] {path.name} exists")
            else:
                print(f"  researcher → {path.name}")
                run_researcher_fixture(example, path)

        if "critic" in targets:
            path = FIXTURES_ROOT / "critic" / f"{ex_id}.json"
            researcher_path = FIXTURES_ROOT / "researcher" / f"{ex_id}.json"
            if should_skip(path, args.force):
                print(f"  [skip critic] {path.name} exists")
            else:
                print(f"  critic → {path.name}")
                run_critic_fixture(example, path, researcher_path)

        if "e2e" in targets:
            path = FIXTURES_ROOT / "e2e" / f"{ex_id}.json"
            if should_skip(path, args.force):
                print(f"  [skip e2e] {path.name} exists")
            else:
                print(f"  e2e → {path.name}")
                run_e2e_fixture(example, path)

    print("\nDone.")


if __name__ == "__main__":
    main()
