# Курсовий проєкт: Конвеєр створення контенту

Реалізація відповідає `project_content.md`. Патерни: **Prompt Chaining** (Strategist → Writer) + **Evaluator-Optimizer** (Writer ↔ Editor). HITL gate між Strategist та Writer. Model Gateway з fallback'ами. Langfuse для трейсингу + Prompt Management + LLM-as-a-Judge. Тести — pytest + власна LLM judge-функція.

---

## 1. Стек

- **Python 3.11+**
- `langgraph`, `langchain`, `langchain-openai` — граф, агенти, LLM
- `pydantic`, `pydantic-settings` — схеми + `.env`
- `langfuse>=3.0` — tracing + Prompt Management + evaluators
- `duckduckgo-search`, `trafilatura` — web search + fetch
- `faiss-cpu`, `rank-bm25`, `sentence-transformers` — RAG (hybrid + rerank, як у hw-5/8)
- `pytest`, `pytest-asyncio` — тести
- **Бонус:** `mcp` (Google Drive MCP) — збереження approved контенту

## 2. Структура файлів

```
course-project/
├── .env.example
├── .gitignore
├── requirements.txt
├── config.py                  # Settings + load_prompt() (Langfuse)
├── model_gateway.py           # NEW — task→model router з fallback
├── schemas.py                 # ContentPlan, DraftContent, EditFeedback
├── tools.py                   # web_search, read_url, knowledge_search, save_content
├── retriever.py               # RAG (FAISS + BM25 + reranker) — як у hw-8
├── ingest.py                  # build index from data/ (style guide, examples, brand)
├── agents/
│   ├── __init__.py
│   ├── strategist.py          # ContentPlan
│   ├── writer.py              # DraftContent
│   └── editor.py              # EditFeedback
├── graph.py                   # LangGraph: nodes + edges + HITL + Command routing
├── main.py                    # REPL + Langfuse session wrapping + HITL handler
├── tests/
│   ├── conftest.py
│   ├── judge.py               # спільна LLM-as-a-Judge функція
│   ├── goldens.py             # тестові брифи та очікування
│   ├── test_strategist.py
│   ├── test_writer.py
│   ├── test_editor.py
│   └── test_e2e.py
├── data/                      # RAG корпус (style guide, brand, examples) — DEFERRED
├── index/                     # FAISS + BM25 після ingest
├── output/                    # фінальні .md артефакти від Writer
├── screenshots/               # Langfuse UI (trace tree, session, evaluators, prompts)
├── plan-course.md             # цей файл
└── README.md
```

## 3. Model Gateway

`model_gateway.py`:

```python
# Settings fields (за замовчуванням всі gpt-4o-mini):
#   model_strategist, model_writer, model_editor, model_judge
#   fallback_models: list[str] = ["gpt-4o-mini", "gpt-4o"]
#
# def get_chat_model(task: Literal["strategist","writer","editor","judge"]) -> BaseChatModel:
#     primary = settings.get_model_for(task)
#     return _build_with_fallback(primary, settings.fallback_models)
#
# _build_with_fallback(primary, fallbacks) повертає ChatOpenAI(primary)
#   обгорнутий .with_fallbacks([ChatOpenAI(f) for f in fallbacks])
#   → LangChain сам перемикне на наступну модель при RateLimitError
```

Плюси: уніфікований entrypoint у коді, легко додати Anthropic/Gemini (через `init_chat_model` з LangChain або окремі factory-функції), ретраї «безкоштовно» від LangChain.

## 4. Pydantic схеми (`schemas.py`)

```python
class ContentPlan(BaseModel):
    outline: list[str]
    keywords: list[str]
    key_messages: list[str]
    target_audience: str
    tone: str

class DraftContent(BaseModel):
    content: str              # Markdown
    word_count: int
    keywords_used: list[str]

class EditFeedback(BaseModel):
    verdict: Literal["APPROVED", "REVISION_NEEDED"]
    issues: list[str]
    tone_score: float         # 0..1
    accuracy_score: float
    structure_score: float
```

## 5. Tools (`tools.py`)

