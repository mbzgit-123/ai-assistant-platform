import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from shared.infrastructure.db.models.business import ConversationMessage


class ConversationRepository:
    def __init__(self, session: Session):
        self._session = session

    def record_exchange(
        self,
        conversation_id: str,
        user_id: str | None,
        question: str,
        reply: str,
        sources: list[dict],
    ) -> None:
        self._session.add(
            ConversationMessage(
                message_id="msg_" + uuid.uuid4().hex[:12],
                conversation_id=conversation_id,
                user_id=user_id,
                role="user",
                message=question,
                sources=None,
                source="teaching",
            )
        )
        self._session.add(
            ConversationMessage(
                message_id="msg_" + uuid.uuid4().hex[:12],
                conversation_id=conversation_id,
                user_id=user_id,
                role="assistant",
                message=reply,
                sources=sources,
                source="teaching",
            )
        )
        self._session.commit()

    def list_conversations(self, user_id: str | None) -> list[dict]:
        stmt = (
            select(ConversationMessage)
            .where(
                ConversationMessage.source == "teaching",
                ConversationMessage.user_id == user_id,
            )
            .order_by(ConversationMessage.id.asc())
        )
        rows = list(self._session.execute(stmt).scalars().all())

        by_conv: dict[str, list[ConversationMessage]] = {}
        for r in rows:
            by_conv.setdefault(r.conversation_id, []).append(r)

        conversations: list[tuple[int, dict]] = []
        for conv_id, msgs in by_conv.items():
            first_user = next((m for m in msgs if m.role == "user"), msgs[0])
            last = msgs[-1]
            conversations.append(
                (
                    last.id,
                    {
                        "conversationId": conv_id,
                        "title": (first_user.message or "")[:50],
                        "lastMessage": (last.message or "")[:50],
                        "messageCount": len(msgs),
                        "updatedAt": last.created_at.isoformat() if last.created_at else None,
                    },
                )
            )
        conversations.sort(key=lambda t: t[0], reverse=True)
        return [c for _, c in conversations]

    def list_messages(self, conversation_id: str) -> list[dict]:
        stmt = (
            select(ConversationMessage)
            .where(ConversationMessage.conversation_id == conversation_id)
            .order_by(ConversationMessage.id.asc())
        )
        rows = list(self._session.execute(stmt).scalars().all())
        return [
            {
                "role": r.role,
                "content": r.message,
                "sources": r.sources,
                "createdAt": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
