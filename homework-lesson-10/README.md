# homework-lesson-10 — DeepEval tests for the multi-agent system

Тестове покриття системи з `homework-lesson-8` (Supervisor → Planner →
Researcher → Critic) за допомогою DeepEval: golden dataset,
component-level метрики (GEval), ToolCorrectnessMetric і e2e з кастомною
метрикою `CitationPresence`.

## Передумови

1. Створити `.env` у корені теки:

   ```dotenv
   API_KEY=<My_Super_Secret_OpenAI_Key>
   MODEL_NAME=gpt-4o-mini
   JUDGE_MODEL=gpt-4o-mini
   ```

2. Встановити залежності:

   ```bash
   pip install -r requirements.txt
   ```

3. (Одноразово) зібрати RAG-індекс, якщо теки `index/` немає:

   ```bash
   python ingest.py
   ```

## Як запустити тести

```bash
deepeval test run tests/                 # усі тести
deepeval test run tests/test_planner.py  # один файл
pytest tests/                            # лише детерміністичні перевірки
```

## Як перегенерувати фікстури

Тести читають артефакти live-прогону агентів з `tests/fixtures/`. Щоб
перебудувати їх заново (платні виклики OpenAI):

```bash
python tests/generate_fixtures.py                 # усе заново (пропускає наявні)
python tests/generate_fixtures.py --only planner  # лише один агент
python tests/generate_fixtures.py --force         # перезаписати існуючі
python tests/generate_fixtures.py --id hp_rag_pipeline
```

## Відповідність вимогам `plan10.md`

| № | Вимога | Реалізація |
| --- | --- | --- |
| 1 | Golden Dataset 15–20 прикладів, 3 категорії | [`tests/golden_dataset.json`](tests/golden_dataset.json) — 15 прикладів (5 happy_path, 5 edge_case, 5 failure_case) |
| 2 | Component tests для Planner / Researcher / Critic | [`tests/test_planner.py`](tests/test_planner.py) — Plan Quality GEval + детерміністичні; [`tests/test_researcher.py`](tests/test_researcher.py) — Groundedness GEval + Sources-перевірка; [`tests/test_critic.py`](tests/test_critic.py) — Critique Quality GEval + verdict-consistency |
| 3 | ≥3 tool-correctness тест-кейси | [`tests/test_tools.py`](tests/test_tools.py) — 4 функції (`test_planner_tools`, `test_researcher_tools`, `test_supervisor_saves_on_approve`, параметризований `test_failure_case_does_not_save` × 5) |
| 4 | E2E на повному golden dataset, ≥2 метрики | [`tests/test_e2e.py`](tests/test_e2e.py) — `test_e2e_golden` × 15 з `AnswerRelevancy + Correctness + CitationPresence` (3 метрики) |
| 5 | ≥1 кастомна GEval метрика | `citation_presence_metric` у [`tests/metrics.py`](tests/metrics.py) — перевіряє наявність `## Sources` секції, ≥2 джерела та чи вони реально згадані в тілі звіту |
| 6 | Обґрунтовані пороги | Секція "Thresholds and rationale" нижче — пороги 0.5–0.7, встановлені як baseline, не як "pass-rate 100%" |
| 7 | `deepeval test run tests/` запускається без помилок | Так: exit 0, **35 passed, 10 failed, 7 skipped** (8:09 хв). Провали зафіксовано як baseline, див. "Baseline" і "Known weak spots" |

## Thresholds and rationale

Пороги встановлені як baseline, а не як "pass rate 100%". Не підвищувати
їх штучно, щоб зазеленити тести — замість того оновлювати систему під
тестом.

| Метрика | Threshold | Обґрунтування |
| --- | --- | --- |
| Plan Quality | 0.70 | Baseline з лекції (`lesson-10.ipynb`, блок 4.1). |
| Groundedness | 0.70 | Суворо для happy_path; частина edge може провалюватися — очікувано. |
| Critique Quality | 0.70 | Baseline з лекції. |
| Tool Correctness | 0.50 | Порівнюємо лише по іменах — аргументи для LLM крихкі, допускаємо неточність. |
| Answer Relevancy | 0.70 | Стандарт DeepEval. |
| Correctness | 0.60 | Нижче — `expected_output` стислий (2–4 речення), штрафує за будь-яке розширення. |
| Citation Presence | 0.70 | М'який — реальні звіти часто мають джерела у `## Sources`, але без inline-цитат. |

