def fuse_summaries(items: list[tuple[str, str]]) -> str:
    """把 (标题, 摘要) 列表融合成一份章节要点文档，作为章节考试出题上下文。

    - 跳过空摘要（仅空白也算空）
    - 有标题时以二级标题作为小节头，帮助出题 Agent 感知结构
    - 小节之间以空行分隔
    - 全部为空时返回空字符串
    """
    parts: list[str] = []
    for title, summary in items:
        summary = (summary or "").strip()
        if not summary:
            continue
        title = (title or "").strip()
        if title:
            parts.append(f"## {title}\n{summary}")
        else:
            parts.append(summary)
    return "\n\n".join(parts)
