"""
Brand knowledge ingestion pipeline.

Loads all .md, .txt, and .pdf files from data/, chunks them, embeds with
OpenAI, and saves FAISS + BM25 corpus into index/.

Usage: python ingest.py
"""

import os
import pickle
import time

from langchain_community.document_loaders import (
    DirectoryLoader,
    PyPDFLoader,
    TextLoader,
)
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from config import Settings

settings = Settings()

# Stay under the text-embedding-3-small 40k TPM limit.
_BATCH_SIZE = 300
_BATCH_PAUSE = 65  # seconds between batches


def _load_documents(data_dir: str):
    """Load .md, .txt, and .pdf files from data_dir into Langchain Documents."""
    docs = []

    text_loader = DirectoryLoader(
        data_dir,
        glob="**/*.md",
        loader_cls=TextLoader,
        loader_kwargs={"encoding": "utf-8"},
        show_progress=False,
    )
    docs.extend(text_loader.load())

    txt_loader = DirectoryLoader(
        data_dir,
        glob="**/*.txt",
        loader_cls=TextLoader,
        loader_kwargs={"encoding": "utf-8"},
        show_progress=False,
    )
    docs.extend(txt_loader.load())

    pdf_loader = DirectoryLoader(
        data_dir,
        glob="**/*.pdf",
        loader_cls=PyPDFLoader,
        show_progress=False,
    )
    docs.extend(pdf_loader.load())

    return docs


def ingest():
    if not os.path.isdir(settings.data_dir):
        print(f"No data directory '{settings.data_dir}/' — skipping ingest.")
        return

    print(f"Loading documents from '{settings.data_dir}/' (.md, .txt, .pdf)…")
    docs = _load_documents(settings.data_dir)
    if not docs:
        print("No documents found. Add brand files to data/ and retry.")
        return
    print(f"Loaded {len(docs)} documents")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
    )
    chunks = splitter.split_documents(docs)
    print(f"Split into {len(chunks)} chunks")

    embeddings = OpenAIEmbeddings(
        model=settings.embedding_model,
        api_key=settings.api_key.get_secret_value(),
    )

    print("Embedding in batches to respect TPM…")
    vectorstore = None
    for i in range(0, len(chunks), _BATCH_SIZE):
        batch = chunks[i : i + _BATCH_SIZE]
        batch_num = i // _BATCH_SIZE + 1
        total_batches = (len(chunks) + _BATCH_SIZE - 1) // _BATCH_SIZE
        print(f"  Batch {batch_num}/{total_batches} ({len(batch)} chunks)…")
        if vectorstore is None:
            vectorstore = FAISS.from_documents(batch, embeddings)
        else:
            vectorstore.add_documents(batch)
        if i + _BATCH_SIZE < len(chunks):
            print(f"  Waiting {_BATCH_PAUSE}s for TPM reset…")
            time.sleep(_BATCH_PAUSE)

    os.makedirs(settings.index_dir, exist_ok=True)
    vectorstore.save_local(settings.index_dir)
    print(f"FAISS index saved to '{settings.index_dir}/'")

    chunks_path = os.path.join(settings.index_dir, "chunks.pkl")
    with open(chunks_path, "wb") as f:
        pickle.dump(chunks, f)
    print(f"Chunks saved to '{chunks_path}'")

    print(f"\nDone! Ingested {len(chunks)} chunks from {len(docs)} documents.")


if __name__ == "__main__":
    ingest()
