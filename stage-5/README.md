# Homework Lesson 5 - Research Agent з RAG-системою

Розширення Research Agent з `homework-lesson-3`: додано RAG-інструмент з гібридним пошуком та reranking. Агент тепер шукає не лише в інтернеті, а й у локальній базі знань з PDF-документів.

## Що реалізовано

### Knowledge Ingestion Pipeline (`ingest.py`)
- Завантаження PDF-файлів з `data/` через `PyPDFDirectoryLoader`
- Розбиття на чанки: `RecursiveCharacterTextSplitter` (chunk_size=500, overlap=100)
- Генерація embeddings: OpenAI `text-embedding-3-small`
- Збереження FAISS індексу на диск (`index/`)
- Збереження чанків у `index/chunks.pkl` для BM25

**Результат запуску:** 52 сторінки -> 462 чанки -> FAISS індекс

### Hybrid Retrieval + Reranking (`retriever.py`)
- **Semantic search**: FAISS + OpenAI embeddings (cosine similarity)
- **BM25 search**: лексичний пошук за ключовими словами (`rank_bm25`)
- **Ensemble**: об'єднання 50/50 через `EnsembleRetriever`
- **Reranking**: cross-encoder `BAAI/bge-reranker-base` через `CrossEncoderReranker`
- Singleton-ініціалізація: retriever завантажується один раз при першому виклику

### RAG Tool (`tools.py`)
Новий інструмент `knowledge_search` поряд з `web_search`, `read_url`, `write_report`:
```python
@tool
def knowledge_search(query: str) -> str:
    """Search the local knowledge base using hybrid retrieval and reranking."""
```
Повертає топ-N відповідних уривків з назвою документа і номером сторінки.

### Agent (`agent.py`)
- LangChain `ChatOpenAI` (gpt-4o-mini) + LangGraph `create_react_agent`
- 4 інструменти: `knowledge_search`, `web_search`, `read_url`, `write_report`
- `MemorySaver` для збереження контексту розмови

## Запуск

```bash
pip install -r requirements.txt

# Побудувати індекс (один раз)
python ingest.py

# Запустити агента
python main.py
```

`.env`:
```
API_KEY=<openai-api-key>
MODEL_NAME=gpt-4o-mini
```

> **Примітка:** `ingest.py` виконує embedding батчами (по 300 чанків) з паузою 65 секунд між батчами, щоб не перевищити ліміт OpenAI 40k TPM. Бо падало.

## Тестові дані

У `data/` знаходяться три PDF-документи:
- `langchain.pdf`
- `large-language-model.pdf`
- `retrieval-augmented-generation.pdf`

## Результат роботи

Запит: *"Що таке RAG і які є підходи до retrieval?"*

Вивід термінала записано в файл: [`terminal.out`](terminal.out)

Агент:
1. Викликав `knowledge_search` -> завантажив `BAAI/bge-reranker-base` (1.1 GB) і отримав релевантні чанки з локальної бази
2. Доповнив результат через `web_search` -> знайшов arxiv-статтю
3. Викликав `write_report` -> зберіг звіт `output/rag_and_retrieval_approaches.md`

Фрагмент відповіді агента з `terminal.out`:
```
Agent: # Retrieval-Augmented Generation (RAG) and Retrieval Approaches

## What is RAG?
Retrieval-Augmented Generation (RAG) is a technique that enhances large language
models (LLMs) by incorporating external data retrieval systems...

## Sources
- Local Knowledge Base: Various documents on RAG techniques and retrieval approaches.
- Web Sources: Retrieval-Augmented Generation for Large Language Models: A Survey
  https://arxiv.org/abs/2312.10997
```

Повний вивід термінала: [`terminal.out`](terminal.out)

## Особливості, з якими стикнувся

1. **HF_TOKEN warning** - не помилка, просто рекомендація від HuggingFace Hub. Модель `BAAI/bge-reranker-base` завантажилась без токена, наступні запити вже будуть з локального кешу.

2. **Sources section у звіті вказує "Various documents"** замість конкретних файлів - це поведінка LLM при синтезі відповіді. Код повертає назву файлу і номер сторінки, але GPT-4o-mini узагальнив їх у підсумку. Не баг.

3. Наступний запуск був вже без **warning** та документи були вказані правильно - конкретні файли.

