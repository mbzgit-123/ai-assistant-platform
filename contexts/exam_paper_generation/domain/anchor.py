def slice_content_md(content_md: str, start_sentence: str, end_sentence: str) -> str | None:
    """在章节 Markdown 中按首句/尾句锚点截取区间，任一未命中返回 None。"""
    start_idx = content_md.find(start_sentence)
    if start_idx == -1:
        return None
    end_idx = content_md.find(end_sentence, start_idx)
    if end_idx == -1:
        return None
    return content_md[start_idx : end_idx + len(end_sentence)]


def split_long_interval(text: str, max_chars: int = 2000) -> str:
    """超长区间按段落边界（换行）截断到 max_chars 以内，不硬切。"""
    if len(text) <= max_chars:
        return text
    result = ""
    for line in text.split("\n"):
        candidate = line if not result else result + "\n" + line
        if len(candidate) > max_chars:
            break
        result = candidate
    return result


def has_code_block(text: str, min_lines: int = 10) -> bool:
    """任一 ``` 围栏代码块行数 > min_lines 时返回 True。"""
    in_block = False
    block_lines = 0
    for line in text.split("\n"):
        if line.strip().startswith("```"):
            if in_block:
                if block_lines > min_lines:
                    return True
                in_block = False
                block_lines = 0
            else:
                in_block = True
                block_lines = 0
        elif in_block:
            block_lines += 1
    return False
