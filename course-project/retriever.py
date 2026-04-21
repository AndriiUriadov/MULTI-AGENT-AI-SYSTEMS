"""
Hybrid retrieval for the brand knowledge base (style guide, brand desc, examples).

Combines semantic search (FAISS) + BM25 (lexical) + cross-encoder reranking.
If the index directory is missing or empty, get_retriever() returns None so
callers can degrade gracefully (useful before the brand corpus is ingested).
"""

import os
import pickle

from langchain_classic.retrievers.contextual_compression import ContextualCompressionRetriever
from langchain_classic.retrievers.ensemble import EnsembleRetriever
from langchain_classic.retrievers.document_compressors.cross_encoder_rerank import CrossEncoderReranker
from langchain_community.cross_encoders import HuggingFaceCrossEncoder
from langchain_community.retrievers import BM25Retriever
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings

from config import Settings

settings = Settings()

_retriever = None


def _index_exists() -> bool:
    faiss_file = os.path.join(settings.index_dir, "index.faiss")
    chunks_file = os.path.join(settings.index_dir, "chunks.pkl")
    return os.path.isfile(faiss_file) and os.path.isfile(chunks_file)


def get_retriever():
    """Return the retriever, or None if the brand index hasn't been built yet."""
    global _retriever
    if _retriever is not None:
        return _retriever

    if not _index_exists():
        return None

    embeddings = OpenAIEmbeddings(
        model=settings.embedding_model,
        api_key=settings.api_key.get_secret_value(),
    )

    vectorstore = FAISS.load_local(
        settings.index_dir,
        embeddings,
        allow_dangerous_deserialization=True,
    )
    semantic_retriever = vectorstore.as_retriever(
        search_kwargs={"k": settings.retrieval_top_k}
    )

    chunks_path = os.path.join(settings.index_dir, "chunks.pkl")
    with open(chunks_path, "rb") as f:
        chunks = pickle.load(f)
    bm25_retriever = BM25Retriever.from_documents(chunks)
    bm25_retriever.k = settings.retrieval_top_k

    ensemble = EnsembleRetriever(
        retrievers=[semantic_retriever, bm25_retriever],
        weights=[0.5, 0.5],
    )

    # v2-m3 is multilingual; the brand corpus may be in any language (Ukrainian
    # for the KPI style guide, English for Mailchimp-like guides, etc.).
    cross_encoder = HuggingFaceCrossEncoder(model_name="BAAI/bge-reranker-v2-m3")
    reranker = CrossEncoderReranker(model=cross_encoder, top_n=settings.rerank_top_n)

    _retriever = ContextualCompressionRetriever(
        base_compressor=reranker,
        base_retriever=ensemble,
    )
    return _retriever
