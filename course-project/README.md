# Курсовий проєкт — Конвеєр створення контенту

Мультиагентна система для створення контенту блогу / соцмереж: **Content Strategist** планує, **Writer** пише, **Editor** рев'ює. Обгорнуто в LangGraph з HITL на затвердженні плану + Evaluator-Optimizer loop'ом Writer ↔ Editor. Повна observability через Langfuse (tracing + Prompt Management + LLM-as-a-Judge evaluators). Тести — pytest + власна `judge()` функція.

## Архітектура

**Патерни:** Prompt Chaining (Strategist → HITL → Writer) + Evaluator-Optimizer (Writer ↔ Editor).

```
             ┌──────────────┐
 User brief ─►  Strategist   ──►  ContentPlan
             └──────────────┘
                    │
                    ▼
             ┌──────────────┐       revise + feedback
             │  HITL gate   │ ─────────────────────────┐
             └──────────────┘                          │
                    │ approve                          │
                    ▼                                  │
             ┌──────────────┐                          │
       ┌────►│   Writer     │◄─── REVISION_NEEDED ─┐   │
       │     └──────────────┘                      │   │
       │            │                              │   │
       │            ▼                              │   │
       │     ┌──────────────┐                      │   │
       │     │   Editor     │──────────────────────┘   │
       │     └──────────────┘     (iter < 5)           │
       │            │                                  │
       │     APPROVED or iter ≥ 5                      │
       │            ▼                                  │
       │     ┌──────────────┐                          │
       └─────│    save      │──► output/*.md   ◄───────┘ (Strategist re-plan)
             └──────────────┘
```

## Стек

- **LangGraph / LangChain** — граф, агенти (`create_agent` з `response_format=PydanticModel`), HITL через `interrupt()` + `Command(resume=...)`.
- **Pydantic** — контракти `ContentPlan`, `DraftContent`, `EditFeedback` (див. [schemas.py](schemas.py)).
- **Model Gateway** ([model_gateway.py](model_gateway.py)) — task → model + LangChain `.with_fallbacks([...])` на випадок RateLimitError.
- **Langfuse** — всі system prompts у Prompt Management (label `production`), `@observe` + `propagate_attributes` для session/user/tags, 2–3 evaluator'и (numeric/boolean/categorical).
- **RAG** — FAISS + BM25 + `BAAI/bge-reranker-base` (перенесено з hw-8) для бренд-довідника (style guide, brand, приклади).
- **Tests** — pytest + LLM-as-a-Judge helper у [tests/judge.py](tests/judge.py).

## Структура

```
course-project/
├── config.py                # Settings + load_prompt()
├── model_gateway.py         # task → ChatOpenAI з fallbacks
├── schemas.py               # ContentPlan, DraftContent, EditFeedback
├── tools.py                 # web_search, read_url, knowledge_search, save_content
├── retriever.py             # hybrid RAG (FAISS + BM25 + reranker)
├── ingest.py                # build index from data/
├── agents/
│   ├── strategist.py
│   ├── writer.py
│   └── editor.py
├── graph.py                 # LangGraph: nodes + HITL + Evaluator-Optimizer
├── main.py                  # REPL + Langfuse wrapping
├── tests/
│   ├── judge.py             # спільна LLM-as-a-Judge функція
│   ├── goldens.py           # тестові брифи + очікування
│   ├── test_strategist.py
│   ├── test_writer.py
│   ├── test_editor.py
│   └── test_e2e.py
├── data/                    # RAG корпус (style guide, brand, приклади)
├── index/                   # FAISS + BM25 після ingest
├── output/                  # збережені .md артефакти
└── screenshots/             # скріншоти Langfuse UI
```

## Запуск

```bash
cd course-project
pip install -r requirements.txt
cp .env.example .env         # і заповнити значення
python main.py
```

Перед першим запуском **налаштуйте Langfuse через UI** (LLM Connection, 4 prompts з label `production`, 2–3 evaluators). Код без цього впаде на `load_prompt()` з `404 prompt not found`. Інструкції з текстом промптів — у локальному `LANGFUSE_SETUP.md` (не комітиться).

Для роботи RAG додайте бренд-матеріали в `data/` і зробіть `python ingest.py`. Без цього `knowledge_search` повертає заглушку — pipeline працює, але без brand grounding.

