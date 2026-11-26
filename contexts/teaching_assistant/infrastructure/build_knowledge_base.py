# -*- coding: utf-8 -*-
"""一次性建库脚本（读 chunks.jsonl → BGE-M3 → Milvus）。

用法（myenv 环境，项目根目录执行）：
    python -m contexts.teaching_assistant.infrastructure.build_knowledge_base
"""

from contexts.teaching_assistant.infrastructure.knowledge_base import (
    build_knowledge_base,
    default_milvus_uri,
)
from shared.infrastructure.config import get_settings
from shared.infrastructure.embeddings import create_embeddings


def main() -> None:
    settings = get_settings()
    build_knowledge_base(
        uri=default_milvus_uri(),
        embedding=create_embeddings(settings.embedding_model),
    )


if __name__ == "__main__":
    main()
