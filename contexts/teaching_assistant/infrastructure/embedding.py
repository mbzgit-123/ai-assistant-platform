import hashlib
import math


class HashEmbedding:
    """字符 2-gram / 3-gram 哈希计数向量（非负、固定维度、L2 归一化）。

    哈希用 md5 摘要转整数取模，禁用 Python 内置 hash()（进程级随机）。
    """

    def __init__(self, dim: int = 256):
        self._dim = dim

    def embed(self, text: str) -> list[float]:
        if not text:
            return [0.0] * self._dim

        counts = [0.0] * self._dim
        for n in (2, 3):
            for i in range(len(text) - n + 1):
                gram = text[i : i + n]
                digest = hashlib.md5(gram.encode("utf-8")).digest()
                idx = int.from_bytes(digest, "big") % self._dim
                counts[idx] += 1.0

        norm = math.sqrt(sum(x * x for x in counts))
        if norm == 0.0:
            return [0.0] * self._dim
        return [x / norm for x in counts]
