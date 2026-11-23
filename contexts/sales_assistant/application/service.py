"""销售助手对话服务。

负责一次完整对话的处理流程：
1. 识别用户意图（方向引导 / 课程介绍 / 报名 FAQ / 学习 FAQ / 留资）；
2. 结合会话记忆中的方向与岗位，决定后续动作；
3. 分派到具体处理器：留资、知识库 FAQ 问答、课程分类引导（一级→二级→课程）；
4. 把最新识别到的方向/岗位写回会话记忆，并返回结构化结果。
"""

import json
import uuid
from collections.abc import Iterator

from shared.infrastructure.llm.port import LLMPort
from shared.infrastructure.memory.port import MemoryPort

from contexts.sales_assistant.domain.catalog import (
    DEFAULT_SUBJECTS,
    CourseInfo,
    SubjectNode,
)
from contexts.sales_assistant.domain.directions import find_child, normalize_direction
from contexts.sales_assistant.domain.faq import (
    FAQ_MIN_SCORE,
    FAQ_NO_MATCH_REPLY,
    FAQ_SYSTEM_PROMPT,
    FAQ_TOP_K,
)
from contexts.sales_assistant.domain.ports import (
    CourseCatalogPort,
    KnowledgeBasePort,
    VipReportPort,
)
from contexts.sales_assistant.infrastructure.repository import SalesRepository

# 课程列表无匹配时的提示，并引导留资
NO_COURSE_REPLY = "抱歉，暂未找到与你方向/岗位匹配的课程。你可以留下联系方式（电话/微信），我们安排顾问老师为你介绍。"
# 留资场景下未提取到联系方式时的追问话术
LEAD_ASK_CONTACT_REPLY = (
    "请留下你的联系方式（电话/微信），我们会安排顾问老师尽快联系你。"
)
# 留资成功后的确认话术
LEAD_SAVED_REPLY = "已为你登记，顾问老师会尽快联系你。"

# 允许的意图取值集合；LLM 返回其他值时统一回退为 direction_guide
_VALID_INTENTS = {
    "direction_guide",  # 方向引导
    "course_intro",  # 课程介绍/推荐
    "enrollment_faq",  # 报名相关 FAQ
    "study_faq",  # 学习相关 FAQ
    "lead_capture",  # 留资（收集联系方式）
}

# 意图识别用的系统提示词：要求 LLM 只输出指定结构的 JSON
_INTENT_SYSTEM_PROMPT = (
    "你是教育平台的销售顾问助手。请根据用户消息判断意图，仅输出 JSON，不要输出其他内容。"
    'JSON 格式：{"intent": "<direction_guide|course_intro|enrollment_faq|study_faq|lead_capture>", '
    '"direction": "<用户想学的方向，如 人工智能/前端开发/后端开发/数据库开发，无则空字符串>", '
    '"position": "<方向下的子分类，如 大模型算法开发岗/JavaScript，无则空字符串>"}'
)

# 联系方式提取用的系统提示词：要求 LLM 只输出指定结构的 JSON
_CONTACT_SYSTEM_PROMPT = (
    "你是教育平台的销售顾问助手。请从用户消息中提取联系方式，仅输出 JSON，不要输出其他内容。"
    'JSON 格式：{"contact": "<电话或微信号，无则空字符串>", "remark": "<备注，无则空字符串>"}'
)

# 课程推荐话术组织用的系统提示词
_COURSE_SYSTEM_PROMPT = (
    "你是教育平台的销售顾问。用户想了解某个分类下的课程，请根据课程列表"
    "客观、简洁地介绍这些课程，只介绍课程名称与核心内容，"
    "不要展示课时和价格，"
    "不要假设或提及用户的学习路径、已有基础或学习进度，也不要虚构课程列表之外的信息。"
)


def _find_node(nodes, node_id: str) -> SubjectNode | None:
    """按 id 在分类树中递归查找节点。"""
    for n in nodes:
        if n.id == node_id:
            return n
        found = _find_node(n.children, node_id)
        if found:
            return found
    return None


