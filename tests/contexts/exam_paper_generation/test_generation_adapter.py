from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from shared.infrastructure.db.base import Base
import shared.infrastructure.db.models  # noqa: F401
from shared.infrastructure.db.models.sync_cache import Video, VideoAnnotation, Chapter
from shared.infrastructure.llm.fake import FakeLLMAdapter
from shared.infrastructure.llm.port import LLMResult
from contexts.exam_paper_generation.infrastructure.adapter import QuestionGenerationAdapter


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


class _SpyLLM:
    def __init__(self, response: str):
        self._response = response
        self.messages: list[list[dict[str, str]]] = []

    def chat(self, messages: list[dict[str, str]]) -> LLMResult:
        self.messages.append(messages)
        return LLMResult(content=self._response)


def test_plan_counts_reads_durations():
    s = _session()
    s.add_all([
        Video(video_id="v1", chapter_id="c1", title="t", duration_seconds=600),
        Video(video_id="v2", chapter_id="c1", title="t", duration_seconds=1800),
    ])
    s.commit()
    a = QuestionGenerationAdapter(s, FakeLLMAdapter())
    assert a.plan_counts(["v1", "v2"]) == {"v1": 5, "v2": 10}


def test_generate_by_video_parses_llm_json():
    s = _session()
    s.add_all([
        Video(video_id="v1", chapter_id="c1", title="t", duration_seconds=600),
        VideoAnnotation(video_id="v1", chapter_id="c1", start_sentence="S", end_sentence="E"),
        Chapter(chapter_id="c1", title="ch", content_md="S 内容 E"),
    ])
    s.commit()
    # allocate_types(3, False) = {multi_choice:1, short_answer:1, scenario:1, code_fill:0}
    llm = FakeLLMAdapter(responses=[
        '[{"content": {"stem": "q", "options": ["A", "B", "C", "D"]}, "reference_answer": {"correct": ["A"]}, "explanation": "x"}]',
        '[{"content": {"stem": "q"}, "reference_answer": {"points": ["p"]}, "explanation": "x"}]',
        '[{"content": {"scenario": "s", "task": "t"}, "reference_answer": {"points": ["p"]}, "explanation": "x"}]',
    ])
    a = QuestionGenerationAdapter(s, llm)
    qs = a.generate_by_video("v1", 3)
    assert len(qs) == 3
    assert {q.question_type for q in qs} == {"multi_choice", "short_answer", "scenario"}
    assert all(q.video_id == "v1" for q in qs)


def test_generate_by_video_bad_json_drops_and_continues():
    s = _session()
    s.add_all([
        Video(video_id="v1", chapter_id="c1", title="t", duration_seconds=600),
        VideoAnnotation(video_id="v1", chapter_id="c1", start_sentence="S", end_sentence="E"),
        Chapter(chapter_id="c1", title="ch", content_md="S 内容 E"),
    ])
    s.commit()
    llm = FakeLLMAdapter(responses=["not json", "not json"])  # 重试一次仍失败
    a = QuestionGenerationAdapter(s, llm)
    qs = a.generate_by_video("v1", 3)  # 3 道题至少 3 个题型
    assert qs == []  # 该视频题目全部丢弃，但不抛异常


def test_generate_by_video_anchor_failure_returns_empty():
    # 坏锚点 + 无 fallbackRange：干净跳过（返回空列表），不抛异常
    s = _session()
    s.add_all([
        Video(video_id="v1", chapter_id="c1", title="t", duration_seconds=600),
        VideoAnnotation(video_id="v1", chapter_id="c1", start_sentence="不存在", end_sentence="也不存在"),
        Chapter(chapter_id="c1", title="ch", content_md="正常内容"),
    ])
    s.commit()
    a = QuestionGenerationAdapter(s, FakeLLMAdapter(responses=[]))
    assert a.generate_by_video("v1", 3) == []


def test_generate_by_video_fallback_range_used_on_anchor_failure():
    s = _session()
    s.add_all([
        Video(video_id="v1", chapter_id="c1", title="t", duration_seconds=600),
        VideoAnnotation(video_id="v1", chapter_id="c1",
                        start_sentence="不存在", end_sentence="也不存在",
                        fallback_range="2.1~2.3"),
        Chapter(chapter_id="c1", title="ch", content_md="## 2.1 开头\n知识点内容\n## 2.3 结尾"),
    ])
    s.commit()
    llm = FakeLLMAdapter(responses=[
        '[{"content": {"stem": "q", "options": ["A", "B", "C", "D"]}, "reference_answer": {"correct": "A"}, "explanation": "x"}]',
        '[{"content": {"stem": "q"}, "reference_answer": {"points": ["p"]}, "explanation": "x"}]',
        '[{"content": {"scenario": "s", "task": "t"}, "reference_answer": {"points": ["p"]}, "explanation": "x"}]',
    ])
    a = QuestionGenerationAdapter(s, llm)
    qs = a.generate_by_video("v1", 3)
    assert len(qs) == 3


def test_generate_by_video_code_fill_prompt_instructs_blanking():
    s = _session()
    code_lines = "\n".join(f"line_{i} = {i}" for i in range(12))  # 12 行 > 10 行
    content = f"START 示例代码\n```python\n{code_lines}\n```\nEND"
    s.add_all([
        Video(video_id="v1", chapter_id="c1", title="t", duration_seconds=3600),
        VideoAnnotation(video_id="v1", chapter_id="c1", start_sentence="START", end_sentence="END"),
        Chapter(chapter_id="c1", title="ch", content_md=content),
    ])
    s.commit()
    spy = _SpyLLM("[]")
    a = QuestionGenerationAdapter(s, spy)
    a.generate_by_video("v1", 10)  # has_code=True 才会分配 code_fill
    joined = " ".join(str(m) for m in spy.messages)
    assert "______" in joined  # 挖空占位符
    assert "挖空" in joined
    assert "按顺序" in joined


def test_generate_by_video_prompt_includes_sliced_content():
    s = _session()
    s.add_all([
        Video(video_id="v1", chapter_id="c1", title="t", duration_seconds=600),
        VideoAnnotation(video_id="v1", chapter_id="c1", start_sentence="S", end_sentence="E"),
        Chapter(chapter_id="c1", title="ch", content_md="S 闭包与作用域 E"),
    ])
    s.commit()
    spy = _SpyLLM("[]")
    a = QuestionGenerationAdapter(s, spy)
    a.generate_by_video("v1", 3)
    joined = " ".join(str(m) for m in spy.messages)
    assert "闭包与作用域" in joined
