from typing import Protocol

from contexts.teaching_assistant.domain.chunks import RetrievedChunk


class RetrievalPort(Protocol):
    def search(self, question: str, top_k: int) -> list[RetrievedChunk]: ...


class ConversationRecordPort(Protocol):
    def record_exchange(
        self,
        conversation_id: str,
        user_id: str | None,
        question: str,
        reply: str,
        sources: list[dict],
    ) -> None: ...

    def list_conversations(self, user_id: str | None) -> list[dict]: ...

    def list_messages(self, conversation_id: str) -> list[dict]: ...