class SalesChatService:
    """销售助手对话服务：编排意图识别、会话记忆、课程分类、FAQ 与留资。"""

    def __init__(
        self,
        llm: LLMPort,
        memory: MemoryPort,
        repo: SalesRepository,
        vip_report: VipReportPort,
        kb: KnowledgeBasePort,
        faq_top_k: int = FAQ_TOP_K,
        catalog: CourseCatalogPort | None = None,
    ):
        """
        Args:
            llm: 大模型调用端口，用于意图识别、信息抽取与话术生成。
            memory: 会话记忆端口，按 conversation_id 保存方向/岗位等状态。
            repo: 销售数据仓储，用于保存线索。
            vip_report: VIP 线索上报端口，留资成功后触发上报。
            kb: 知识库检索端口，用于 FAQ 语义检索。
            faq_top_k: FAQ 检索返回的条数上限。
            catalog: 课程分类目录端口；为空时用内置兜底分类，课程查询返回空。
        """
        self._llm = llm
        self._memory = memory
        self._repo = repo
        self._vip_report = vip_report
        self._kb = kb
        self._faq_top_k = faq_top_k
        self._catalog = catalog
        self._tree_cache: list[SubjectNode] | None = None

    def chat(self, conversation_id: str | None, message: str, source: str) -> dict:
        """处理一条用户消息，返回本轮对话结果。"""
        conv_id = conversation_id or "c_" + uuid.uuid4().hex[:12]
        routed = self._route(conv_id, message, source)
        if routed["llm_messages"] is not None:
            reply = self._llm.chat(routed["llm_messages"]).content
        else:
            reply = routed["reply"]
        return {
            "conversationId": routed["conversationId"],
            "reply": reply,
            "direction": routed["direction"],
            "position": routed["position"],
            "courses": routed["courses"],
            "leadSaved": routed["leadSaved"],
            "sources": routed["sources"],
        }

    def chat_stream(
        self, conversation_id: str | None, message: str, source: str
    ) -> Iterator[dict]:
        """处理一条用户消息，以 SSE 事件流（meta / delta / done / error）返回回复。"""
        conv_id = conversation_id or "c_" + uuid.uuid4().hex[:12]
        try:
            routed = self._route(conv_id, message, source)
            yield {
                "type": "meta",
                "conversationId": routed["conversationId"],
                "direction": routed["direction"],
                "position": routed["position"],
                "courses": routed["courses"],
                "leadSaved": routed["leadSaved"],
                "sources": routed["sources"],
            }
            if routed["llm_messages"] is not None:
                for chunk in self._llm.stream(routed["llm_messages"]):
                    yield {"type": "delta", "content": chunk}
            else:
                yield {"type": "delta", "content": routed["reply"]}
        except Exception:
            # 生成失败时下发终止事件，避免客户端因断流而无法区分「完成」与「出错」
            yield {"type": "error", "message": "回复生成失败，请稍后重试"}
            return
        yield {"type": "done"}

    def _route(self, conv_id: str, message: str, source: str) -> dict:
        """识别意图并路由到对应处理，返回生成回复所需的全部信息（不含最终回复文本）。"""
        state = self._memory.get(conv_id) or {}
        intent = self._recognize_intent(message, state)

        courses: list[dict] = []
        lead_saved = False
        sources: list[dict] = []
        reply: str | None = None
        llm_messages: list[dict[str, str]] | None = None
        direction_name = state.get("direction")
        position_name = state.get("position")
        direction_id = state.get("direction_id")
        position_id = state.get("position_id")

        intent_value = intent["intent"]
        if intent_value == "lead_capture":
            direction_name = (
                state.get("direction")
                or normalize_direction(intent.get("direction"))
                or "其他"
            )
            position_name = state.get("position")
            reply, lead_saved = self._handle_lead(
                direction_name, position_name, message, source
            )
        elif intent_value in ("enrollment_faq", "study_faq"):
            llm_messages, sources = self._faq_messages(message)
            if llm_messages is None:
                reply = FAQ_NO_MATCH_REPLY
        else:
            # course_intro / direction_guide → 多轮分类引导（一级 → 二级 → 课程）
            direction_node, position_node, reply, courses, llm_messages = (
                self._subject_flow(state, intent)
            )
            direction_name = direction_node.name if direction_node else None
            position_name = position_node.name if position_node else None
            direction_id = direction_node.id if direction_node else None
            position_id = position_node.id if position_node else None

        self._memory.set(
            conv_id,
            {
                "direction": direction_name,
                "direction_id": direction_id,
                "position": position_name,
                "position_id": position_id,
            },
        )
        return {
            "conversationId": conv_id,
            "direction": direction_name,
            "position": position_name,
            "courses": courses,
            "leadSaved": lead_saved,
            "sources": sources,
            "reply": reply,
            "llm_messages": llm_messages,
        }

    def _subject_flow(
        self, state: dict, intent: dict
    ) -> tuple[SubjectNode | None, SubjectNode | None, str | None, list[dict], list | None]:
        """课程分类多轮引导：解析一级/二级，返回节点与回复/课程。"""
        tree = self._get_subject_tree()
        direction_node = self._resolve_direction(state, intent, tree)
        position_node = self._resolve_position(state, intent, direction_node)

        if direction_node is None:
            return None, None, self._directions_prompt(tree), [], None
        if position_node is None:
            return direction_node, None, self._positions_prompt(direction_node), [], None

        courses = self._fetch_courses(direction_node, position_node)
        if not courses:
            return direction_node, position_node, NO_COURSE_REPLY, [], None
        llm_messages = [
            {"role": "system", "content": _COURSE_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(courses, ensure_ascii=False),
            },
        ]
        return direction_node, position_node, None, courses, llm_messages

    def _resolve_direction(
        self, state: dict, intent: dict, tree: list[SubjectNode]
    ) -> SubjectNode | None:
        """解析一级分类：记忆优先，其次本轮意图文本。"""
        if state.get("direction_id"):
            node = _find_node(tree, state["direction_id"])
            if node:
                return node
        name = normalize_direction(intent.get("direction"))
        if name:
            for node in tree:
                if node.name == name:
                    return node
        return None

    def _resolve_position(
        self, state: dict, intent: dict, direction_node: SubjectNode | None
    ) -> SubjectNode | None:
        """解析二级分类：在已选一级的子分类中匹配。"""
        if direction_node is None:
            return None
        if state.get("position_id"):
            for child in direction_node.children:
                if child.id == state["position_id"]:
                    return child
        text = intent.get("position") or intent.get("direction")
        return find_child(text, direction_node.children)

    def _get_subject_tree(self) -> list[SubjectNode]:
        """获取分类树（缓存；接口失败降级到内置兜底）。"""
        if self._tree_cache is None:
            tree: list[SubjectNode] = list(DEFAULT_SUBJECTS)
            if self._catalog is not None:
                try:
                    tree = self._catalog.get_subject_tree()
                except Exception:
                    tree = list(DEFAULT_SUBJECTS)
            self._tree_cache = tree
        return self._tree_cache

    def _fetch_courses(
        self, direction_node: SubjectNode, position_node: SubjectNode
    ) -> list[dict]:
        """按二级+一级 id 查课程列表，失败返回空。"""
        if self._catalog is None:
            return []
        try:
            infos = self._catalog.get_courses(position_node.id, direction_node.id)
        except Exception:
            return []
        return [self._course_to_dict(c) for c in infos]

    def _course_to_dict(self, c: CourseInfo) -> dict:
        return {
            "courseId": c.id,
            "name": c.title,
            "duration": c.duration,
            "cover": c.cover,
            "description": c.description,
        }

    def _directions_prompt(self, tree: list[SubjectNode]) -> str:
        names = "、".join(n.name for n in tree)
        return (
            f"请问你想了解哪个方向？可选：{names}。"
            "如果还不确定，也可以直接找老师咨询。"
        )

    def _positions_prompt(self, direction_node: SubjectNode) -> str:
        names = "、".join(c.name for c in direction_node.children)
        return f"「{direction_node.name}」下可选：{names}。你对哪个更感兴趣？"

    def _recognize_intent(self, message: str, state: dict) -> dict:
        """调用 LLM 识别用户意图，并抽取方向与岗位。"""
        default = {"intent": "direction_guide", "direction": None, "position": None}
        messages = [{"role": "system", "content": _INTENT_SYSTEM_PROMPT}]
        context_parts = []
        if state.get("direction"):
            context_parts.append(f"已识别方向: {state.get('direction')}")
        if state.get("position"):
            context_parts.append(f"岗位: {state.get('position')}")
        if context_parts:
            messages.append({"role": "system", "content": " / ".join(context_parts)})
        messages.append({"role": "user", "content": message})
        data = self._call_llm_json(messages, default)
        intent = data.get("intent")
        if intent not in _VALID_INTENTS:
            intent = "direction_guide"
        return {
            "intent": intent,
            "direction": data.get("direction"),
            "position": data.get("position"),
        }

    def _handle_lead(
        self, direction: str, position: str | None, message: str, source: str
    ) -> tuple[str, bool]:
        """处理留资：抽取联系方式，保存线索并触发 VIP 上报。"""
        data = self._call_llm_json(
            [
                {"role": "system", "content": _CONTACT_SYSTEM_PROMPT},
                {"role": "user", "content": message},
            ],
            {"contact": "", "remark": ""},
        )
        contact = data.get("contact") or ""
        remark = data.get("remark") or None
        if not contact:
            return LEAD_ASK_CONTACT_REPLY, False
        lead = self._repo.save_lead(contact, direction, position, remark, source)
        self._vip_report.report_vip(lead)
        return LEAD_SAVED_REPLY, True

    def _faq_messages(self, message: str) -> tuple[list[dict[str, str]] | None, list[dict]]:
        """检索知识库并构建 FAQ 的 LLM 消息。"""
        try:
            hits = self._kb.search(message, top_k=self._faq_top_k)
        except Exception:
            return None, []
        hits = [h for h in hits if h.score >= FAQ_MIN_SCORE]
        if not hits:
            return None, []
        context = "\n\n".join(f"[{i}] {h.content}" for i, h in enumerate(hits, start=1))
        messages = [
            {"role": "system", "content": FAQ_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"【知识库内容】\n{context}\n\n"
                    f"【用户问题】\n{message}\n\n"
                    "请根据知识库内容回答用户问题。"
                ),
            },
        ]
        sources = [
            {"question": h.question, "content": h.content, "score": h.score}
            for h in hits
        ]
        return messages, sources

    def _call_llm_json(self, messages: list[dict[str, str]], default: dict) -> dict:
        """调用 LLM 并解析 JSON 输出，最多重试一次。"""
        for _ in range(2):
            content = self._llm.chat(messages).content
            try:
                data = json.loads(content)
            except (ValueError, TypeError):
                continue
            if isinstance(data, dict):
                return data
        return default
