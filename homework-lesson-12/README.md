# Homework Lesson 12 — MAS з Langfuse Observability

Розширення системи з `homework-lesson-8` (Plan -> Research -> Critique + HITL) через **Langfuse**:

- **Tracing** — кожен запуск створює trace з повним деревом суб-агентів і tool calls
- **Session / User tracking** — трейси згруповані в сесію, мають `user_id`
- **Prompt Management** — усі 4 system prompts винесені в Langfuse; у коді жодного хардкоду
- **LLM-as-a-Judge** — 3 evaluator'и автоматично оцінюють кожен новий trace

## Що реалізовано

### Архітектура

```
User (REPL: main.py)
  │
  ▼
Supervisor Agent  ← InMemorySaver + HumanInTheLoopMiddleware
  │
  ├── 1. plan(request)       → Planner Agent   → ResearchPlan (Pydantic)
  │
  ├── 2. research(plan)      → Research Agent  → [web_search, read_url, knowledge_search]
  │
  ├── 3. critique(findings)  → Critic Agent    → CritiqueResult (Pydantic)
  │         │
  │         ├── verdict: APPROVE → перейти до кроку 4
  │         └── verdict: REVISE  → повернутись до кроку 2 (max 2 раунди)
  │
  └── 4. save_report(...)    → HITL: approve / edit / reject
```

**Ключові патерни:**
- **Evaluator-optimizer loop** : Critic може повернути дослідника на доопрацювання з конкретним зворотним зв'язком
- **Structured output** : Planner і Critic повертають валідовані Pydantic-моделі через `response_format`
- **Human-in-the-Loop** : `HumanInTheLoopMiddleware` перехоплює `save_report` до запису, дозволяючи approve / edit / reject

### Файлова структура

```
homework-lesson-12/
├── main.py              # REPL з HITL + Langfuse @observe / propagate_attributes / CallbackHandler
├── supervisor.py        # Supervisor + @tool-обгортки sub-агентів; system_prompt з Langfuse
├── agents/
│   ├── planner.py       # Planner Agent — system_prompt з Langfuse
│   ├── research.py      # Research Agent — system_prompt з Langfuse
│   └── critic.py        # Critic Agent  — system_prompt з Langfuse
├── schemas.py           # Pydantic: ResearchPlan, CritiqueResult
├── tools.py             # web_search, read_url, knowledge_search, save_report
├── retriever.py         # Hybrid FAISS+BM25+reranker (з lesson-5)
├── ingest.py            # PDF → FAISS index (з lesson-5)
├── config.py            # Settings + load_prompt(name, **vars) helper (жодних захардкоджених промптів)
├── screenshots/         # 4 скріншоти з Langfuse UI (trace tree, session, evaluator scores, prompts)
└── requirements.txt
```

### Схеми (schemas.py)

```python
class ResearchPlan(BaseModel):
    goal: str
    search_queries: list[str]
    sources_to_check: list[Literal["knowledge_base", "web"]]
    output_format: str

class CritiqueResult(BaseModel):
    verdict: Literal["APPROVE", "REVISE"]
    is_fresh: bool
    is_complete: bool
    is_well_structured: bool
    strengths: list[str]
    gaps: list[str]
    revision_requests: list[str]
```

### HITL (Human-in-the-Loop)

```
⏸️  ACTION REQUIRES APPROVAL
  Tool: save_report
  File: rag_overview.md
  --- Report preview ---
  # Overview of RAG...
  ---
 approve / edit / reject:
  approve  -> зберегти як є
  edit     -> ввести feedback -> Supervisor переробляє -> новий HITL
  reject   -> скасувати збереження
```

## Запуск

```bash
pip install -r requirements.txt

# Побудувати індекс (якщо немає — або скопіювати з lesson-5/index/)
python ingest.py

# ПЕРЕД першим запуском: налаштувати Langfuse UI (4 промпти, 3 evaluator'и, LLM connection)

# Запустити систему
python main.py
```

`.env`:

```
API_KEY=my-super-secret-openai-api-key
MODEL_NAME=gpt-4o-mini

LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=https://cloud.langfuse.com     # або https://us.cloud.langfuse.com
LANGFUSE_USER_ID=my-user-id
```

## Langfuse Observability

### Tracing

Кожен REPL-turn обгортається в `@observe(name="supervisor-turn")` з `propagate_attributes(session_id, user_id, tags)`. `CallbackHandler` переданий через `RunnableConfig.callbacks` автоматично вкладає всі LangGraph-спани (Supervisor, Planner, Research, Critic + tool calls) в один trace-дерево. У Langfuse UI → **Tracing → Traces** кожен рядок розгортається у повну ієрархію.

### Session / User

