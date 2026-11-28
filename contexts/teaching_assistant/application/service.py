import uuid
from collections.abc import Iterator

from contexts.teaching_assistant.domain.chunks import SCORE_THRESHOLD, RetrievedChunk
from contexts.teaching_assistant.domain.ports import (
    ConversationRecordPort,
    RetrievalPort,
)
from shared.infrastructure.llm.port import LLMPort
from shared.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

UNABLE_TO_ANSWER_REPLY = "暂未找到相关课件内容，无法回答，请换个问法或补充更多信息。"
TOP_K = 5
ANSWER_SYSTEM_PROMPT = (
    "你是课程助教。请基于给定的课件分块回答学员问题，讲解知识点并尽量溯源。"
    "若课件分块不足以回答，请如实说明。"
    "回答请用简体中文，分段清晰；可用 **加粗** 强调重点、用 - 列表分点。"
    "不要使用 Markdown 标题（#）、引用（>）或代码块等符号。"
)


class TeachingAssistantService:
    def __init__(
        self,
        llm: LLMPort,
        retrieval: RetrievalPort,
        conversation_record: ConversationRecordPort,
    ):
        self._llm = llm
        self._retrieval = retrieval
        self._conversation_record = conversation_record

    def ask(self, question: str, student_id: str | None, conversation_id: str | None = None) -> dict:
        conversation_id = conversation_id or ("conv_" + uuid.uuid4().hex[:12])

        hits = self._retrieval.search(question, TOP_K)
        selected = [h for h in hits if h.score >= SCORE_THRESHOLD]
        if not selected:
            reply = UNABLE_TO_ANSWER_REPLY
            sources: list[dict] = []
        else:
            reply = self._llm.chat(self._build_messages(question, selected)).content
            sources = self._to_sources(selected)

        self._record(conversation_id, student_id, question, reply, sources)
        return {"reply": reply, "sources": sources, "conversationId": conversation_id}

    def ask_stream(
        self,
        question: str,
        student_id: str | None,
        conversation_id: str | None = None,
    ) -> Iterator[dict]:
        """以 SSE 事件流（meta / delta / done / error）返回答疑；完成后落库。"""
        conversation_id = conversation_id or ("conv_" + uuid.uuid4().hex[:12])

        hits = self._retrieval.search(question, TOP_K)
        selected = [h for h in hits if h.score >= SCORE_THRESHOLD]

        if not selected:
            reply = UNABLE_TO_ANSWER_REPLY
            sources: list[dict] = []
            yield {"type": "meta", "conversationId": conversation_id, "sources": sources}
            yield {"type": "delta", "content": reply}
        else:
            sources = self._to_sources(selected)
            yield {"type": "meta", "conversationId": conversation_id, "sources": sources}
            parts: list[str] = []
            try:
                for chunk in self._llm.stream(self._build_messages(question, selected)):
                    parts.append(chunk)
                    yield {"type": "delta", "content": chunk}
            except Exception:
                yield {"type": "error", "message": "回复生成失败，请稍后重试"}
                return
            reply = "".join(parts)

        self._record(conversation_id, student_id, question, reply, sources)
        yield {"type": "done"}

    def list_conversations(self, user_id: str | None) -> list[dict]:
        return self._conversation_record.list_conversations(user_id)

    def list_messages(self, conversation_id: str) -> list[dict]:
        return self._conversation_record.list_messages(conversation_id)

    def _record(
        self,
        conversation_id: str,
        user_id: str | None,
        question: str,
        reply: str,
        sources: list[dict],
    ) -> None:
        try:
            self._conversation_record.record_exchange(
                conversation_id=conversation_id,
                user_id=user_id,
                question=question,
                reply=reply,
                sources=sources,
            )
        except Exception:
            logger.warning("conversation_record_failed", conversation_id=conversation_id)

    @staticmethod
    def _to_source(hit: RetrievedChunk) -> dict:
        heading_path = hit.heading_path
        if hit.document_name and hit.document_name not in heading_path:
            heading_path = f"{hit.document_name} > {heading_path}"
        return {
            "chapterId": hit.chapter,
            "headingPath": heading_path,
            "sourceRef": hit.heading_path.rsplit(" > ", 1)[-1],
        }

    @staticmethod
    def _to_sources(hits: list[RetrievedChunk]) -> list[dict]:
        """将命中分块转为去重后的溯源来源（同一小节多个分块只保留一条）。"""
        seen: set[str] = set()
        sources: list[dict] = []
        for hit in hits:
            source = TeachingAssistantService._to_source(hit)
            key = source["headingPath"]
            if key in seen:
                continue
            seen.add(key)
            sources.append(source)
        return sources

    @staticmethod
    def _build_messages(question: str, hits: list[RetrievedChunk]) -> list[dict[str, str]]:
        context = "\n\n".join(f"[{h.heading_path}]\n{h.text}" for h in hits)
        return [
            {"role": "system", "content": ANSWER_SYSTEM_PROMPT},
            {"role": "user", "content": f"课件分块：\n{context}\n\n学员问题：{question}"},
        ]
