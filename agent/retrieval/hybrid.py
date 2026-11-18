"""Hybrid search combining ChromaDB dense vectors and BM25 lexical retrieval."""

import re
from typing import Any

import chromadb
from chromadb.api import ClientAPI
from rank_bm25 import BM25Okapi


def tokenize(text: str) -> list[str]:
    """Tokenizes text into normalized words, splitting identifiers and underscores."""
    cleaned = re.sub(r"[^\w\s]", " ", text.lower())
    tokens = [t for t in re.split(r"[\s_]+", cleaned) if len(t) > 1]
    return tokens


class BM25Index:
    """In-memory BM25 index over documents."""

    def __init__(self):
        self.doc_ids: list[str] = []
        self.documents: list[str] = []
        self.metadatas: list[dict[str, Any]] = []
        self.bm25: BM25Okapi | None = None

    def index(self, doc_ids: list[str], documents: list[str], metadatas: list[dict[str, Any]]):
        self.doc_ids = list(doc_ids)
        self.documents = list(documents)
        self.metadatas = list(metadatas)

        tokenized_corpus = [tokenize(doc) for doc in documents]
        # Avoid empty token corpus
        for i, tok in enumerate(tokenized_corpus):
            if not tok:
                tokenized_corpus[i] = ["empty"]

        self.bm25 = BM25Okapi(tokenized_corpus)

    def search(self, query: str, top_k: int = 5) -> list[tuple[str, float, dict[str, Any]]]:
        if not self.bm25 or not self.doc_ids:
            return []

        tokens = tokenize(query)
        if not tokens:
            tokens = ["query"]

        scores = self.bm25.get_scores(tokens)
        scored_pairs = []
        for i, score in enumerate(scores):
            if score > 0:
                scored_pairs.append((self.doc_ids[i], float(score), self.metadatas[i]))

        scored_pairs.sort(key=lambda x: x[1], reverse=True)
        return scored_pairs[:top_k]


class HybridSearcher:
    """Performs Reciprocal Rank Fusion (RRF) between Dense (Chroma) and Sparse (BM25)."""

    def __init__(
        self,
        collection_name: str,
        chroma_client: ClientAPI | None = None,
        dense_weight: float = 0.5,
        sparse_weight: float = 0.5,
        rrf_k: int = 60,
    ):
        self.collection_name = collection_name
        self.chroma_client = chroma_client or chromadb.EphemeralClient()
        self.collection = self.chroma_client.get_or_create_collection(name=collection_name)
        self.bm25_index = BM25Index()
        self.dense_weight = dense_weight
        self.sparse_weight = sparse_weight
        self.rrf_k = rrf_k

    def index(self, doc_ids: list[str], documents: list[str], metadatas: list[dict[str, Any]]):
        """Indexes documents in both Chroma (dense) and BM25 (sparse)."""
        # Index in BM25
        self.bm25_index.index(doc_ids, documents, metadatas)

        # Index in Chroma
        # Clear existing entries in collection first if any
        try:
            existing = self.collection.get()
            if existing and existing.get("ids"):
                self.collection.delete(ids=existing["ids"])
        except Exception:
            pass

        self.collection.add(
            ids=doc_ids,
            documents=documents,
            metadatas=metadatas,
        )

    def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Searches using both dense and sparse retrieval, then merges via RRF."""
        # 1. Sparse BM25 Search
        sparse_results = self.bm25_index.search(query, top_k=top_k * 2)
        sparse_ranks = {doc_id: rank for rank, (doc_id, _, _) in enumerate(sparse_results, start=1)}
        metadata_map = {doc_id: meta for doc_id, _, meta in sparse_results}

        # 2. Dense Chroma Search
        dense_ranks: dict[str, int] = {}
        try:
            dense_response = self.collection.query(
                query_texts=[query], n_results=min(top_k * 2, len(self.bm25_index.doc_ids))
            )
            if dense_response and dense_response.get("ids") and dense_response["ids"][0]:
                for rank, doc_id in enumerate(dense_response["ids"][0], start=1):
                    dense_ranks[doc_id] = rank
                    if doc_id not in metadata_map:
                        idx = dense_response["ids"][0].index(doc_id)
                        meta = (
                            dense_response["metadatas"][0][idx]
                            if dense_response.get("metadatas")
                            else {}
                        )
                        metadata_map[doc_id] = meta
        except Exception:
            pass

        # 3. Reciprocal Rank Fusion (RRF)
        all_doc_ids = set(sparse_ranks.keys()).union(set(dense_ranks.keys()))
        if not all_doc_ids:
            # Fallback if query produced no score matches: return top elements from index
            return [
                {"id": doc_id, "score": 0.0, "metadata": meta}
                for doc_id, meta in zip(
                    self.bm25_index.doc_ids[:top_k], self.bm25_index.metadatas[:top_k], strict=False
                )
            ]

        fused_scores: list[tuple[str, float]] = []
        for doc_id in all_doc_ids:
            score = 0.0
            if doc_id in dense_ranks:
                score += self.dense_weight / (self.rrf_k + dense_ranks[doc_id])
            if doc_id in sparse_ranks:
                score += self.sparse_weight / (self.rrf_k + sparse_ranks[doc_id])
            fused_scores.append((doc_id, score))

        fused_scores.sort(key=lambda x: x[1], reverse=True)

        return [
            {
                "id": doc_id,
                "score": round(score, 6),
                "metadata": metadata_map.get(doc_id, {}),
            }
            for doc_id, score in fused_scores[:top_k]
        ]
