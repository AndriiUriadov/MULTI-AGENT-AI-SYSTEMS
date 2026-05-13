"""
Golden test cases for the content-creation pipeline — KPI (Київська політехніка) brand.

All briefs and final content are in Ukrainian. The Langfuse-hosted judge
prompt is English but language-agnostic: the rubric + Ukrainian input/output
are passed verbatim, and the judge model reasons cross-lingually.
"""

from schemas import ContentPlan, DraftContent

# ---------------------------------------------------------------------------
# Strategist golden — KPI partnership announcement on LinkedIn
# ---------------------------------------------------------------------------

LINKEDIN_KPI_BRIEF = {
    "brief": (
        "Напиши пост для LinkedIn-сторінки КПІ ім. Ігоря Сікорського про запуск "
        "наносупутника PolyITAN-HP-30 ракетою SpaceX Falcon 9. "
        "Цільова аудиторія: міжнародні академічні партнери, наукова спільнота, "
        "випускники. Обсяг контенту: ≈250 слів. Тон: офіційний, стриманий, з гордістю."
    ),
    "criteria": (
        "ContentPlan має бути українською мовою. target_audience повинна чітко "
        "відповідати брифу — міжнародні академічні партнери та випускники (НЕ "
        "абітурієнти, НЕ казуальна студентська аудиторія). Тон: офіційний або "
        "стриманий з гордістю — НЕ «теплий», НЕ «меми», НЕ «storytime». outline "
        "має 4–8 секцій, що покривають: контекст запуску, що таке супутник, "
        "роль КПІ, значення. keywords включають щонайменше три з: "
        "'PolyITAN-HP-30', 'наносупутник', 'Falcon 9', 'КПІ ім. Ігоря Сікорського', "
        "'космічна програма'. План НЕ повинен пропонувати емоджі в заголовках чи "
        "жартівливий фреймінг."
    ),
}


# ---------------------------------------------------------------------------
# Writer golden — fixed plan → draft must cover all sections + keywords
# ---------------------------------------------------------------------------

FIXED_PLAN_FOR_WRITER = ContentPlan(
    outline=[
        "Контекст: як КПІ потрапив на борт Falcon 9",
        "PolyITAN-HP-30: що це за наносупутник і для чого",
        "Команда КПІ: викладачі, аспіранти, студенти, які створили апарат",
        "Значення запуску для української науки та освіти",
        "Подяки партнерам та запрошення до співпраці",
    ],
    keywords=[
        "PolyITAN-HP-30",
        "наносупутник",
        "Falcon 9",
        "КПІ ім. Ігоря Сікорського",
        "космічна програма",
    ],
    key_messages=[
        "КПІ — єдиний український ЗВО з власною космічною програмою CubeSat.",
        "Студенти і аспіранти беруть участь у реальних міжнародних місіях.",
        "Запуск демонструє, що українська інженерна школа бере участь у світових технологічних процесах попри війну.",
    ],
    target_audience="Міжнародні академічні партнери, випускники, українська і закордонна наукова спільнота",
    tone="офіційний, стриманий, з гордістю",
    word_count_target=350,
)

WRITER_CRITERIA = (
    "Текст має бути УКРАЇНСЬКОЮ мовою. Draft повинен покрити КОЖНУ з 5 секцій "
    "outline (кожній секції відповідає окремий абзац або підзаголовок — "
    "контекст запуску, опис супутника, роль команди, значення, подяки). "
    "УСІ 5 ключових слів мають бути присутні в тексті дослівно (не перефразовані). "
    "Тон: офіційний, стриманий — НЕ казуальний, НЕ меми, НЕ звертання 'ти'/'фам'. "
    "Список keywords_used НЕ повинен містити жодного слова, якого немає в тексті."
)


# ---------------------------------------------------------------------------
# Editor golden — deliberately bad draft for a KPI-context plan
# ---------------------------------------------------------------------------

BAD_DRAFT_FOR_EDITOR = DraftContent(
    content=(
        "# Йоу, фам 🚀 КПІ ЛІТАЄ В КОСМОС???\n\n"
        "Хей, політехи! Ви не повірите, але нам реально щось запустили в космос лол 😂\n\n"
        "Хто в темі — тому привіт. Хто не в темі — ну тепер ви в темі.\n\n"
        "Їжа в їдальні корпусу №7 стала нарешті нормальна, респект кухарям! 🍕🍔\n"
        "Ще до цього треба було йти з університетом на спорт-бази, а тепер усе в кампусі.\n\n"
        "Коротше, космос — це круто, лайкайте пост, кидайте в сторіс.\n\n"
        "#КПІ #космос #СупутникЯкий"
    ),
    word_count=75,
    keywords_used=["КПІ"],
)

EDITOR_CRITERIA = (
    "You are evaluating the Editor's OUTPUT (an EditFeedback object). "
    "The Editor was asked to review an obviously bad draft (memes, off-topic, "
    "cafeteria jokes) against a plan about the PolyITAN-HP-30 launch — the "
    "draft itself is NOT what you score. Only the Editor's output matters.\n\n"
    "A GOOD output (score → 1.0):\n"
    "- verdict == 'REVISION_NEEDED'\n"
    "- tone_score <= 0.5 AND structure_score <= 0.5\n"
    "- issues list has >= 2 specific, actionable items that name the real "
    "problems (off-topic content, wrong register/tone, missing outline sections, "
    "or missing keywords)\n\n"
    "A BAD output (score → 0.0):\n"
    "- verdict == 'APPROVED' (editor failed to reject bad content), OR\n"
    "- any score > 0.5 (editor was too lenient), OR\n"
    "- issues list is empty, vague ('improve the intro'), or misses what's "
    "obviously wrong with the draft.\n\n"
    "Focus exclusively on whether the EditFeedback correctly characterizes "
    "the problems. Do not re-judge the draft itself."
)


# ---------------------------------------------------------------------------
# E2E golden — Instagram Reels post about KPI event
# ---------------------------------------------------------------------------

E2E_BRIEF = (
    "Напиши короткий пост для Instagram (формат опису під Reels) акаунту "
    "КПІ ім. Ігоря Сікорського про щорічну подію «Дослідник року 2026». "
    "Цільова аудиторія: нинішні студенти КПІ та старшокласники-абітурієнти. "
    "Обсяг: 150–220 слів. Тон: теплий, з почуттям спільноти, природний — "
    "живі деталі про подію, заклик до дії в кінці. Українською мовою."
)

E2E_CRITERIA = (
    "Фінальний контент має бути УКРАЇНСЬКОЮ мовою. Довжина ≈ 150–250 слів "
    "(допуск ±30%). Аудиторія — студенти та абітурієнти (НЕ міжнародні "
    "партнери, НЕ академічна спільнота). Тон — теплий, природний, з почуттям "
    "спільноти; НЕ офіційний, НЕ сухий. Має бути згадка події «Дослідник року» "
    "(або «Дослідник року 2026») і заклик до дії в кінці (реєстрація, прихід, "
    "поділитися). Формат схожий на Instagram-пост: короткі абзаци, "
    "читабельна структура, щонайбільше 2–3 хештеги в кінці якщо взагалі."
)
