"""方向/岗位归一化：把用户自由文本匹配到真实课程分类。"""

from contexts.sales_assistant.domain.catalog import SubjectNode

# 一级分类别名 → 真实分类名（顺序即优先级）
_DIRECTION_ALIASES = (
    ("人工智能", ("人工智能", "大模型", "ai", "人工")),
    ("前端开发", ("前端", "web", "网页")),
    ("后端开发", ("后端", "java", "服务端")),
    ("数据库开发", ("数据库", "sql")),
)

# AI 二级（岗位）别名 → 真实岗位名（含旧名「大模型算法岗」兜底）
_POSITION_ALIASES = (
    ("大模型算法开发岗", ("大模型算法开发岗", "大模型算法岗", "算法")),
    ("大模型应用开发岗", ("大模型应用开发岗", "应用")),
    ("大模型公共知识", ("大模型公共知识", "公共")),
)


def normalize_direction(text: str | None) -> str | None:
    """把用户文本归一化到一级分类名；无法匹配返回 None。"""
    if not text or not isinstance(text, str):
        return None
    t = text.strip().lower()
    for canonical, aliases in _DIRECTION_ALIASES:
        if any(a in t for a in aliases):
            return canonical
    return None


def normalize_position(text: str | None) -> str | None:
    """把用户文本归一化到 AI 二级（岗位）名；无法匹配返回 None。"""
    if not text or not isinstance(text, str):
        return None
    t = text.strip().lower()
    for canonical, aliases in _POSITION_ALIASES:
        if any(a in t for a in aliases):
            return canonical
    return None


def find_child(text: str | None, children) -> SubjectNode | None:
    """在二级子分类列表中按名称/别名匹配用户输入，返回命中的节点。"""
    if not text or not isinstance(text, str) or not children:
        return None
    t = text.strip().lower()
    if not t:
        return None
    # 1) 名称包含匹配（覆盖 JavaScript/Java基础 等普通二级）
    for child in children:
        name = (child.name or "").lower()
        if name and (name in t or t in name):
            return child
    # 2) 别名兜底（如旧名「大模型算法岗」→「大模型算法开发岗」）
    target = normalize_position(t)
    if target:
        for child in children:
            if child.name == target:
                return child
    return None