### `.env`

```
API_KEY=sk-...

# Model gateway — per-task моделі + fallback-ланцюг
MODEL_STRATEGIST=gpt-4o-mini
MODEL_WRITER=gpt-4o-mini
MODEL_EDITOR=gpt-4o-mini
MODEL_JUDGE=gpt-4o-mini
FALLBACK_MODELS=gpt-4o-mini,gpt-4o

# Langfuse
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=https://us.cloud.langfuse.com
LANGFUSE_USER_ID=your-id
```

## Приклад

```
Brief: Write a 400-word LinkedIn post for senior software engineers about why AI coding agents are changing how teams do code review. Tone: professional.

[Strategist] planning…
    🔧 knowledge_search(...)
    🔧 web_search(...)
[Strategist] plan ready — outline: 5 sections, keywords: 7, tone: professional, confident

============================================================
📋 CONTENT PLAN — awaiting your approval
============================================================
  target_audience: Senior software engineers on LinkedIn
  tone: professional, confident
  outline:
    • Why AI coding agents now make it into review loops
    • Where they help most: triage, style, obvious bugs
    ...

👉 approve / revise: approve

[Writer] iteration 1/5…
    🔧 web_search(...)
[Writer] draft ready — 412 words, keywords used: 7/7

[Editor] reviewing…
[Editor] verdict: APPROVED — tone=0.90 acc=0.85 struct=0.90

[Save] output/write-a-400-word-linkedin-post-for-senior-software-engineers-about-why.md
```

## Тести

```bash
pytest tests/ -v                # усі 4 сценарії
pytest tests/test_editor.py -v  # один файл
```

Кожен тест виконує компонент на golden-сценарії й валідує результат через `judge()` — окремий LLM-виклик з рубрикою (поріг `score >= 0.7`). Judge-виклики обгорнуті `@observe` → видно в Langfuse з тегом `eval` окремо від продакшн-трейсів.

| Файл | Що тестується |
|---|---|
| [test_strategist.py](tests/test_strategist.py) | plan відповідає audience / tone / channel з брифу |
| [test_writer.py](tests/test_writer.py) | draft покриває всі пункти outline + заявлені keywords є в тексті |
| [test_editor.py](tests/test_editor.py) | Editor rejects off-topic/off-tone draft, scores ≤ 0.5, issues ≥ 2 |
| [test_e2e.py](tests/test_e2e.py) | повний прогін `strategist → writer ↔ editor → save` |

## Observability

- **Один бриф = один trace** у Langfuse, зібраний через `@observe(name="content-pipeline-turn")` в `main.py`.
- **`propagate_attributes`** прокидає `session_id` (один на REPL-сесію), `user_id`, та tags `["course-project","content-pipeline"]` на все дерево trace'а.
- **`CallbackHandler`** з `langfuse.langchain` під'єднано до LangGraph через `config["callbacks"]` — усі LLM-виклики, tool calls, node-переходи автоматично стають spans'ами.
- **Evaluators** налаштовані в Langfuse UI на `target = New traces`, sampling 100% — нові trace'и оцінюються автоматично без змін коду.

## Відповідність вимогам `project_content.md`

- [x] 3 агенти: Strategist / Writer / Editor з мінімальним набором інструментів
- [x] Structured Output через Pydantic (`ContentPlan`, `DraftContent`, `EditFeedback`)
- [x] RAG для brand / style guide (hybrid retrieval + reranker)
- [x] HITL gate на затвердженні плану
- [x] Evaluator-Optimizer loop (Writer ↔ Editor), capped на `max_writer_iterations`
- [x] Command API для routing Editor → Writer із payload'ом
- [x] Langfuse tracing з input/output/latency/tokens + metadata (agent name, iteration, session)
- [x] Langfuse Prompt Management (жодного захардкодженого промпту в коді)
- [x] LLM-as-a-Judge evaluators у Langfuse (мінімум 2, різні score types)
- [x] Тести: 4 сценарії (Strategist, Writer, Editor, E2E) з LLM-as-a-Judge
- [ ] Демо (відео/GIF) — записується після фінального прогону
- [ ] Бонус: Google Drive MCP — додамо після основного pipeline
