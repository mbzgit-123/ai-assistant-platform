from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from shared.infrastructure.db.base import Base
import shared.infrastructure.db.models  # noqa: F401
from shared.infrastructure.db.models.business import ConversationMessage
from contexts.teaching_assistant.infrastructure.conversation_repository import ConversationRepository


def _repo():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    s = Session(engine)
    return ConversationRepository(s), s


def test_record_exchange_writes_two_rows():
    repo, s = _repo()
    repo.record_exchange(
        conversation_id="conv_1",
        user_id="s_1",
        question="什么是循环结构",
        reply="循环结构用于重复执行代码。",
        sources=[{"chapterId": "c1", "headingPath": "第2章 > 2.1", "sourceRef": "2.1"}],
    )
    rows = list(s.execute(select(ConversationMessage)).scalars().all())
    assert len(rows) == 2
    assert {r.role for r in rows} == {"user", "assistant"}
    assert {r.conversation_id for r in rows} == {"conv_1"}


def test_record_exchange_role_specific_fields():
    repo, s = _repo()
    repo.record_exchange("conv_1", "s_1", "q", "a", [{"chapterId": "c1"}])
    rows = list(s.execute(select(ConversationMessage)).scalars().all())
    user = next(r for r in rows if r.role == "user")
    assistant = next(r for r in rows if r.role == "assistant")
    assert user.message == "q"
    assert user.sources is None
    assert assistant.message == "a"
    assert assistant.sources == [{"chapterId": "c1"}]
    assert all(r.source == "teaching" for r in rows)
    assert all(r.user_id == "s_1" for r in rows)


def test_record_exchange_user_id_nullable():
    repo, s = _repo()
    repo.record_exchange("conv_1", None, "q", "a", [])
    rows = list(s.execute(select(ConversationMessage)).scalars().all())
    assert all(r.user_id is None for r in rows)


def test_list_conversations_groups_by_conversation():
    repo, s = _repo()
    repo.record_exchange("conv_1", "s_1", "什么是循环", "循环讲解", [{"chapterId": "c1"}])
    repo.record_exchange("conv_1", "s_1", "什么是递归", "递归讲解", [{"chapterId": "c2"}])
    repo.record_exchange("conv_2", "s_1", "什么是数组", "数组讲解", [{"chapterId": "c3"}])
    convs = repo.list_conversations("s_1")
    assert len(convs) == 2
    by_id = {c["conversationId"]: c for c in convs}
    assert by_id["conv_1"]["messageCount"] == 4
    assert by_id["conv_1"]["title"] == "什么是循环"
    assert by_id["conv_1"]["lastMessage"] == "递归讲解"
    assert by_id["conv_2"]["messageCount"] == 2
    assert by_id["conv_2"]["title"] == "什么是数组"


def test_list_conversations_filters_by_user():
    repo, s = _repo()
    repo.record_exchange("conv_1", "s_1", "q", "a", [])
    repo.record_exchange("conv_2", "s_2", "q", "a", [])
    assert [c["conversationId"] for c in repo.list_conversations("s_1")] == ["conv_1"]
    assert [c["conversationId"] for c in repo.list_conversations("s_2")] == ["conv_2"]


def test_list_messages_returns_ordered():
    repo, s = _repo()
    repo.record_exchange("conv_1", "s_1", "q1", "a1", [{"chapterId": "c1"}])
    repo.record_exchange("conv_1", "s_1", "q2", "a2", [{"chapterId": "c2"}])
    msgs = repo.list_messages("conv_1")
    assert len(msgs) == 4
    assert [m["role"] for m in msgs] == ["user", "assistant", "user", "assistant"]
    assert [m["content"] for m in msgs] == ["q1", "a1", "q2", "a2"]
    assert msgs[0]["sources"] is None
    assert msgs[1]["sources"] == [{"chapterId": "c1"}]