## Baseline (перший прогін)

`deepeval test run tests/` — **35 passed, 10 failed, 7 skipped** за 8:09
(повний журнал у `terminal.out`).

### Failures (за місцем)

**`test_e2e_golden` (6):**

| id | метрика | score | threshold |
| --- | --- | --- | --- |
| `hp_rag_pipeline` | Correctness | 0.52 | 0.60 |
| `hp_hybrid_retrieval` | Correctness | 0.53 | 0.60 |
| `hp_hybrid_retrieval` | Citation Presence | 0.61 | 0.70 |
| `hp_llm_context_window` | Correctness | 0.54 | 0.60 |
| `hp_reranking` | Citation Presence | 0.49 | 0.70 |
| `ec_everything_about_rag` | Correctness | 0.56 | 0.60 |
| `ec_llm_agent_ambiguous` | Answer Relevancy | 0.55 | 0.70 |

**`test_research_grounded` (3):**

| id | метрика | score | threshold |
| --- | --- | --- | --- |
| `hp_rag_pipeline` | Groundedness | 0.69 | 0.70 |
| `hp_llm_context_window` | Groundedness | 0.59 | 0.70 |
| `hp_reranking` | Groundedness | 0.66 | 0.70 |

**`test_research_has_sources_section` (1):** `ec_three_subquestions`
findings без заголовка `## Sources` / `## References`.

### Skipped (7): missing fixtures

- `test_e2e_golden`: `ec_three_subquestions`, `fc_gibberish`,
  `fc_nba_results`, `fc_weather_kyiv` — див. "Known weak spots".
- `test_failure_case_does_not_save`: ті самі 3 failure-case, плюс
  fixture для них відсутній. (Хоча насправді на етапі refactor можна
  переосмислити — див. нижче.)

## Known weak spots

1. **GraphRecursionError на частині failure/edge-запитів.**
   Під час `generate_fixtures.py` 5 прикладів провалилися з
   `langgraph.errors.GraphRecursionError` (recursion_limit=21 для
   планера/дослідника, 31 для критика). Зокрема: `e2e` на
   `ec_three_subquestions`, `fc_gibberish`, `fc_nba_results`,
   `fc_weather_kyiv`; `planner` на `fc_nba_results`. Supervisor
   зациклюється на цих запитах замість того, щоб рано відмовити.
   Це — legitimate baseline-сигнал, а не проблема тестів.

2. **Correctness < 0.6 на 4 happy/edge e2e.** Звіти семантично
   правильні, але GEval штрафує за розходження лексики і додаткові
   деталі, яких немає в стислому `expected_output` (2–4 речення).
   Варіанти покращення: довший `expected_output`, або м'якше
   формулювання `evaluation_steps`.

3. **Groundedness < 0.7 на 3 happy researcher-запусках.** Судячи з
   reasons, модель додає корисні деталі (benchmarks, performance
   implications), яких немає в `retrieval_context`. Рекомендація —
   або звузити researcher-prompt до строгого grounding, або
   розширити retrieval (більше chunks / глибший rerank).

4. **Citation Presence < 0.7 на 2 e2e.** Секція `## Sources` є, але
   в тілі звіту немає inline-посилань на джерела. Підтягується
   промптом supervisor'а ("include inline citations").

5. **`ec_three_subquestions` researcher — без Sources-секції.**
   Мульти-під-запит розсипає findings, агент забуває фінальний
   розділ. Можна зміцнити researcher-prompt.

6. **DeepEval Cloud upload error.** В кінці прогону DeepEval
   намагається завантажити результати у Confident AI (бачить
   закешований логін десь у середовищі) і падає з
   `ConfidentApiError: Invalid API key`. На pass/fail тестів не
   впливає — сам прогін уже завершений.

