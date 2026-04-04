# Homework Lesson 8 — Мультиагентна дослідницька система

Розширення Research Agent з `homework-lesson-5` до **мультиагентної системи** з патерном **Plan → Research → Critique** та Human-in-the-Loop контролем над збереженням звітів.

## Що реалізовано

### Архітектура

```
User (REPL: main.py)
  └── Supervisor Agent  ← InMemorySaver + HumanInTheLoopMiddleware
        ├── plan(request)      → Planner Agent   → ResearchPlan (Pydantic)
        ├── research(plan)     → Research Agent  → Markdown findings
        ├── critique(findings) → Critic Agent    → CritiqueResult (Pydantic)
        │      └── verdict=REVISE → повторний research (max 2 раунди)
        └── save_report(...)   → HITL: approve / edit / reject
```

**Ключові патерни:**
- **Evaluator-optimizer loop** — Critic може повернути дослідника на доопрацювання з конкретним зворотним зв'язком
- **Structured output** — Planner і Critic повертають валідовані Pydantic-моделі через `response_format`
- **Human-in-the-Loop** — `HumanInTheLoopMiddleware` перехоплює `save_report` до запису, дозволяючи approve / edit / reject

### Файлова структура

```
homework-lesson-8/
├── main.py          # REPL з HITL interrupt/resume
├── supervisor.py    # Supervisor + @tool-обгортки sub-агентів
├── agents/
│   ├── planner.py   # Planner Agent (response_format=ResearchPlan)
│   ├── research.py  # Research Agent (web + knowledge base)
│   └── critic.py    # Critic Agent (response_format=CritiqueResult)
├── schemas.py       # Pydantic: ResearchPlan, CritiqueResult
├── tools.py         # web_search, read_url, knowledge_search, save_report
├── retriever.py     # Hybrid FAISS+BM25+reranker (з lesson-5)
├── ingest.py        # PDF → FAISS index (з lesson-5)
├── config.py        # Settings + system prompts для всіх 4 агентів
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
👉 approve / edit / reject:
  approve  → зберегти як є
  edit     → ввести feedback → Supervisor переробляє → новий HITL
  reject   → скасувати збереження
```

## Запуск

```bash
pip install -r requirements.txt

# Побудувати індекс (якщо немає — або скопіювати з lesson-5/index/)
python ingest.py

# Запустити систему
python main.py
```

`.env`:
```
API_KEY=your-openai-api-key
MODEL_NAME=gpt-4o-mini
```

## Реальний приклад роботи

Запит: *"What is RAG? Write a short 1-paragraph report."*

```
🔧 plan({"request": "What is RAG?"})
📎 [plan] {"goal": "Provide a comprehensive understanding of RAG...",
           "search_queries": ["Overview of RAG", ...],
           "sources_to_check": ["knowledge_base", "web"], ...}

🔧 research({"request": "Provide a comprehensive understanding..."})
📎 [research] # Comprehensive Overview of RAG...

🔧 critique({"findings": "..."})
📎 [critique] {"verdict": "REVISE", "is_fresh": false,
               "gaps": ["No recent 2024-2025 benchmarks"],
               "revision_requests": ["Find current benchmarks"]}

🔧 research({"request": "...include specific benchmarks 2024-2025..."})
📎 [research] # Overview of RAG (updated with 2024-2025 data)...

🔧 critique({"findings": "..."})
📎 [critique] {"verdict": "APPROVE", "is_fresh": true, "is_complete": true, ...}

🔧 save_report({"filename": "rag_overview", "content": "..."})

⏸️  ACTION REQUIRES APPROVAL
  Tool: save_report  |  File: rag_overview.md

👉 approve / edit / reject: approve
📎 [save_report] Report saved to output/rag_overview.md

Agent: The research report has been successfully saved to output/rag_overview.md
```

**Збережений звіт:** [`output/rag_overview.md`](output/rag_overview.md)

## Що нового порівняно з lesson-5

| Було (lesson-5) | Стало (lesson-8) |
|---|---|
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
Command(resume={interrupt.id: {"decisions": [{"type": "edit",
    "edited_action": {"feedback": "Add a table"}}]}})
Command(resume={interrupt.id: {"decisions": [{"type": "reject",
    "message": "Not needed"}]}})
```

### Спостережена поведінка LLM
1. **Перший виклик `research` з dict замість str** — Supervisor спробував передати JSON-об'єкт `ResearchPlan` замість текстової інструкції. Виникла помилка, але Supervisor самостійно виправився і повторив виклик з коректним рядком. Система стійка до таких помилок.

2. **Critic завжди активно верифікує** — не просто переглядає текст, а виконує власні `web_search` виклики для перевірки актуальності даних.

3. **InMemorySaver** — зберігає стан між HITL interrupt і resume в межах сесії. Втрачається при перезапуску `main.py`.
