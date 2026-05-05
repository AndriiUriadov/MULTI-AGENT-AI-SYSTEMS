# Курсовий проєкт — Конвеєр створення контенту

Мультиагентна система генерації контенту для соцмереж КПІ ім. Ігоря Сікорського.
**Content Strategist** планує, **Writer** пише, **Editor** рев'ює. LangGraph +
HITL на затвердженні плану + Evaluator-Optimizer loop Writer ↔ Editor.
Повна observability через Langfuse (tracing + Prompt Management + LLM-as-a-Judge).
Тести — pytest + власна `judge()` функція.

## Demo

Повний прогін pipeline'а на одному брифі (Facebook Physics про «1 Дірак») — від брифу через HITL revise/approve до збереженого посту, з переходом у Langfuse за спостережуваністю.

[![Watch the demo](https://img.youtube.com/vi/d8382ey__BI/hqdefault.jpg)](https://youtu.be/d8382ey__BI)

## Архітектура

**Патерни:** Prompt Chaining (Strategist → HITL → Writer) + Evaluator-Optimizer (Writer ↔ Editor).

```
             ┌──────────────┐       (Strategist re-plan)
 User brief ─►  Strategist   ◄─────────────────────────┐  
             └──────────────┘                          │
                    │ ContentPlan                      │ 
                    ▼                                  │
             ┌──────────────┐       revise + feedback. │
             │  HITL gate   │ ─────────────────────────┘
             └──────────────┘                          
                    │ approve                          
                    ▼                                  
             ┌──────────────┐                          
       ┌────►│   Writer     │◄─── REVISION_NEEDED ─┐   
       │     └──────────────┘                      │   
       │            │                              │   
       │            ▼                              │   
       │     ┌──────────────┐                      │   
       │     │   Editor     │──────────────────────┘   
       │     └──────────────┘  (iter < max_iter)       
       │            │                                  
       │   APPROVED або iter ≥ max_iter                
       │            ▼                                  
       │     ┌──────────────┐                          
       └─────│    save      │──► output/*.md    
             └──────────────┘
```

## Стек

- **LangGraph / LangChain** — граф, агенти (`create_agent` з `response_format=PydanticModel`), HITL через `interrupt()` + `Command(resume=...)`.
- **Pydantic** — контракти `ContentPlan` (з `word_count_target`), `DraftContent`, `EditFeedback` — див. [schemas.py](schemas.py).
- **Model Gateway** ([model_gateway.py](model_gateway.py)) — task → ChatOpenAI з LangChain `.with_fallbacks([...])` на `RateLimitError` / `APIError`.
- **Langfuse** — усі 4 system prompts у Prompt Management (label `production`, mustache variables), `@observe` + `propagate_attributes` для session/user/tags, 3 evaluator'и різних типів (numeric / boolean / categorical).
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
│   ├── test_strategist.py
│   ├── test_writer.py
│   ├── test_editor.py
│   └── test_e2e.py
├── data/
│   ├── style/               # KPI Social Media Style Guide (PDF, 20 стор.)
│   ├── examples/            # Референсні дописи за платформами (PDF)
│   └── brand/               # brand.md: місія, продукт, аудиторії, переваги
├── index/                   # FAISS + BM25 після ingest (152 chunks із 37 docs)
├── output/                  # Артефакти pipeline (саме тут Writer зберігає фінальні .md)
└── screenshots/             # Скріншоти Langfuse UI
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

Скорочений фрагмент — HITL з одним revise, approve, один прохід Writer, Editor з APPROVED. Повний лог — у [terminal.out](terminal.out).

```
Brief: Напиши пост для Facebook в стилі Facebook Physics про одиницю виміру 1 Дірак…

[Strategist] planning…
    🔧 knowledge_search({"query": "Facebook Physics tone audience voice"})
    🔧 web_search({"query": "1 Dirac unit measurement"})
    🔧 read_url({"url": "https://en.wikipedia.org/wiki/Dirac_measure"})
    🔧 ContentPlan(outline=["Вступ: Що таке одиниця виміру 1 Дірак?", …])
[Strategist] plan ready — outline: 5 sections, keywords: 5, tone: теплий, гумористичний

📋 CONTENT PLAN — awaiting your approval
  outline: • Вступ… • Історія виникнення… • Застосування в фізиці…
  keywords: • 1 Дірак • Дірак-міра • Діраковська дельта-функція …

👉 approve / revise: revise
✏️  What to change: Ця гумористична одиниця зʼявилася із-за того, що Пол Дірак був дуже мовчазним

[Strategist] planning…   ← переплановує з урахуванням feedback'а
    📎 [read_url] Paul Dirac, one of the most famous scientists of the 20th century, was a very quiet man…
    🔧 ContentPlan(outline=["Вступ: Хто такий Пол Дірак?", "Історії з життя: мовчазний геній", …])
[Strategist] plan ready — outline: 5 sections, keywords: 5, tone: теплий, гумористичний

👉 approve / revise: approve

[Writer] iteration 1/3…
[Writer] draft ready — 224 words, keywords used: 5/5

[Editor] reviewing…
    🔧 EditFeedback(verdict=APPROVED, tone=1.0, accuracy=1.0, structure=1.0)
[Editor] verdict: APPROVED — tone=1.00 acc=1.00 struct=1.00

[Save] Content saved to output/facebook-facebook-physics-1-150.md
```

Фінальний пост — [output/facebook-facebook-physics-1-150.md](output/facebook-facebook-physics-1-150.md).

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

## Інженерні рішення

| Рішення | Чому саме так |
|---|---|
| `max_writer_iterations = 3` (а не 5, як у спеці) | Writer дрейфить у формальний article-style після 3+ revisions; коротший loop = якісніший фінальний драфт |
| Fallback-гілки у всіх агентах | `GraphRecursionError` / `RateLimitError` / `StructuredOutputValidationError` → повертаємо conservative default замість хард-fail; pipeline завжди доходить до save |
| `BAAI/bge-reranker-v2-m3` замість `base` | Корпус українською — base-reranker оптимізований під англ./кит., multilingual v2-m3 дає правильний ranking |
| Editor `accuracy_score = 1.0` при відсутності claims | Інакше lifestyle/promo-контент блокується назавжди: editor ставить 0.5 «не можу верифікувати» + verdict rule «all ≥ 0.75» → infinite loop |
| `word_count_target` у `ContentPlan` | Без цього Writer не знає обсягу з брифу — писав article-length на Instagram (378 слів замість 200) |
| Multilingual prompts + LANGUAGE RULE | `gpt-4o` без explicit rule переходив на англійську в outline, хоча бриф був українською |

## Відповідність вимогам `project_content.md`

- 3 агенти Strategist / Writer / Editor з мінімальним набором інструментів (DuckDuckGo, RAG, file system)
- Structured Output через Pydantic (`ContentPlan`, `DraftContent`, `EditFeedback`)
- RAG для brand / style guide / examples (hybrid retrieval + multilingual reranker)
- HITL gate на затвердженні плану
- Evaluator-Optimizer loop Writer ↔ Editor, capped на `max_writer_iterations`
- Command API для routing Editor → Writer із payload'ом (`Command(goto=, update=)`)
- Langfuse tracing: input/output/latency/tokens + metadata (agent, iteration, session)
- Langfuse Prompt Management — жодного захардкодженого system prompt у коді
- LLM-as-a-Judge evaluators у Langfuse (numeric, boolean, categorical)
- 4 pytest-тести з LLM-as-a-Judge (Strategist / Writer / Editor / E2E)
- Model Gateway з fallback'ами (LangChain `.with_fallbacks`)
- Демо — [YouTube](https://youtu.be/d8382ey__BI) (повний прогін pipeline'а на брифі Facebook Physics про «1 Дірак»)
- Скріншоти Langfuse — 5 файлів у [screenshots/](screenshots/)
