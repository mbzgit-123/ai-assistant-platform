import re

# 非标准项目符号（富文本/Word 转换残留）
_BULLET_RE = re.compile(r"^[○●▪·•]\s*")
# 箭头残留（-->、----> 等）
_ARROW_DASH_RE = re.compile(r"-{2,}>")
_ARROW_SYMBOL_RE = re.compile(r"→")
# 错位的引用符号（行首 > + 空白）
_MISPLACED_QUOTE_RE = re.compile(r"^>\s*")
# 编号后多余空格（1.  文本 -> 1. 文本）
_NUMBER_SPACING_RE = re.compile(r"^(\d+)\.\s{2,}")
# 编号标题后缺空格（4.1理解 -> 4.1 理解）
_HEADING_SPACING_RE = re.compile(r"^(\d+(?:\.\d+)+)(?=[^\s\d])")
# 行内连续空格
_MULTI_SPACE_RE = re.compile(r" {2,}")


def clean_markdown(text: str) -> str:
    """清洗课程文档中的非规范 Markdown 杂质，保留 ``` 围栏代码块原样。

    - 项目符号 ○/●/▪/·/• -> 标准列表符号 -
    - 箭头残留 -->/---->、→ -> 删除
    - 错位引用 > -> 删除
    - 编号后多余空格规整
    - 连续空行折叠
    """
    out: list[str] = []
    in_code = False
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            out.append(line)
            continue
        if in_code:
            out.append(line)
            continue
        out.append(_clean_text_line(line))
    result = "\n".join(out)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


def _clean_text_line(line: str) -> str:
    line = line.strip()
    line = _BULLET_RE.sub("- ", line)
    line = _ARROW_DASH_RE.sub("", line)
    line = _ARROW_SYMBOL_RE.sub("", line)
    line = _MISPLACED_QUOTE_RE.sub("", line)
    line = _NUMBER_SPACING_RE.sub(r"\1. ", line)
    line = _HEADING_SPACING_RE.sub(r"\1 ", line)
    line = _MULTI_SPACE_RE.sub(" ", line)
    return line
