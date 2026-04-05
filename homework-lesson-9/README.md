# Homework Lesson 9 - Мультиагентна система з MCP + ACP протоколами

Розширення `homework-lesson-8` до **повноцінної мікросервісної архітектури**: інструменти переїхали в MCP-сервери, суб-агенти — в ACP-сервер. Один термінал запускає все.

## Що реалізовано

### Архітектура

```
User (REPL: main.py)
  │
  ▼
Supervisor Agent  ← InMemorySaver + HumanInTheLoopMiddleware
  │   (sync, asyncio.run() для ACP/MCP викликів)
  │
  ├── 1. delegate_to_planner(request)   → ACP → Planner Agent  → ResearchPlan (Pydantic)
  │
  ├── 2. delegate_to_researcher(plan)   → ACP → Research Agent → [SearchMCP tools]
  │
  ├── 3. delegate_to_critic(findings)   → ACP → Critic Agent   → CritiqueResult (Pydantic)
  │         │
  │         ├── verdict: APPROVE → перейти до кроку 4
  │         └── verdict: REVISE  → повернутись до кроку 2 (max 2 раунди)
  │
  └── 4. save_report(...)    → ReportMCP → HITL: approve / edit / reject
```

**MCP-сервери:**
- **SearchMCP** (порт 8901) — `web_search`, `read_url`, `knowledge_search`, resource `knowledge-base-stats`
- **ReportMCP** (порт 8902) — `save_report`, resource `output-dir`

**ACP-сервер (порт 8903):**
- `planner` — `build_planner()` з `response_format=ResearchPlan`
- `researcher` — `build_researcher()`, повертає текст знахідок
- `critic` — `build_critic()` з `response_format=CritiqueResult`

### Файлова структура

```
homework-lesson-9/
├── main.py                      # REPL: запускає MCP+ACP сервери, HITL interrupt/resume
├── supervisor.py                # Supervisor + @tool-делегати через ACP/MCP
├── acp_server.py                # ACP-сервер з трьома агентами (planner/researcher/critic)
├── mcp_utils.py                 # mcp_tools_to_langchain(): MCP → LangChain StructuredTool
├── agents/
│   ├── planner.py               # build_planner(lc_tools)
│   ├── research.py              # build_researcher(lc_tools)
│   └── critic.py                # build_critic(lc_tools)
├── mcp_servers/
│   ├── search_mcp.py            # SearchMCP: web_search, read_url, knowledge_search
│   └── report_mcp.py            # ReportMCP: save_report
├── schemas.py                   # Pydantic: ResearchPlan, CritiqueResult
├── retriever.py                 # Hybrid FAISS+BM25+reranker (з lesson-5)
├── ingest.py                    # PDF → FAISS index (з lesson-5)
├── config.py                    # Settings + порти + system prompts
└── requirements.txt
```

### Ключові технічні рішення

**Sync Supervisor + async ACP/MCP:**
```python
# supervisor.py — sync @tool обгортає async виклик
@tool
def delegate_to_researcher(request: str, runtime: ToolRuntime) -> str:
    result = asyncio.run(_acp_call("researcher", request))
    return result

async def _acp_call(agent_name: str, text: str) -> str:
    async with ACPClient(base_url=ACP_BASE_URL, headers={"Content-Type": "application/json"}) as client:
        run = await client.run_sync(agent=agent_name,
            input=[Message(role="user", parts=[MessagePart(content=text)])])
    if not run.output:
        return f"[{agent_name} returned no output]"
    return run.output[-1].parts[0].content
```

**MCP tools → LangChain (mcp_utils.py):**
```python
for tool in mcp_tools:
    async def _invoke(_name=tool.name, _client=mcp_client, **kwargs):
        result = await _client.call_tool(_name, kwargs)
        return str(result.data)
    lc_tools.append(StructuredTool.from_function(coroutine=_invoke, name=tool.name, ...))
```

**ACP-агент відкриває MCP-з'єднання для кожного запиту:**
```python
@server.agent(name="researcher", ...)
async def researcher_handler(input: list[Message]) -> Message:
    async with Client(SEARCH_MCP_URL) as mcp_client:
        lc_tools = mcp_tools_to_langchain(await mcp_client.list_tools(), mcp_client)
        agent = build_researcher(lc_tools)
        result = await agent.ainvoke({"messages": [("user", user_text)]},
                                     config={"recursion_limit": 31})
    return Message(role="agent", parts=[MessagePart(content=result["messages"][-1].content)])
```

## Запуск

```bash
pip install -r requirements.txt

# Побудувати індекс (або скопіювати з lesson-5/index/ або lesson-8/index/)
python ingest.py

# Запустити всю систему одною командою
python main.py
```

`.env`:
```
API_KEY=my-super-secret-openai-api-key
MODEL_NAME=gpt-4o-mini
```

`main.py` автоматично запускає SearchMCP (8901), ReportMCP (8902) і ACP-сервер (8903) у фонових потоках.

## Реальний приклад роботи

Запит: *"порівняй RAG підходи: naive RAG vs modular RAG"*

Повний вивід терміналу: [`terminal.out`](terminal.out)

