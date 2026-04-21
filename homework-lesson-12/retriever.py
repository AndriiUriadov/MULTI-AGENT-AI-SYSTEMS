"""
Hybrid retrieval module.

Combines semantic search (FAISS) + BM25 (lexical) + cross-encoder reranking.
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


def get_retriever():
    global _retriever
    if _retriever is not None:
        return _retriever

    embeddings = OpenAIEmbeddings(
        model=settings.embedding_model,
        api_key=settings.api_key.get_secret_value(),
    )

    # Semantic retriever from FAISS index
    vectorstore = FAISS.load_local(
        settings.index_dir,
        embeddings,
        allow_dangerous_deserialization=True,
    )
    semantic_retriever = vectorstore.as_retriever(
        search_kwargs={"k": settings.retrieval_top_k}
    )

    # BM25 retriever from saved chunks
    chunks_path = os.path.join(settings.index_dir, "chunks.pkl")
    with open(chunks_path, "rb") as f:
        chunks = pickle.load(f)
    bm25_retriever = BM25Retriever.from_documents(chunks)
    bm25_retriever.k = settings.retrieval_top_k

    # Ensemble: 50% semantic + 50% BM25
    ensemble = EnsembleRetriever(
        retrievers=[semantic_retriever, bm25_retriever],
        weights=[0.5, 0.5],
    )

    # Cross-encoder reranker on top
    cross_encoder = HuggingFaceCrossEncoder(model_name="BAAI/bge-reranker-base")
    reranker = CrossEncoderReranker(model=cross_encoder, top_n=settings.rerank_top_n)

    _retriever = ContextualCompressionRetriever(
        base_compressor=reranker,
        base_retriever=ensemble,
    )
    return _retriever
