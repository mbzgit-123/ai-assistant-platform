"""课程分类目录的领域模型。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class SubjectNode:
    """课程分类树中的一个节点（一级/二级/…）。"""

    id: str
    name: str
    parent_id: str | None
    children: tuple["SubjectNode", ...] = ()


@dataclass(frozen=True)
class CourseInfo:
    """课程列表接口返回的一门课程。"""

    id: str
    title: str
    description: str
    price: float
    lesson_num: int
    duration: float
    cover: str


# 内置兜底分类树：外部接口不可用时，仍能列出真实方向/岗位引导用户。
DEFAULT_SUBJECTS: tuple[SubjectNode, ...] = (
    SubjectNode(
        id="1934275035996008450",
        name="人工智能",
        parent_id=None,
        children=(
            SubjectNode(id="2114657204919508994", name="大模型应用开发岗", parent_id="1934275035996008450"),
            SubjectNode(id="2114657205011783682", name="大模型算法开发岗", parent_id="1934275035996008450"),
            SubjectNode(id="2114657479080189954", name="大模型公共知识", parent_id="1934275035996008450"),
        ),
    ),
    SubjectNode(
        id="1934275036142809090",
        name="前端开发",
        parent_id=None,
        children=(
            SubjectNode(id="1934275036176363522", name="JavaScript", parent_id="1934275036142809090"),
            SubjectNode(id="1934275036218306561", name="jquery", parent_id="1934275036142809090"),
        ),
    ),
    SubjectNode(
        id="1934275036251860994",
        name="后端开发",
        parent_id=None,
        children=(
            SubjectNode(id="1934275036285415426", name="Java基础", parent_id="1934275036251860994"),
            SubjectNode(id="1934275036327358466", name="JavaEE", parent_id="1934275036251860994"),
            SubjectNode(id="1934275036365107201", name="框架技术", parent_id="1934275036251860994"),
            SubjectNode(id="1934275036407050241", name="操作系统与架构设计", parent_id="1934275036251860994"),
            SubjectNode(id="1934275036448993282", name="实战项目", parent_id="1934275036251860994"),
        ),
    ),
    SubjectNode(
        id="1934275036495130625",
        name="数据库开发",
        parent_id=None,
        children=(
            SubjectNode(id="1934275036528685058", name="数据库与JDBC", parent_id="1934275036495130625"),
        ),
    ),
)
