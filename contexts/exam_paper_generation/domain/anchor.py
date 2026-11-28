import keyword
import re

_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
# 核心代码位置（优先级从高到低）：方法/属性名 > 函数调用名 > 函数定义名
_CORE_PATTERNS = (
    re.compile(r"\.([A-Za-z_][A-Za-z0-9_]*)"),       # model.forward() -> forward
    re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*\("),    # criterion(...) -> criterion
    re.compile(r"\bdef\s+([A-Za-z_][A-Za-z0-9_]*)"),  # def forward(...) -> forward
)
# 语言关键字（Python）不作为挖空目标，避免题干退化为「补 def/if」这类过浅的空位
_SKIP_TOKENS = set(keyword.kwlist)
# 高频占位标识符（循环变量/self 等），无知识点含量，不作为挖空目标
_COMMON_VARS = {"self", "x", "y", "z", "i", "j", "k", "n"}

CODE_FILL_BLANKS = 3


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
    """任一 ``` 围栏代码块行数 >= min_lines 时返回 True。"""
    in_block = False
    block_lines = 0
    for line in text.split("\n"):
        if line.strip().startswith("```"):
            if in_block:
                if block_lines >= min_lines:
                    return True
                in_block = False
                block_lines = 0
            else:
                in_block = True
                block_lines = 0
        elif in_block:
            block_lines += 1
    return False


def extract_code_blocks(text: str) -> list[str]:
    """提取所有 ``` 围栏代码块的内部代码（不含围栏行与语言标签）。"""
    blocks: list[str] = []
    in_block = False
    current: list[str] = []
    for line in text.split("\n"):
        if line.strip().startswith("```"):
            if in_block:
                blocks.append("\n".join(current))
                current = []
                in_block = False
            else:
                in_block = True
        elif in_block:
            current.append(line)
    return blocks


def blank_code(code: str, num_blanks: int = CODE_FILL_BLANKS) -> tuple[str, list[str]]:
    """从原始代码中确定性挖空若干核心标识符，返回 (挖空后的代码, 被挖空的原始标识符列表)。

    逐行扫描，每行最多挖一个；优先挖方法/属性名、函数调用名、函数定义名，
    答案即为被挖空的原始 token（不重写、不编造）。
    """
    lines = code.split("\n")
    answers: list[str] = []
    used: set[str] = set()
    out: list[str] = []
    for line in lines:
        if len(answers) >= num_blanks:
            out.append(line)
            continue
        picked = _pick_core(line, used)
        if picked is None:
            out.append(line)
            continue
        start, end, token = picked
        placeholder = f"___({len(answers) + 1})___"
        out.append(line[:start] + placeholder + line[end:])
        answers.append(token)
        used.add(token)
    return "\n".join(out), answers


def _pick_core(line: str, used: set[str]) -> tuple[int, int, str] | None:
    """在一行内按优先级挑选一个可挖空的核心标识符，返回 (start, end, token) 或 None。

    优先级：方法/属性名 > 函数调用名 > 函数定义名 > 首个非关键字/占位标识符。
    注释行、空行、无可用标识符的行返回 None。
    """
    stripped = line.strip()
    if not stripped or stripped.startswith(("#", "//", "/*", "*", "'''", '"""')):
        return None
    for pattern in _CORE_PATTERNS:
        for m in pattern.finditer(line):
            token = m.group(1)
            if _is_blankable(token, used):
                start, end = m.span(1)
                return start, end, token
    for m in _IDENT_RE.finditer(line):
        token = m.group(0)
        if _is_blankable(token, used):
            return m.start(), m.end(), token
    return None


def _is_blankable(token: str, used: set[str]) -> bool:
    return token not in _SKIP_TOKENS and token not in _COMMON_VARS and token not in used
