"""Component test: Strategist plan must match the brief's audience, tone, channel."""

from agents.strategist import run_strategist
from tests.goldens import LINKEDIN_KPI_BRIEF
from tests.judge import assert_passes, judge


def test_strategist_professional_linkedin_brief():
    brief = LINKEDIN_KPI_BRIEF["brief"]
    plan = run_strategist(brief)

    # Cheap structural preconditions before spending tokens on the judge.
    assert 4 <= len(plan.outline) <= 8, f"outline has {len(plan.outline)} sections"
    assert len(plan.keywords) >= 5, "plan must have ≥5 keywords"
    assert plan.target_audience, "target_audience cannot be empty"
    assert plan.tone, "tone cannot be empty"

    verdict = judge(
        criteria=LINKEDIN_KPI_BRIEF["criteria"],
        input_=brief,
        output=plan.model_dump_json(indent=2),
    )
    assert_passes(verdict, threshold=0.7)
