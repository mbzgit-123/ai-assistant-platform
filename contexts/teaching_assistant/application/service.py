from contexts.teaching_assistant.domain.chunks import (
    HANDOFF_KEYWORDS,
    SCORE_THRESHOLD,
    Chunk,
)
from contexts.teaching_assistant.domain.ports import (
    EmbeddingPort,
    HandoffPort,
    VectorStorePort,
)
from shared.infrastructure.llm.port import LLMPort

HANDOFF_REPLY = "已为你转接授课老师，请稍候。"
TOP_K = 5
ANSWER_SYSTEM_PROMPT = (
    "你是课程助教。请基于给定的课件分块回答学员问题，讲解知识点并尽量溯源。"
    "若课件分块不足以回答，请如实说明。"
)


class TeachingAssistantService:
    def __init__(
        self,
        llm: LLMPort,
        embedding: EmbeddingPort,
        vector_store: VectorStorePort,
        handoff: HandoffPort,
    ):
        self._llm = llm
        self._embedding = embedding
        self._vector_store = vector_store
        self._handoff = handoff

    def ask(self, question: str, student_id: str | None) -> dict:
        if not question or not question.strip():
            return self._handoff_reply(question, student_id)
        if any(kw in question for kw in HANDOFF_KEYWORDS):
            return self._handoff_reply(question, student_id)

        emb = self._embedding.embed(question)
        scored = self._vector_store.search(emb, TOP_K)
        max_score = max((s.score for s in scored), default=-1.0)
        if max_score < SCORE_THRESHOLD:
            return self._handoff_reply(question, student_id)

        hits = [s.chunk for s in scored if s.score >= SCORE_THRESHOLD]
        reply = self._llm.chat(self._build_messages(question, hits)).content
        sources = [
            {
                "chapterId": c.chapter_id,
                "headingPath": c.heading_path,
                "sourceRef": c.source_ref,
            }
            for c in hits
        ]
        return {"reply": reply, "sources": sources, "handoff": False}

    def _handoff_reply(self, question: str, student_id: str | None) -> dict:
        self._handoff.create_handoff(question, student_id)
        return {"reply": HANDOFF_REPLY, "sources": [], "handoff": True}

    @staticmethod
    def _build_messages(question: str, hits: list[Chunk]) -> list[dict[str, str]]:
        context = "\n\n".join(
            f"[{c.heading_path} / {c.source_ref}]\n{c.text}" for c in hits
        )
        return [
            {"role": "system", "content": ANSWER_SYSTEM_PROMPT},
            {"role": "user", "content": f"课件分块：\n{context}\n\n学员问题：{question}"},
        ]
