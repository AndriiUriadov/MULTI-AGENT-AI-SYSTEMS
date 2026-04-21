"""
Knowledge ingestion pipeline.

Loads documents from data/ directory, splits into chunks,
generates embeddings, and saves the index to disk.

Usage: python ingest.py
"""

import os
import pickle
import time

from langchain_community.document_loaders import PyPDFDirectoryLoader
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from config import Settings

settings = Settings()

# Max tokens per batch to stay under 40k TPM rate limit.
# text-embedding-3-small: ~300 chunks of 500 chars ≈ 37k tokens — safe margin.
_BATCH_SIZE = 300
_BATCH_PAUSE = 65  # seconds to wait between batches


def ingest():
    print(f"Loading documents from '{settings.data_dir}'...")
    loader = PyPDFDirectoryLoader(settings.data_dir)
    docs = loader.load()
    print(f"Loaded {len(docs)} pages")

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

    print("Building FAISS index in batches to respect rate limits...")
    vectorstore = None
    for i in range(0, len(chunks), _BATCH_SIZE):
        batch = chunks[i : i + _BATCH_SIZE]
        batch_num = i // _BATCH_SIZE + 1
        total_batches = (len(chunks) + _BATCH_SIZE - 1) // _BATCH_SIZE
        print(f"  Embedding batch {batch_num}/{total_batches} ({len(batch)} chunks)...")
        if vectorstore is None:
            vectorstore = FAISS.from_documents(batch, embeddings)
        else:
            vectorstore.add_documents(batch)
        if i + _BATCH_SIZE < len(chunks):
            print(f"  Waiting {_BATCH_PAUSE}s for TPM rate limit to reset...")
            time.sleep(_BATCH_PAUSE)

    os.makedirs(settings.index_dir, exist_ok=True)
    vectorstore.save_local(settings.index_dir)
    print(f"FAISS index saved to '{settings.index_dir}/'")

    chunks_path = os.path.join(settings.index_dir, "chunks.pkl")
    with open(chunks_path, "wb") as f:
        pickle.dump(chunks, f)
    print(f"Chunks saved to '{chunks_path}'")

    print(f"\nDone! Ingested {len(chunks)} chunks from {len(docs)} pages.")


if __name__ == "__main__":
    ingest()