- `web_search(query: str)` — DuckDuckGo, top-k результатів (як hw-8).
- `read_url(url: str)` — trafilatura, truncate до `max_url_content_length`.
- `knowledge_search(query: str)` — RAG (Strategist). Читає з `index/`.
- `save_content(filename: str, content: str)` — пише у `output/<filename>.md`. **Викликається лише з Writer, після APPROVED.**
- **Бонус:** `save_to_gdrive(filename, content)` через Google Drive MCP (додамо в кінці).

## 6. RAG (`retriever.py`, `ingest.py`)

Код перетягуємо з hw-8 **1-в-1** (FAISS + BM25, 50/50 ensemble, `BAAI/bge-reranker-base`). Підміняємо лише вхідні дані.

**Дані — DEFERRED.** Поки інший агент готує style guide / brand / приклади, пишемо код так, щоб `knowledge_search` міг запуститися на порожньому корпусі (заглушка: якщо `index/` немає — повертаємо `"(knowledge base not available)"`, щоб тести не падали). Коли дані з'являться — `python ingest.py`.

## 7. LangGraph (`graph.py`)

**Ноди:**

1. `strategist_node` — викликає Strategist Agent, кладе `ContentPlan` у state.
2. `hitl_gate` — `interrupt()` з серіалізованим планом; resume через `Command(resume=decision)`.
3. `writer_node` — викликає Writer Agent, кладе `DraftContent` у state.
4. `editor_node` — викликає Editor Agent, кладе `EditFeedback` у state.
5. `route_after_editor` — conditional edge: `APPROVED` або `iteration ≥ 5` → END (спочатку `save_content`), інакше → `writer_node` (через `Command(goto="writer_node", update={...})`).

**State (`TypedDict`):**

```python
class GraphState(TypedDict):
    brief: dict                      # topic, audience, channel, tone, word_count
    plan: Optional[ContentPlan]
    plan_feedback: Optional[str]     # від user, якщо REVISE
    draft: Optional[DraftContent]
    feedback: Optional[EditFeedback]
    iteration: int
    messages: list                   # для трейсингу
```

**HITL gate (Strategist):**
- `interrupt({"plan": plan.model_dump()})` перед переходом до Writer.
- Resume options: `{"type": "approve"}` | `{"type": "revise", "feedback": "..."}`.
- `revise` → повернення в `strategist_node` з `plan_feedback` у state.

**Evaluator-Optimizer loop (Writer ↔ Editor):**
- Editor повертає `EditFeedback`; `route_after_editor` читає `verdict` + `iteration`.
- `REVISION_NEEDED` + `iteration < 5` → `Command(goto="writer_node", update={"iteration": iteration+1, "feedback": feedback, "draft": draft})`.
- Writer у наступному виклику бачить `feedback` та попередній `draft` — переписує з урахуванням issues.

