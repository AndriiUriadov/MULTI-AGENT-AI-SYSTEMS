# Homework Lesson 4 - Research Agent з власним ReAct Loop

Розширення Research Agent з homework-lesson-3: заміна `create_react_agent` на власну реалізацію ReAct-циклу та покращення system prompt.

## Що зроблено

### 1. Власний ReAct Loop
Прибрано залежності від LangGraph і LangChain. Клас `ResearchAgent` в `agent.py` самостійно керує циклом:
- відправляє повідомлення в Gemini API з визначеннями інструментів
- отримує відповідь і перевіряє наявність `function_call`
- виконує інструмент, додає результат до історії
- повторює до отримання фінальної текстової відповіді або досягнення ліміту ітерацій

### 2. Tools як JSON Schema
Інструменти (`web_search`, `read_url`, `write_report`) описані як JSON Schema у форматі Gemini tool calling API замість `@tool` декоратора LangChain. Додано диспетчер `execute_tool(name, args)`.

### 3. Ручне управління пам'яттю
`self.history` — список `Content` об'єктів, що зберігає весь діалог між запитами в межах сесії. Без `MemorySaver`.

### 4. Покращений System Prompt
Переписано з застосуванням технік промпт-інжинірингу: чітка роль агента, структурований workflow з кроками, явні обмеження поведінки, приклад reasoning trace.

### 5. Логування кроків
Кожен виклик інструменту виводиться в консоль:
```
🔧 Tool call: web_search(query="naive RAG explained")
📎 Result: [{'title': '...', ...}]
```

### 6. Обробка помилок
- Помилки окремих tool calls перехоплюються і передаються моделі як повідомлення про помилку — агент продовжує роботу
- Ліміт ітерацій (`max_iterations`) захищає від нескінченного циклу
- Обробка `MALFORMED_FUNCTION_CALL`: модель отримує запит повторити виклик з коротшим контентом

## Запуск

```bash
pip install -r requirements.txt
python main.py
```

Потрібен файл `.env`:
```
API_KEY=my-google-api-key
MODEL_NAME=gemini-2.0-flash
```



## Вивід

Результати роботи `main.py` в терміналі записано в `terminal.out` 
