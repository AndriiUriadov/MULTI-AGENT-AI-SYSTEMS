# Homework Lesson 3 - Research Agent

LangChain ReAct агент, який отримує питання від користувача, самостійно шукає інформацію через набір інструментів і генерує структурований Markdown-звіт.

## Що реалізовано

### Інструменти агента (`tools.py`)

**`web_search(query)`** — пошук через DuckDuckGo (`ddgs`):
- Повертає список результатів з `title`, `url`, `snippet`
- Сніпети обрізаються до `max_snippet_length` (300 символів) — context engineering
- Обробка помилок: мережеві збої повертають `[{"error": "..."}]` замість краша

**`read_url(url)`** — витягує повний текст сторінки через `trafilatura`:
- Обрізає до `max_url_content_length` (5000 символів)
- Обробка помилок: недоступна сторінка або помилка парсингу повертає рядок з описом помилки

**`write_report(filename, content)`** — зберігає Markdown-звіт у `output/`:
- Автоматично додає `.md` до імені файлу
- Повертає повний шлях до збереженого файлу

### Agent Loop (`agent.py`)

- `ChatGoogleGenerativeAI` (Gemini) як LLM
- `create_react_agent` з LangGraph — ReAct цикл без ручної реалізації
- `MemorySaver` (checkpointer) — збереження контексту між повідомленнями в межах сесії
- `_AgentWrapper` — обгортка для автоматичного підставляння `thread_id` та `recursion_limit`
- Нормалізація Gemini-контенту: Gemini повертає `list[dict]`, обгортка конвертує в рядок

### Конфігурація (`config.py`)

- `Settings` (Pydantic) читає `.env`: `API_KEY`, `MODEL_NAME`
- Константи: `max_search_results=5`, `max_snippet_length=300`, `max_url_content_length=5000`, `max_iterations=10`
- `SYSTEM_PROMPT` — роль агента, опис інструментів, стратегія дослідження

## Запуск

```bash
pip install -r requirements.txt
python main.py
```

`.env`:
```
API_KEY=<google-gemini-api-key>
MODEL_NAME=gemini-2.0-flash
```

## Приклад роботи

Запит: *"Що таке RAG (Retrieval-Augmented Generation)?"*

Агент виконав кілька `web_search` та `read_url` викликів, зібрав інформацію з Wikipedia, IBM та AWS, після чого викликав `write_report` і зберіг структурований звіт.

Збережений звіт: [`example_output/report.md`](example_output/report.md)

## Зауваження від куратора та виправлення

Після здачі роботи отримав два зауваження, які були виправлені:

1. **Відсутнє обрізання у `web_search`** — додано `snippet[:max_snippet_length]` (300 символів на результат), щоб уникнути переповнення контексту при 5 результатах пошуку
2. **Відсутня обробка помилок у `web_search`** — загорнуто у `try/except`, помилки повертаються як `[{"error": "..."}]` аналогічно до `read_url`
