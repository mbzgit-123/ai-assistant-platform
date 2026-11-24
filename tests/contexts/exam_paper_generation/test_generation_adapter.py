from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from shared.infrastructure.db.base import Base
import shared.infrastructure.db.models  # noqa: F401
from shared.infrastructure.db.models.sync_cache import Video, VideoAnnotation, Chapter
from shared.infrastructure.llm.fake import FakeLLMAdapter
from shared.infrastructure.llm.port import LLMResult
from contexts.exam_paper_generation.infrastructure.adapter import (
    QuestionGenerationAdapter,
    _extract_json_list,
)


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
    assert "___(1)___" in joined  # 带编号挖空占位符
    assert "挖空" in joined
    assert "按编号顺序" in joined


def test_generate_by_video_multi_choice_prompt_instructs_variable_count():
    s = _session()
    s.add_all([
        Video(video_id="v1", chapter_id="c1", title="t", duration_seconds=600),
        VideoAnnotation(video_id="v1", chapter_id="c1", start_sentence="S", end_sentence="E"),
        Chapter(chapter_id="c1", title="ch", content_md="S 内容 E"),
    ])
    s.commit()
    spy = _SpyLLM("[]")
    a = QuestionGenerationAdapter(s, spy)
    a.generate_by_video("v1", 3)
    joined = " ".join(str(m) for m in spy.messages)
    assert "不定项" in joined  # 明确告诉 LLM 是不定项
    assert "2 个及以上" in joined  # 要求部分题目有多个正确项
    assert "选项字母" in joined  # correct 用字母表示


def test_generate_by_video_prompt_forbids_context_prefix():
    s = _session()
    s.add_all([
        Video(video_id="v1", chapter_id="c1", title="t", duration_seconds=600),
        VideoAnnotation(video_id="v1", chapter_id="c1", start_sentence="S", end_sentence="E"),
        Chapter(chapter_id="c1", title="ch", content_md="S 内容 E"),
    ])
    s.commit()
    spy = _SpyLLM("[]")
    a = QuestionGenerationAdapter(s, spy)
    a.generate_by_video("v1", 3)
    joined = " ".join(str(m) for m in spy.messages)
    assert "根据以下课程内容" not in joined  # 旧措辞会诱导 LLM 在题干中复读「根据课程内容」
    assert "下面是课程内容" in joined
    assert "前缀" in joined  # 显式约束题干不要带「根据课程内容」等前缀


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


def test_generate_from_document_slices_and_generates():
    s = _session()
    doc = "# 标题\n○ 机器学习概念\n● 深度学习概念\n结束句"
    llm = FakeLLMAdapter(responses=[
        '[{"content": {"stem": "q", "options": ["A", "B", "C", "D"]}, "reference_answer": {"correct": ["A"]}, "explanation": "x"}]',
        '[{"content": {"stem": "q"}, "reference_answer": {"points": ["p"]}, "explanation": "x"}]',
        '[{"content": {"scenario": "s", "task": "t"}, "reference_answer": {"points": ["p"]}, "explanation": "x"}]',
    ])
    a = QuestionGenerationAdapter(s, llm)
    qs = a.generate_from_document(doc)
    assert {q.question_type for q in qs} == {"multi_choice", "short_answer", "scenario"}
    assert all(q.video_id == "" for q in qs)


def test_generate_from_document_empty_doc_returns_empty():
    s = _session()
    a = QuestionGenerationAdapter(s, FakeLLMAdapter(responses=[]))
    assert a.generate_from_document("   \n  ") == []


def test_generate_from_document_code_block_triggers_code_fill():
    s = _session()
    code_lines = "\n".join(f"line_{i} = {i}" for i in range(15))  # 15 行 >= 15
    doc = f"START\n```python\n{code_lines}\n```\nEND"
    spy = _SpyLLM("[]")
    a = QuestionGenerationAdapter(s, spy)
    a.generate_from_document(doc)
    joined = " ".join(str(m) for m in spy.messages)
    assert "挖空" in joined  # 分配了 code_fill 题型，prompt 含挖空指令


def test_generate_from_document_short_code_block_skips_code_fill():
    s = _session()
    doc = "START\n```python\nprint(1)\n```\nEND"
    spy = _SpyLLM("[]")
    a = QuestionGenerationAdapter(s, spy)
    a.generate_from_document(doc)
    joined = " ".join(str(m) for m in spy.messages)
    assert "挖空" not in joined  # 代码块 <15 行，不出代码题


def test_extract_json_list_strips_code_fence():
    raw = '```json\n[{"a": 1}]\n```'
    assert _extract_json_list(raw) == [{"a": 1}]


def test_extract_json_list_wraps_single_object():
    assert _extract_json_list('{"a": 1}') == [{"a": 1}]


def test_extract_json_list_returns_none_on_garbage():
    assert _extract_json_list("不是 json") is None
