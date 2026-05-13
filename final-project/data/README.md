# Brand Knowledge Base — КПІ ім. Ігоря Сікорського

RAG-корпус, з якого Content Strategist підтягує бренд-контекст (style guide,
опис бренду, приклади контенту) на етапі планування. Запускай
`python ingest.py` з кореня проєкту, щоб (пере)зібрати FAISS + BM25 індекс
у `../index/`.

Підтримувані формати: `.md`, `.txt`, `.pdf` (recursive — `DirectoryLoader`
з `glob="**/*.md"` та аналогами).

## Структура

| Папка | Що лежить | Джерело |
|---|---|---|
| `style/` | KPI Social Media Style Guide (тон, аудиторії, заборони, платформи) | `kpi-social-media-style-guide.pdf` |
| `examples/` | Референсні приклади дописів за платформами (FB, Instagram, YouTube, Telegram, LinkedIn, TikTok, Facebook Physics) | `examples.pdf` |
| `brand/` | Опис бренду КПІ: місія, продукт, аудиторії, конкурентні переваги, заборонені теми, ключові слова позиціонування | `brand.md` |

Після будь-якої зміни вмісту — `python ingest.py` з кореня `course-project/`.
Індекс пересобирається з нуля щоразу.
