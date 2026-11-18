import math

from contexts.teaching_assistant.infrastructure.embedding import HashEmbedding


def test_embed_is_deterministic_across_instances():
    a = HashEmbedding().embed("什么是循环结构")
    b = HashEmbedding().embed("什么是循环结构")
    assert a == b


def test_embed_has_fixed_dim_and_non_negative():
    v = HashEmbedding(dim=256).embed("循环结构")
    assert len(v) == 256
    assert all(x >= 0 for x in v)


def test_embed_is_l2_normalized():
    v = HashEmbedding().embed("循环结构用于重复执行一段代码")
    norm = math.sqrt(sum(x * x for x in v))
    assert abs(norm - 1.0) < 1e-9


def test_embed_empty_returns_zero_vector():
    v = HashEmbedding(dim=256).embed("")
    assert v == [0.0] * 256