```
============================================================
  Multi-Agent Research System  (homework-lesson-9)
  MCP + ACP architecture
  Type 'quit' or 'exit' to stop.
============================================================
  Starting MCP servers and ACP server… ready.
  Loading retriever model… ready.

You: порівняй RAG підходи: naive RAG vs modular RAG

  🔧 delegate_to_planner({"request": "Compare RAG approaches: naive RAG vs modular RAG..."})
  🤖 [planner via ACP] ← Compare RAG approaches...
    🔧 knowledge_search({"query": "naive RAG modular RAG comparison"})
    🔧 web_search({"query": "naive RAG vs modular RAG academic papers"})
    📎 [knowledge_search] [1] Source: retrieval-augmented-generation.pdf, page 0...
    📎 [web_search] [...]
  📎 [delegate_to_planner] {"goal": "...", "search_queries": [...], ...}

  🔧 delegate_to_researcher({"request": "Research naive RAG vs modular RAG..."})
  🤖 [researcher via ACP] ← Research naive RAG vs modular RAG...
    🔧 web_search({"query": "naive RAG modular RAG comparison features"})
    🔧 knowledge_search({"query": "naive RAG modular RAG"})
    🔧 read_url({"url": "https://..."})
    📎 [web_search] [...] 📎 [knowledge_search] ... 📎 [read_url] ...
  📎 [delegate_to_researcher] # Comparison of RAG Approaches: Naive RAG vs. Modular RAG...

  🔧 delegate_to_critic({"findings": "..."})
  🤖 [critic via ACP]
    🔧 knowledge_search({"query": "latest RAG benchmarks 2024"})
    🔧 web_search({"query": "recent benchmarks 2024 RAG approaches naive vs modular"})
    📎 [knowledge_search] ... 📎 [web_search] ...
  📎 [delegate_to_critic] {"verdict": "REVISE", "is_fresh": false,
    "gaps": ["No recent benchmarks"], "revision_requests": ["Add 2024 metrics"]}

  🔧 delegate_to_researcher({"request": "Enhance with recent benchmarks 2024..."})
  🤖 [researcher via ACP] ← Enhance with recent benchmarks 2024...
    🔧 web_search({"query": "recent benchmarks 2024 RAG approaches naive vs modular"})
    🔧 knowledge_search({"query": "RAG approaches naive RAG vs modular RAG benchmarks 2024"})
    🔧 read_url({"url": "https://web.archive.org/..."})
    📎 [read_url] Q&A with RAG...
  📎 [delegate_to_researcher] # Comparison of RAG Approaches (enhanced)...

============================================================
⏸️  ACTION REQUIRES APPROVAL
============================================================
  Tool: save_report
  File: rag_comparison.md
  --- Report preview ---
  # Comparison of RAG Approaches: Naive RAG vs. Modular RAG...
  ---

👉 approve / edit / reject: edit
✏️  Your feedback: Add more specific examples and sources for each approach
  📎 [save_report] Please revise the report: Add more specific examples and sources for each approach

============================================================
⏸️  ACTION REQUIRES APPROVAL
============================================================
  Tool: save_report
  File: rag_comparison.md
  --- Report preview ---
  # Comparison of RAG Approaches: Naive RAG vs. Modular RAG (revised)...
  ---

👉 approve / edit / reject: approve
  📎 [save_report] Report saved to output/rag_comparison.md

Agent: The report has been saved to output/rag_comparison.md.
```

**Збережений звіт:**
- [`output/rag_comparison.md`](output/rag_comparison.md) — порівняння підходів RAG (з реального тесту)

## Очікуваний результат (відповідність завданню)

1. ✅ **MCP-сервери запускаються** — SearchMCP (8901) і ReportMCP (8902) стартують автоматично при `python main.py`
2. ✅ **ACP-сервер запускається** — три агенти (planner/researcher/critic) доступні на порту 8903
3. ✅ **Planner декомпозує через ACP** — `delegate_to_planner` → ACP call → `ResearchPlan` JSON
4. ✅ **Researcher використовує MCP tools** — `web_search`, `read_url`, `knowledge_search` через SearchMCP
5. ✅ **Critic оцінює через ACP** — `delegate_to_critic` → ACP call → `CritiqueResult` JSON з APPROVE/REVISE
6. ✅ **REVISE-ітерація працює** — Supervisor повертає Researcher на доопрацювання з конкретним feedback
7. ✅ **save_report через ReportMCP** — запис файлу виконується через MCP `save_report` tool
8. ✅ **HITL працює** — `save_report` перехоплюється middleware: approve / edit / reject
9. ✅ **edit → approve flow** — після edit Supervisor переписує звіт, другий HITL → approve → файл збережено

## Що нового порівняно з lesson-8

| Було (lesson-8) | Стало (lesson-9) |
|---|---|
| Sub-агенти викликаються напряму (`invoke()`) | Sub-агенти ізольовані в ACP-сервері (окремий процес) |
| Tools — звичайні Python-функції в `tools.py` | Tools — MCP endpoints на SearchMCP/ReportMCP |
| Один процес | Три сервери: SearchMCP, ReportMCP, ACP |
| Sub-агент отримує tools при побудові | Sub-агент запитує MCP tools при кожному зверненні |
| Прямий виклик Python-функції | ACP HTTP call → JSON response |

## Технічні деталі

### ACP Content-Type
ACP-клієнт **обов'язково** потребує заголовку `Content-Type: application/json`, інакше — 422:
```python
ACPClient(base_url=ACP_BASE_URL, headers={"Content-Type": "application/json"})
```

### Recursion limit
Плануваьник і дослідник потребують `recursion_limit=31` (мінімум) — кожен tool call займає 2 кроки в LangGraph.

### Sanitization pipeline
Scraped web content може містити control characters, які ламають JSON-серіалізацію OpenAI API. Кожен ACP handler санітизує вхідний текст:
```python
def _sanitize(text: str, max_len: int = 0) -> str:
    cleaned = "".join(c for c in text if c >= " " or c in "\n\t")
    if max_len and len(cleaned) > max_len:
        cleaned = cleaned[:max_len] + "\n\n[...truncated...]"
    return cleaned
```

### StructuredOutputValidationError в critic
Якщо OpenAI не може розпарсити structured output для `CritiqueResult`, `critic_handler` перехоплює `StructuredOutputValidationError` і повертає fallback REVISE — цикл продовжується, а не падає.
