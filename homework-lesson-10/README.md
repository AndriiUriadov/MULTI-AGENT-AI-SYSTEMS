# homework-lesson-10 — DeepEval tests for the multi-agent system

Тестове покриття системи з `homework-lesson-8` (Supervisor → Planner →
Researcher → Critic) за допомогою DeepEval: golden dataset,
component-level метрики (GEval), ToolCorrectnessMetric і e2e з кастомною
метрикою `CitationPresence`.

## Передумови

1. Створити `.env` у корені теки:
   ```
   API_KEY=<OpenAI key>
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

## Запуск тестів

```bash
deepeval test run tests/                 # усі тести
deepeval test run tests/test_planner.py  # один файл
pytest tests/                            # лише детерміністичні перевірки
```

## Посилання

- Постановка: [plan10.md](plan10.md)
- Детальний план виконання: [plan-detailed-10.md](plan-detailed-10.md)