`SESSION_ID = f"hw12-{uuid.uuid4().hex[:8]}"` генерується на старті `main.py` — усі turns одного запуску згруповані в одну сесію. `user_id` береться з `LANGFUSE_USER_ID` (`.env`). Перевірка: вкладки **Sessions** і **Users** у Langfuse UI.

### Prompt Management

Промпти `supervisor_system`, `planner_system`, `researcher_system`, `critic_system` живуть у Langfuse з label `production`. Код завантажує їх через `config.load_prompt(name, **vars)` — жодного захардкодженого промпту в `*.py`. Supervisor-промпт параметризований `{{max_revisions}}` і компілюється значенням з `Settings.max_revisions`. Зміна промпту в UI → рестарт процесу → нова версія в силі (без редеплою коду).

### LLM-as-a-Judge (3 evaluator'и)

| Evaluator | Score type | Що перевіряє |
| --- | --- | --- |
| `answer_relevance` | numeric 0–1 | наскільки фінальний репорт відповідає початковому запиту |
| `groundedness` | boolean | чи підкріплені факти цитатами на джерела (no hallucination) |
| `research_completeness` | categorical (`thorough` / `adequate` / `shallow`) | глибина дослідження |

Всі три налаштовані на Target = "New traces", sampling 100% — оцінка відбувається автоматично через 1–2 хв після завершення trace. Перевірка: trace → вкладка **Scores**.

## Реальний приклад роботи

Сесія `hw12-cc94d0d1` з двома турами. Повний вивід терміналу: [`terminal.out`](terminal.out).

```
============================================================
  Multi-Agent Research System  (homework-lesson-12)
  Langfuse session: hw12-cc94d0d1
  Type 'quit' or 'exit' to stop.
============================================================
  Loading retriever model… ready.

You: What is a chain in LangChain?

  🔧 plan({"request": "Explain what a chain is in LangChain, including its purpose, types of chains, and examples of how it is used."})
    🔧 knowledge_search({"query": "what is a chain in LangChain, purpose and types of chains"})
    🔧 web_search({"query": "LangChain chain types examples"})
    📎 [knowledge_search] [1] Source: langchain.pdf, page 0 ...
    📎 [web_search] [{"title": "LangChain Expression Language", ...}]
  📎 [plan] {"goal": "Explain what a chain is in LangChain...", "search_queries": [...], ...}

  🔧 research({"request": "Research what a chain is in LangChain. Explain its purpose, types of chains, and provide examples..."})
    🔧 knowledge_search({"query": "what is a chain in LangChain"})
    🔧 web_search({"query": "LangChain chains purpose types examples"})
    🔧 read_url({"url": "https://www.comet.com/site/blog/chaining-the-future-..."})
    📎 [knowledge_search] [1] Source: langchain.pdf ...
  📎 [research] # Understanding Chains in LangChain ...

  🔧 critique({"findings": "..."})
    🔧 web_search({"query": "LangChain vs LangGraph comparison 2024"})
    🔧 knowledge_search({"query": "LangChain chain advancements"})
    📎 [web_search] [...] 📎 [knowledge_search] ...
  📎 [critique] {"verdict": "REVISE", "is_fresh": false, ...,
                 "revision_requests": ["Include recent LangChain vs LangGraph developments"]}

  🔧 research({"request": "Find 2024 benchmarks comparing LangChain and LangGraph..."})
  📎 [research] [REVISION LIMIT REACHED — 3 research rounds completed]
                You MUST now call save_report()...

============================================================
⏸️  ACTION REQUIRES APPROVAL
============================================================
  Tool: save_report
  File: understanding_chains_in_langchain.md

  --- Report preview ---
# Understanding Chains in LangChain

LangChain is a software framework designed to facilitate the integration of large
language models (LLMs) into various applications. One of its core features is the
concept of "chains," which allows developers to orchestrate multiple components...
  ---

👉 approve / edit / reject: approve
  📎 [save_report] Report saved to output/understanding_chains_in_langchain.md

Agent: The research report on "Understanding Chains in LangChain" has been successfully saved...

You: How does retrieval augmentation work?

  🔧 plan({"request": "Explain how retrieval augmentation works, focusing on its principles, applications..."})
  ...
  📎 [save_report] Report saved to output/retrieval_augmentation.md

You: exit
Bye!
```

**Збережені звіти цієї сесії:**

- [`output/understanding_chains_in_langchain.md`](output/understanding_chains_in_langchain.md)
- [`output/retrieval_augmentation.md`](output/retrieval_augmentation.md)

**Додатково в `output/` — з інших прогонів:**

- [`output/hybrid_retrieval_faiss_bm25.md`](output/hybrid_retrieval_faiss_bm25.md)
- [`output/model_context_protocol.md`](output/model_context_protocol.md)
- [`output/rag_vs_fine_tuning.md`](output/rag_vs_fine_tuning.md)

