# -*- coding: utf-8 -*-
"""一次性建库脚本。
用法（myenv 环境）：
    python -m contexts.sales_assistant.infrastructure.build_knowledge_base
"""

from contexts.sales_assistant.infrastructure.embeddings import create_embeddings
from contexts.sales_assistant.infrastructure.knowledge_base import (
    build_knowledge_base,
    default_milvus_uri,
)
from shared.infrastructure.config import get_settings


def main() -> None:
    settings = get_settings()
    build_knowledge_base(
        uri=settings.milvus_uri or default_milvus_uri(),
        embedding=create_embeddings(settings.embedding_model),
    )


if __name__ == "__main__":
    main()
