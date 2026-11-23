from dataclasses import dataclass


@dataclass(frozen=True)
class FaqHit:
    """知识库检索命中的一条 FAQ 片段。"""

    question: str
    content: str
    score: float


# 检索返回的片段数（可在依赖装配处用 Settings.sales_faq_top_k 覆盖）
FAQ_TOP_K = 4

# 命中分数阈值：score 低于该值的片段视为不相关，不进 sources 也不喂给 LLM
FAQ_MIN_SCORE = 0.65

# 知识库无命中时的兜底回复（引导留资 / 转顾问老师）
FAQ_NO_MATCH_REPLY = (
    "抱歉，这个问题我暂时无法准确解答。你可以留下联系方式（电话/微信），"
    "我安排顾问老师为你详细解答。"
)

# 基于知识库生成回答的系统提示词（迁移自旧项目 rag_service.SYSTEM_PROMPT）
FAQ_SYSTEM_PROMPT = (
    "你是「智能营销助手」的客服。请直接、自然地回答用户问题，"
    "就像你自己就掌握这些信息一样。\n"
    "要求：\n"
    "1. 回答内容必须严格基于下方提供的知识库内容，不要编造；\n"
    "2. 用你自己的话重新组织语言，不要逐字照抄知识库原文；\n"
    "3. 不要使用「→」「-」等符号，改用「然后」「接着」「最后」等口语连接词；\n"
    "4. 禁止出现「资料」「知识库」「根据资料」等字眼，不要暴露信息来源；\n"
    "5. 如果知识库不足以回答，直接说明暂时无法解答；\n"
    "6. 用简洁、友好、口语化的中文回答。"
)
