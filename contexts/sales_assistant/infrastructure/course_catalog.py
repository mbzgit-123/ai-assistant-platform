"""课程分类/课程列表的外部 HTTP 适配器（码帮智教育平台）。"""

import json
import re
from urllib.request import Request, urlopen

from contexts.sales_assistant.domain.catalog import CourseInfo, SubjectNode


def parse_subject_tree(payload: dict) -> list[SubjectNode]:
    """从 getAllSubject 响应解析分类树。"""
    raw_list = (payload.get("data") or {}).get("list") or []
    return [_parse_node(item, None) for item in raw_list]


def _parse_node(raw: dict, parent_id: str | None) -> SubjectNode:
    node_id = str(raw.get("id") or "")
    children = tuple(_parse_node(c, node_id) for c in (raw.get("children") or []))
    return SubjectNode(
        id=node_id,
        name=raw.get("title") or "",
        parent_id=parent_id,
        children=children,
    )


def parse_course_list(payload: dict) -> list[CourseInfo]:
    """从 getFrontCourseList 响应解析课程列表。"""
    items = (payload.get("data") or {}).get("items") or []
    return [_parse_course(item) for item in items]


def _parse_course(raw: dict) -> CourseInfo:
    return CourseInfo(
        id=str(raw.get("id") or ""),
        title=raw.get("title") or "",
        description=_strip_html(raw.get("description") or ""),
        price=float(raw.get("price") or 0),
        lesson_num=int(raw.get("lessonNum") or 0),
        duration=float(raw.get("duration") or 0),
        cover=raw.get("cover") or "",
    )


def _strip_html(html: str) -> str:
    return re.sub(r"<[^>]+>", "", html).strip()


class MbCourseCatalog:
    """调用外部课程目录接口，并缓存分类树。"""

    def __init__(self, subject_url: str, course_list_url: str, timeout: int = 20):
        self._subject_url = subject_url
        self._course_list_url = course_list_url
        self._timeout = timeout
        self._tree_cache: list[SubjectNode] | None = None

    def get_subject_tree(self) -> list[SubjectNode]:
        if self._tree_cache is None:
            self._tree_cache = parse_subject_tree(self._get_json(self._subject_url))
        return self._tree_cache

    def get_courses(self, subject_id: str, subject_parent_id: str) -> list[CourseInfo]:
        body = json.dumps(
            {"subjectId": subject_id, "subjectParentId": subject_parent_id}
        ).encode("utf-8")
        req = Request(
            self._course_list_url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        return parse_course_list(self._get_json(req))

    def _get_json(self, url_or_req):
        with urlopen(url_or_req, timeout=self._timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
