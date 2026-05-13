"""Component test: Editor must flag an obviously bad draft with low scores."""

from agents.editor import run_editor
from tests.goldens import BAD_DRAFT_FOR_EDITOR, EDITOR_CRITERIA, FIXED_PLAN_FOR_WRITER
from tests.judge import assert_passes, judge


def test_editor_rejects_off_topic_off_tone_draft():
    # The bad draft is judged against the PolyITAN plan — it ignores the plan
    # entirely (off-topic, off-tone), which is exactly what the Editor must flag.
    feedback = run_editor(FIXED_PLAN_FOR_WRITER, BAD_DRAFT_FOR_EDITOR)

    # Hard structural assertions: this draft MUST be rejected.
    assert feedback.verdict == "REVISION_NEEDED", (
        f"Editor approved a draft that is off-topic, off-tone, and off-plan "
        f"(scores: tone={feedback.tone_score}, acc={feedback.accuracy_score}, "
        f"struct={feedback.structure_score})"
    )
    assert feedback.tone_score <= 0.5, f"tone_score {feedback.tone_score} too high"
    assert feedback.structure_score <= 0.5, f"structure_score {feedback.structure_score} too high"
    assert len(feedback.issues) >= 2, "Editor must list at least 2 concrete issues"

    # Semantic check: issues should actually describe the real problems.
    verdict = judge(
        criteria=EDITOR_CRITERIA,
        input_={
            "plan": FIXED_PLAN_FOR_WRITER.model_dump(),
            "draft": BAD_DRAFT_FOR_EDITOR.model_dump(),
        },
        output=feedback.model_dump(),
    )
    assert_passes(verdict, threshold=0.7)