## Очікуваний результат (відповідність завданню)

1.  **Ingestion працює** — `python ingest.py` будує FAISS-індекс (52 стор., 462 чанки)
2.  **Planner декомпозує** — запит розбивається у структурований `ResearchPlan` з `goal`, `search_queries`, `sources_to_check`, `output_format`
3.  **Researcher виконує** — слідує плану, використовує `web_search`, `read_url`, `knowledge_search`
4.  **Critic оцінює** — повертає структурований `CritiqueResult` з `verdict`, `is_fresh`, `is_complete`, `is_well_structured`, `strengths`, `gaps`, `revision_requests`
5.  **Ітерація працює** — якщо Critic повертає `REVISE`, Researcher повторює з конкретним зворотним зв'язком (max 2 раунди, далі — примусовий перехід до збереження)
6.  **HITL працює** — при виклику `save_report` користувач бачить preview звіту і обирає дію
7.  **Звіт збережено** — після `approve` звіт зберігається у `./output/`

## Що нового порівняно з lesson-8

| Було (lesson-8) | Стало (lesson-12) |
| --- | --- |
| Жодного observability — чорна скринька | Langfuse tracing, повне дерево суб-агентів + tool calls у UI |
| Трейси ізольовані | Session + User tracking через `propagate_attributes` |
| Промпти захардкоджені в `config.py` | Promption Management в Langfuse; код тягне через `load_prompt()` |
| Якість перевіряється Critic-агентом у loop | Додатково — 3 автоматичні LLM-as-a-Judge evaluator'и на кожен trace |

## Що нового порівняно з lesson-5

| Було (lesson-5) | Стало (lesson-8) |
| --- | --- |
| Один агент з 4 інструментами | Supervisor + 3 спеціалізованих суб-агенти |
| Без оцінки якості | Critic перевіряє freshness / completeness / structure |
| Одноразове дослідження | Ітеративне: Critic повертає на доопрацювання |
| Збереження без підтвердження | HITL: approve / edit / reject перед записом |
| Вільний текст | Planner і Critic повертають валідовані Pydantic-моделі |

## Технічні деталі та особливості

### LangChain 1.x API
Завдання використовує нові API (підтверджено для `langchain==1.2.11`, `langgraph==1.1.0`):
- `from langchain.agents import create_agent` — замість `create_react_agent` з langgraph
- `from langchain.agents.middleware import HumanInTheLoopMiddleware`
- `response_format=PydanticModel` у `create_agent` — підтримується, повертає через `result["structured_response"]`

### Формат Interrupt/Resume
```python
# При interrupt:
chunk["__interrupt__"][0].value["action_requests"][0]["name"]  # ім'я інструменту
chunk["__interrupt__"][0].id                                    # для resume

# Resume:
Command(resume={interrupt.id: {"decisions": [{"type": "approve"}]}})
Command(resume={interrupt.id: {"decisions": [{"type": "reject",
    "message": "Please revise: feedback text"}]}})   # "edit" → reject з feedback
Command(resume={interrupt.id: {"decisions": [{"type": "reject",
    "message": "Not needed"}]}})
```

**Примітка щодо `edit`**: `EditDecision` у middleware очікує `edited_action: {"name": ..., "args": {...}}` — тобто повну заміну аргументів інструменту. Для сценарію «перепиши звіт на основі feedback» використовується `reject` з feedback-текстом як message. Supervisor бачить відхилений виклик і переписує звіт згідно з поясненням у повідомленні.

### Видимість викликів суб-агентів

Кожен суб-агент (planner, researcher, critic) використовує єдиний `invoke()`. Після завершення `result["messages"]` містить повну історію розмови, включно з усіма `AIMessage.tool_calls` та `ToolMessage`. Ці виклики друкуються з відступом 4 пробіли — рівень суб-агента під Supervisor-рівнем (2 пробіли):

```
  🔧 research(...)            ← Supervisor рівень
    🔧 knowledge_search(...)  ← Research Agent рівень
    📎 [knowledge_search] ... ← результат
```

### Спостережена поведінка LLM
1. **Critic майже завжди повертає REVISE** через перевірку freshness — навіть якщо знахідки якісні, він шукає новіші джерела і знаходить їх. Це нормальна поведінка активного верифікатора. Програмний ліміт у `research` tool (`ToolRuntime` підраховує попередні виклики) примусово зупиняє цикл після `max_revisions` раундів.

2. **Supervisor іноді викликає research двічі паралельно** після отримання повідомлення про ліміт — LangGraph обробляє обидва виклики, обидва повертають `[REVISION LIMIT REACHED]`, після чого Supervisor коректно переходить до `save_report`.

3. **InMemorySaver** — зберігає стан між HITL interrupt і resume в межах сесії. Втрачається при перезапуску `main.py`.
