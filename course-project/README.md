# Курсовий проєкт — Конвеєр створення контенту

Мультиагентна система генерації контенту для соцмереж КПІ ім. Ігоря Сікорського.
**Content Strategist** планує, **Writer** пише, **Editor** рев'ює. LangGraph +
HITL на затвердженні плану + Evaluator-Optimizer loop Writer ↔ Editor.
Повна observability через Langfuse (tracing + Prompt Management + LLM-as-a-Judge).
Тести — pytest + власна `judge()` функція.

## Demo

Повний прогін pipeline'а на одному брифі (Facebook Physics про «1 Дірак») — від брифу через HITL revise/approve до збереженого посту, з переходом у Langfuse за спостережуваністю.

[![Watch the demo](https://img.youtube.com/vi/d8382ey__BI/hqdefault.jpg)](https://youtu.be/d8382ey__BI)

Сценарій запису — [scenario.md](scenario.md).

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
       │     └──────────────┘  (iter < max_iter)       │
       │            │                                  │
       │   APPROVED або iter ≥ max_iter                │
       │            ▼                                  │
       │     ┌──────────────┐                          │
       └─────│    save      │──► output/*.md   ◄───────┘ (Strategist re-plan)
             └──────────────┘
```

`max_writer_iterations = 3` ([config.py](config.py)) — спец дозволяє до 5,
ми тримаємо коротший loop, щоб Writer не дрейфив у формальну прозу після
кількох revisions. Editor повертає REVISION_NEEDED ще раз — save забирає
останній чорновик, `[Editor] max iterations reached` логується як warning.

## Стек

- **LangGraph / LangChain** — граф, агенти (`create_agent` з `response_format=PydanticModel`), HITL через `interrupt()` + `Command(resume=...)`.
- **Pydantic** — контракти `ContentPlan` (з `word_count_target`), `DraftContent`, `EditFeedback` — див. [schemas.py](schemas.py).
- **Model Gateway** ([model_gateway.py](model_gateway.py)) — task → ChatOpenAI з LangChain `.with_fallbacks([...])` на `RateLimitError` / `APIError`.
- **Langfuse** — усі 4 system prompts у Prompt Management (label `production`, mustache variables), `@observe` + `propagate_attributes` для session/user/tags, 2–3 evaluator'и (numeric / boolean / categorical).
- **RAG** — FAISS + BM25 (50/50 ensemble) + `BAAI/bge-reranker-v2-m3` (мультимовний) для бренд-корпусу КПІ.
- **Tests** — pytest з власним LLM-as-a-Judge helper у [tests/judge.py](tests/judge.py).

## Структура

```
course-project/
├── config.py                # Settings + load_prompt() (Langfuse)
├── model_gateway.py         # task → ChatOpenAI з fallbacks
├── schemas.py               # ContentPlan, DraftContent, EditFeedback
├── tools.py                 # web_search, read_url, knowledge_search, save_content
├── retriever.py             # hybrid RAG (FAISS + BM25 + bge-reranker-v2-m3)
├── ingest.py                # build index from data/
├── agents/
│   ├── strategist.py        # + graceful fallback
│   ├── writer.py            # + graceful fallback
│   └── editor.py            # + graceful fallback
├── graph.py                 # LangGraph: nodes + HITL + Evaluator-Optimizer
├── main.py                  # REPL + Langfuse session wrapping
├── tests/
│   ├── judge.py             # спільна LLM-as-a-Judge функція (@observe tag=eval)
│   ├── goldens.py           # КПІ-тестові брифи
│   ├── test_strategist.py   # ✅ gpt-4o  ~18s
│   ├── test_writer.py       # ✅ gpt-4o  ~25s
│   ├── test_editor.py       # ✅ gpt-4o  ~8s
│   └── test_e2e.py          # ✅ gpt-4o  ~6min
├── data/
│   ├── style/               # KPI Social Media Style Guide (PDF, 20 стор.)
│   ├── examples/            # Референсні дописи за платформами (PDF)
│   └── brand/               # brand.md: місія, продукт, аудиторії, переваги
├── index/                   # FAISS + BM25 після ingest (152 chunks із 37 docs)
├── output/                  # Артефакти pipeline (саме тут Writer зберігає фінальні .md)
└── screenshots/             # Скріншоти Langfuse UI (заповнити перед здачею)
```

## Запуск

```bash
cd course-project
pip install -r requirements.txt
cp .env.example .env         # і заповнити значення
python ingest.py             # RAG індекс з data/ → index/  (одноразово)
python main.py               # REPL
```

Перед першим запуском **налаштуй Langfuse через UI**: створи проєкт, LLM Connection,
4 prompts (`strategist_system`, `writer_system`, `editor_system`, `judge_system`)
з label `production`, 2–3 evaluator'и. Без цього код впаде на `load_prompt()` з
`404 prompt not found`. Готовий текст промптів — у локальному `LANGFUSE_SETUP.md`
(не комітиться, `LANGFUSE_*` у `.gitignore`).

### `.env`

```
API_KEY=sk-...

# Model gateway — per-task моделі + fallback-ланцюг.
# gpt-4o-mini ігнорує HARD TOOL BUDGET у агентах: gpt-4o потрібен для
# Strategist / Writer / Editor, інакше recursion-loop + fallback-гілки.
# Judge лишаємо на gpt-4o-mini — внутрішнє оцінювання score'ів толерантне.
MODEL_STRATEGIST=gpt-4o
MODEL_WRITER=gpt-4o
MODEL_EDITOR=gpt-4o
MODEL_JUDGE=gpt-4o-mini
FALLBACK_MODELS=gpt-4o-mini,gpt-4o

# Langfuse (us.cloud.langfuse.com)
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=https://us.cloud.langfuse.com
LANGFUSE_USER_ID=your-id
```

## Приклад прогону

```
Brief: Напиши короткий пост для Instagram (формат опису під Reels) акаунту
КПІ ім. Ігоря Сікорського про щорічну подію «Дослідник року 2026».
Цільова аудиторія: нинішні студенти КПІ та старшокласники-абітурієнти.
Обсяг: 150–220 слів. Тон: теплий, з почуттям спільноти, природний. Українською.

[Strategist] planning…
    🔧 knowledge_search(...)    ← 1 запит у RAG (бренд тон/аудиторія)
    🔧 web_search(...)          ← 1 запит у DuckDuckGo
[Strategist] plan ready — outline: 5 sections, keywords: 7, tone: теплий, з почуттям спільноти

============================================================
📋 CONTENT PLAN — awaiting your approval
============================================================
  target_audience: Нинішні студенти КПІ та старшокласники-абітурієнти
  tone: теплий, з почуттям спільноти, природний
  outline:
    • Вступ: Що таке «Дослідник року 2026»
    • Історія та значення події для КПІ
    • Основні моменти цьогорічної події
    • Як взяти участь або відвідати
    • Заклик до дії: приєднуйтесь до спільноти дослідників
  keywords:
    • Дослідник року 2026
    • КПІ ім. Ігоря Сікорського
    ...

👉 approve / revise: approve

[Writer] iteration 1/3…
    🔧 web_search(...)
[Writer] draft ready — 214 words, keywords used: 7/7

[Editor] reviewing…
[Editor] verdict: APPROVED — tone=1.00 acc=0.50 struct=1.00

[Save] output/instagram-reels-2026-150-220.md
```

Фінальний Markdown лежить у [output/instagram-reels-2026-150-220.md](output/instagram-reels-2026-150-220.md).

## Тести

```bash
pytest tests/ -v                     # усі 4 сценарії
pytest tests/test_editor.py -v       # один файл
```

Кожен тест виконує компонент на golden-сценарії і валідує результат через
`judge()` — окремий LLM-виклик з рубрикою. Judge-виклики обгорнуті `@observe`
з тегом `eval` → видно в Langfuse окремо від продакшн-трейсів.

| Файл | Сценарій | Threshold judge | Тип моделі |
|---|---|---|---|
| [test_strategist.py](tests/test_strategist.py) | LinkedIn-анонс запуску наносупутника PolyITAN-HP-30 на Falcon 9 — план має бути укр., target audience = міжнародні партнери, tone офіційний | 0.7 | gpt-4o |
| [test_writer.py](tests/test_writer.py) | Фіксований план → draft покриває всі 5 секцій outline + усі 5 keywords (stem-tolerant до укр. відмінювання) | 0.7 | gpt-4o |
| [test_editor.py](tests/test_editor.py) | Катастрофічно поганий draft («йоу фам 🚀 КПІ ЛІТАЄ В КОСМОС») → Editor видає REVISION_NEEDED, scores ≤ 0.5, issues ≥ 2 | 0.7 | gpt-4o |
| [test_e2e.py](tests/test_e2e.py) | Повний прогін: Instagram Reels про «Дослідник року 2026», auto-approve HITL, Writer↔Editor, save | 0.6 (composite variance) | gpt-4o |

## Observability

- **Один бриф = один trace** у Langfuse через `@observe(name="content-pipeline-turn")` в [main.py](main.py).
- **`propagate_attributes`** прокидає `session_id` (один на REPL-сесію), `user_id`, tags `["course-project","content-pipeline"]` на все дерево trace'а.
- **`CallbackHandler`** з `langfuse.langchain` під'єднано до LangGraph через `config["callbacks"]` — усі LLM-виклики, tool calls, node-переходи автоматично стають spans'ами з input/output/latency/tokens.
- **Evaluators** налаштовані в Langfuse UI на `target = New traces`, sampling 100% — нові trace'и оцінюються автоматично без змін коду.
- **Judge-виклики** (тести) теж трейсяться, але з тегом `eval` — легко відфільтрувати від продакшн-трейсів.

## Інженерні рішення — корисно знати

| Рішення | Чому саме так |
|---|---|
| `max_writer_iterations = 3` (а не 5, як у спеці) | Writer дрейфить у формальний article-stiлль після 3+ revisions; коротший loop = якісніший фінальний драфт |
| Fallback-гілки у всіх агентах | `GraphRecursionError` / `RateLimitError` / `StructuredOutputValidationError` → повертаємо conservative default замість хард-fail; pipeline завжди доходить до save |
| `BAAI/bge-reranker-v2-m3` замість `base` | Корпус українською — base-reranker оптимізований під англ./кит., multilingual v2-m3 дає правильний ranking |
| Editor `accuracy_score = 1.0` при відсутності claims | Інакше lifestyle/promo-контент блокується назавжди: editor ставить 0.5 «не можу верифікувати» + verdict rule «all ≥ 0.75» → infinite loop |
| `word_count_target` у `ContentPlan` | Без цього Writer не знає обсягу з брифу — писав article-length на Instagram (378 слів замість 200) |
| Multilingual prompts + LANGUAGE RULE | `gpt-4o` без explicit rule переходив на англійську в outline, хоча бриф був українською |

## Відповідність вимогам `project_content.md`

- [x] 3 агенти Strategist / Writer / Editor з мінімальним набором інструментів (DuckDuckGo, RAG, file system)
- [x] Structured Output через Pydantic (`ContentPlan`, `DraftContent`, `EditFeedback`)
- [x] RAG для brand / style guide / examples (hybrid retrieval + multilingual reranker)
- [x] HITL gate на затвердженні плану
- [x] Evaluator-Optimizer loop Writer ↔ Editor, capped на `max_writer_iterations`
- [x] Command API для routing Editor → Writer із payload'ом (`Command(goto=, update=)`)
- [x] Langfuse tracing: input/output/latency/tokens + metadata (agent, iteration, session)
- [x] Langfuse Prompt Management — жодного захардкодженого system prompt у коді
- [x] LLM-as-a-Judge evaluators у Langfuse (numeric, boolean, categorical)
- [x] 4 pytest-тести з LLM-as-a-Judge (Strategist / Writer / Editor / E2E)
- [x] Model Gateway з fallback'ами (LangChain `.with_fallbacks`)
- [x] Демо — [YouTube](https://youtu.be/d8382ey__BI) (повний прогін pipeline'а на брифі Facebook Physics про «1 Дірак»)
- [x] Скріншоти Langfuse — 5 файлів у [screenshots/](screenshots/)
- [ ] Бонус: Google Drive MCP — опційно в кінці
