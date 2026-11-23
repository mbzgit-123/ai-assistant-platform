import json
from unittest.mock import patch

from contexts.sales_assistant.infrastructure.course_catalog import (
    MbCourseCatalog,
    parse_course_list,
    parse_subject_tree,
)


SAMPLE_TREE = {
    "success": True,
    "data": {
        "list": [
            {
                "id": "1934275035996008450",
                "title": "人工智能",
                "children": [
                    {"id": "2114657204919508994", "title": "大模型应用开发岗"},
                    {"id": "2114657205011783682", "title": "大模型算法开发岗"},
                ],
            },
            {"id": "1934275036142809090", "title": "前端开发", "children": []},
        ]
    },
}


def test_parse_subject_tree():
    nodes = parse_subject_tree(SAMPLE_TREE)
    assert [n.name for n in nodes] == ["人工智能", "前端开发"]
    ai = nodes[0]
    assert ai.id == "1934275035996008450"
    assert ai.parent_id is None
    assert [c.name for c in ai.children] == ["大模型应用开发岗", "大模型算法开发岗"]
    assert ai.children[0].parent_id == ai.id


SAMPLE_COURSES = {
    "data": {
        "items": [
            {
                "id": "1953303162097172481",
                "title": "第一模块:AI的历史与认知",
                "description": "<p>本课程围绕人工智能</p>",
                "duration": 9902.0,
                "price": 0.00,
                "lessonNum": 18,
                "cover": "https://x/y.jpg",
            }
        ]
    }
}


def test_parse_course_list():
    courses = parse_course_list(SAMPLE_COURSES)
    assert len(courses) == 1
    c = courses[0]
    assert c.id == "1953303162097172481"
    assert c.title == "第一模块:AI的历史与认知"
    assert c.description == "本课程围绕人工智能"
    assert c.price == 0.0
    assert c.lesson_num == 18
    assert c.duration == 9902.0
    assert c.cover == "https://x/y.jpg"


def test_get_subject_tree_caches():
    catalog = MbCourseCatalog("http://x/subject", "http://x/course")
    with patch.object(catalog, "_get_json", return_value=SAMPLE_TREE) as get:
        catalog.get_subject_tree()
        catalog.get_subject_tree()
    assert get.call_count == 1


def test_get_courses_posts_body():
    catalog = MbCourseCatalog("http://x/subject", "http://x/course")
    with patch.object(catalog, "_get_json", return_value=SAMPLE_COURSES) as get:
        courses = catalog.get_courses("2114657205011783682", "1934275035996008450")
    assert len(courses) == 1
    req = get.call_args.args[0]
    assert json.loads(req.data.decode("utf-8")) == {
        "subjectId": "2114657205011783682",
        "subjectParentId": "1934275035996008450",
    }
