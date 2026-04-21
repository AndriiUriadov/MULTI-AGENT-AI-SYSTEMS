"""Component test: Writer must cover every outline section and use plan keywords."""

from agents.writer import run_writer
from tests.goldens import FIXED_PLAN_FOR_WRITER, WRITER_CRITERIA
from tests.judge import assert_passes, judge


def test_writer_covers_all_outline_and_keywords():
    draft = run_writer(FIXED_PLAN_FOR_WRITER)

    # Structural: at least some content, non-trivial word count.
    assert draft.word_count > 200, f"draft is too short: {draft.word_count} words"
    assert draft.content.strip(), "draft content is empty"

    # Keywords the writer *claims* to have used must appear at least as a stem
    # (first 5 chars, case-insensitive). Ukrainian morphology inflects nouns —
    # 'космічна програма' in the keyword list legitimately becomes 'космічної
    # програми' in the body. The semantic coverage check is delegated to judge().
    lower = draft.content.lower()
    for kw in draft.keywords_used:
        for word in kw.lower().split():
            if len(word) < 5:
                continue
            stem = word[:5]
            assert stem in lower, (
                f"claimed keyword {kw!r}: stem {stem!r} for word {word!r} "
                f"does not appear in the draft body"
            )

    verdict = judge(
        criteria=WRITER_CRITERIA,
        input_=FIXED_PLAN_FOR_WRITER.model_dump_json(indent=2),
        output=draft.content,
    )
    assert_passes(verdict, threshold=0.7)
