import math

from contexts.teaching_assistant.domain.chunks import Chunk, ScoredChunk
from contexts.teaching_assistant.domain.ports import EmbeddingPort


class InMemoryVectorStore:
    """内存向量库：按 chunk_id 去重，余弦相似度 Top-K 检索。"""

    def __init__(self, embedding: EmbeddingPort):
        self._embedding = embedding
        self._vectors: dict[str, tuple[Chunk, list[float]]] = {}

    def upsert(self, chunks: list[Chunk]) -> None:
        for chunk in chunks:
            self._vectors[chunk.chunk_id] = (chunk, self._embedding.embed(chunk.text))

    def search(self, embedding: list[float], top_k: int) -> list[ScoredChunk]:
        results: list[ScoredChunk] = []
        for chunk, vec in self._vectors.values():
            results.append(ScoredChunk(chunk=chunk, score=self._cosine(embedding, vec)))
        results.sort(key=lambda s: s.score, reverse=True)
        return results[:top_k]

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(x * x for x in b))
        if na == 0.0 or nb == 0.0:
            return 0.0
        return dot / (na * nb)
