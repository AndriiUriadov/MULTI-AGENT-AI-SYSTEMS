# Brand Knowledge Base

RAG corpus for the Content Strategist. Drop files here, then run `python ingest.py`
from the project root to (re)build the FAISS + BM25 index in `../index/`.

Supported formats: `.md`, `.txt`, `.pdf` (any subfolder depth — DirectoryLoader
globs recursively).

## Expected subfolders

| Folder | What goes here | Status |
|---|---|---|
| `style/` | Tone of voice, audience, dos & don'ts (1–2 pages) | ✅ KPI style guide added |
| `examples/` | 5–10 "good" posts/articles that represent the brand voice | ⏳ pending |
| `brand/` | Mission, product, competitive positioning (1 page) | ⏳ pending |

After the other agent adds the missing corpora, re-run `python ingest.py` —
the index is rebuilt from scratch every time.
