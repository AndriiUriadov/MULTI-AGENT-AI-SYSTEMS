"""
LLM-as-a-Judge helper used across the test files.

`judge()` calls a model (through the Model Gateway, task="judge") with
a rubric and returns a structured JudgeVerdict. Each call is wrapped
with `@observe` so runs show up in Langfuse under the `eval` tag.
"""

from typing import Any

from langfuse import get_client, observe, propagate_attributes
from pydantic import BaseModel, Field

from config import Settings, load_prompt
from model_gateway import get_chat_model

_settings = Settings()
_lf_client = get_client()


class JudgeVerdict(BaseModel):
    score: float = Field(ge=0.0, le=1.0, description="Rubric score, 0.0–1.0")
    reasoning: str = Field(description="Why you assigned this score (1–2 sentences)")
    issues: list[str] = Field(default_factory=list, description="Concrete problems (empty if strong)")


@observe(name="llm-judge")
def judge(criteria: str, input_: Any, output: Any) -> JudgeVerdict:
    """Run the judge and return a structured verdict.

    `criteria`, `input_`, and `output` are stringified and passed to the judge
    model. Any non-string value is cast via str() so callers can pass dicts,
    Pydantic models, etc. without ceremony.
    """
    model = get_chat_model("judge", temperature=0.0).with_structured_output(JudgeVerdict)
    system_prompt = load_prompt("judge_system")

    user_msg = (
        f"CRITERIA:\n{criteria}\n\n"
        f"INPUT:\n{input_}\n\n"
        f"OUTPUT:\n{output}"
    )

    with propagate_attributes(tags=["course-project", "eval"]):
        verdict = model.invoke(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg},
            ]
        )

    _lf_client.flush()
    return verdict


def assert_passes(verdict: JudgeVerdict, threshold: float = 0.7) -> None:
    """Raise AssertionError with reasoning if the verdict is below threshold."""
    if verdict.score < threshold:
        issues = "\n  - ".join(verdict.issues) if verdict.issues else "(no issues listed)"
        raise AssertionError(
            f"Judge score {verdict.score:.2f} < {threshold:.2f}\n"
            f"Reasoning: {verdict.reasoning}\n"
            f"Issues:\n  - {issues}"
        )