**Checkpointer:** `InMemorySaver` (обов'язковий для HITL як у hw-8).

## 8. Агенти (`agents/`)

Кожен агент — `create_agent(model, tools=..., system_prompt=load_prompt("name"), response_format=PydanticModel)`:

- **Strategist:** tools=`[web_search, read_url, knowledge_search]`, `response_format=ContentPlan`.
- **Writer:** tools=`[web_search, read_url]`, `response_format=DraftContent`. Вхід — `ContentPlan` + (опц.) `previous_draft` + `feedback`.
- **Editor:** tools=`[web_search, read_url]`, `response_format=EditFeedback`.

Промпти → **Langfuse Prompt Management** з label `production` (як у hw-12).

## 9. Langfuse (`config.py`, `main.py`)

1. **Налаштування Cloud** — повторно використати проєкт з hw-12 або новий `course-project`. `.env`:
   ```
   LANGFUSE_PUBLIC_KEY=...
   LANGFUSE_SECRET_KEY=...
   LANGFUSE_BASE_URL=https://us.cloud.langfuse.com
   LANGFUSE_USER_ID=auinua
   ```
2. **Prompt Management** — 4 промпти з label `production`:
   - `strategist_system`, `writer_system`, `editor_system`, `judge_system` (для тестів).
3. **Tracing:**
   - `main.py`: кожен користувацький бриф → `@observe(name="content-pipeline")` + `propagate_attributes(session_id, user_id, tags=["course-project","content-pipeline"])`.
   - `CallbackHandler()` додається до `config["callbacks"]` при виклику графа.
4. **Evaluators (UI):** створимо мінімум 2 (в реальних трейсах):
   - `content_quality` (numeric 0..1) — оцінює фінальний контент.
   - `plan_alignment` (boolean) — чи план відповідає брифу.
   - *(бажано третій — `tone_fidelity` (categorical: strict|loose|off-brand))*

## 10. Тести (`tests/`) — LLM-as-a-Judge

`tests/judge.py`:
```python
class JudgeVerdict(BaseModel):
    score: float                  # 0..1
    reasoning: str
    issues: list[str] = []

def judge(criteria: str, input: str, output: str, threshold: float = 0.7) -> JudgeVerdict:
    # gpt-4o-mini через model_gateway task="judge", temperature=0
    # with_structured_output(JudgeVerdict)
    # system prompt з Langfuse (name="judge_system")
    # @observe(name="llm-judge") → видно в Langfuse окремим трейсом
```

Тести (мінімум 4 сценарії з завдання):

| Файл | Тестує | Сценарій |
|---|---|---|
| `test_strategist.py` | Plan відповідає брифу (audience, tone, channel) | LinkedIn / AI in healthcare / professional → judge перевіряє, що в outline немає casual/memes |
| `test_writer.py` | Draft покриває всі пункти outline + keywords | Фіксований ContentPlan з 5 пунктами → judge перевіряє покриття |
| `test_editor.py` | Feedback виявляє явні проблеми + scores низькі | Свідомо off-topic + wrong tone draft → `verdict == REVISION_NEEDED`, scores < 0.5 |
| `test_e2e.py` | Фінальний контент відповідає брифу (end-to-end run) | Повний граф з auto-approve HITL → judge на financial output |

Pytest assert: `assert verdict.score >= 0.7, verdict.reasoning`. Запуск: `pytest tests/ -v`.

## 11. Бонус: Google Drive MCP

- Додати MCP-сервер Google Drive (офіційний з modelcontextprotocol/servers).
- У `tools.py` додати `save_to_gdrive(filename, content)` як MCP-клієнт виклик.
- Викликається **після** `save_content` (локальне збереження залишається як fallback).
- Робимо в самому кінці, коли основний pipeline працює.

## 12. Покрокова послідовність

1. Scaffolding: `requirements.txt`, `.env.example`, `.gitignore`, `config.py`, `schemas.py`.
2. `model_gateway.py` + перевірка, що `ChatOpenAI.with_fallbacks([...])` працює.
3. `tools.py` (web_search, read_url, save_content) + `retriever.py` (RAG зі stub'ом на порожній index).
4. Промпти — написати чернетки локально, **потім** створити в Langfuse UI і видалити з коду (залишити лише `load_prompt`).
5. `agents/{strategist,writer,editor}.py`.
6. `graph.py`: nodes + edges + HITL + `route_after_editor`.
7. `main.py`: REPL + Langfuse `@observe` + `propagate_attributes` + HITL handler.
8. Прогін 3-5 брифів → перевірка Langfuse UI (traces, session, user).
9. Evaluators в Langfuse UI (2-3 штуки).
10. Тести: `judge.py` + 4 test-файли + `pytest tests/`.
11. README.md (архітектурна діаграма, запуск, приклади).
12. 4 скріншоти в `screenshots/` (trace tree, session, evaluators, prompts).
13. Коли дані для RAG готові → `python ingest.py`, прогнати повний pipeline з `knowledge_search`.
14. Бонус: Google Drive MCP.
15. Демо: інструкція, як записати GIF/відео (ти записуєш — я надам сценарій).

## 13. Критерії готовності (із `project_content.md`)

- [ ] Код у Git-репо
- [ ] Архітектурна діаграма в README
- [ ] Інструкція запуску + приклади
- [ ] Langfuse traces: input/output/latency/tokens/metadata для кожного LLM-виклику
- [ ] ≥ 2 LLM-as-a-Judge evaluators у Langfuse (online)
- [ ] ≥ 4 тестові сценарії (pytest) з LLM-as-a-Judge
- [ ] Скріншоти Langfuse у `screenshots/`
- [ ] Записане демо (відео/GIF)
- [ ] Бонус: Google Drive MCP
