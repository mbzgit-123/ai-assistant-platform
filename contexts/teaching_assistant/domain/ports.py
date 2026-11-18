from typing import Protocol

from contexts.teaching_assistant.domain.chunks import Chunk, ScoredChunk


class EmbeddingPort(Protocol):
    def embed(self, text: str) -> list[float]: ...


class VectorStorePort(Protocol):
    def upsert(self, chunks: list[Chunk]) -> None: ...

    def search(self, embedding: list[float], top_k: int) -> list[ScoredChunk]: ...


class HandoffPort(Protocol):
    def create_handoff(self, question: str, student_id: str | None) -> str: ...
