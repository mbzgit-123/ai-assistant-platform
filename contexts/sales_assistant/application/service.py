import json
import uuid

from shared.infrastructure.llm.port import LLMPort
from shared.infrastructure.memory.port import MemoryPort

from contexts.sales_assistant.domain.directions import (
    FAQ_ENROLLMENT,
    FAQ_STUDY,
    match_faq,
    normalize_direction,
    normalize_position,
)
from contexts.sales_assistant.domain.ports import VipReportPort
from contexts.sales_assistant.infrastructure.repository import SalesRepository

DIRECTION_PROMPT = "请问你想学习哪个方向？可选：Java、前端、AI。如果还不确定，也可以直接找老师咨询。"
AI_POSITION_PROMPT = "AI 方向有两个岗位方向：大模型算法岗、大模型应用开发岗。你对哪个更感兴趣？"
NO_DIRECTION_PROMPT = "好的，你可以直接找老师咨询，也可以留下联系方式，我们安排老师为你介绍。"
NO_COURSE_REPLY = "抱歉，暂未找到与你方向/岗位匹配的课程。你可以留下联系方式（电话/微信），我们安排顾问老师为你介绍。"
LEAD_ASK_CONTACT_REPLY = "请留下你的联系方式（电话/微信），我们会安排顾问老师尽快联系你。"
LEAD_SAVED_REPLY = "已为你登记，顾问老师会尽快联系你。"

_VALID_INTENTS = {"direction_guide", "course_intro", "enrollment_faq", "study_faq", "lead_capture"}

_INTENT_SYSTEM_PROMPT = (
    "你是教育平台的销售顾问助手。请根据用户消息判断意图，仅输出 JSON，不要输出其他内容。"
    'JSON 格式：{"intent": "<direction_guide|course_intro|enrollment_faq|study_faq|lead_capture>", '
    '"direction": "<用户想学的方向，如 Java/前端/AI，无则空字符串>", '
    '"position": "<AI 方向下的岗位，如 大模型算法岗/大模型应用开发岗，无则空字符串>"}'
)

_CONTACT_SYSTEM_PROMPT = (
    "你是教育平台的销售顾问助手。请从用户消息中提取联系方式，仅输出 JSON，不要输出其他内容。"
    'JSON 格式：{"contact": "<电话或微信号，无则空字符串>", "remark": "<备注，无则空字符串>"}'
)

_FAQ_SYSTEM_PROMPT = "你是教育平台的销售顾问，请用简洁友好的中文回答用户的问题。"

_COURSE_SYSTEM_PROMPT = "你是教育平台的销售顾问，请根据课程列表为用户组织一段简洁的课程推荐话术。"


class SalesChatService:
    def __init__(
        self,
        llm: LLMPort,
        memory: MemoryPort,
        repo: SalesRepository,
        vip_report: VipReportPort,
    ):
        self._llm = llm
        self._memory = memory
        self._repo = repo
        self._vip_report = vip_report

    def chat(self, conversation_id: str | None, message: str, source: str) -> dict:
        conv_id = conversation_id or "c_" + uuid.uuid4().hex[:12]
        state = self._memory.get(conv_id) or {}

        intent = self._recognize_intent(message)
        direction = state.get("direction") or normalize_direction(intent.get("direction"))
        position = state.get("position") or normalize_position(intent.get("position"))

        courses: list[dict] = []
        lead_saved = False

        intent_value = intent["intent"]
        if intent_value == "lead_capture":
            direction = direction or "其他"
            reply, lead_saved = self._handle_lead(direction, position, message, source)
        elif intent_value in ("enrollment_faq", "study_faq"):
            reply = self._handle_faq(message, intent_value)
        elif intent_value == "course_intro":
            if direction is None or direction == "其他" or (direction == "AI" and position is None):
                reply = self._guidance_reply(direction, position)
            else:
                courses = self._repo.find_courses(direction, position)
                if not courses:
                    reply = NO_COURSE_REPLY
                else:
                    reply = self._organize_courses(courses)
        else:
            reply = self._guidance_reply(direction, position)

        self._memory.set(conv_id, {"direction": direction, "position": position})

        return {
            "conversationId": conv_id,
            "reply": reply,
            "direction": direction,
            "position": position,
            "courses": courses,
            "leadSaved": lead_saved,
        }

    def _recognize_intent(self, message: str) -> dict:
        default = {"intent": "direction_guide", "direction": None, "position": None}
        data = self._call_llm_json(
            [
                {"role": "system", "content": _INTENT_SYSTEM_PROMPT},
                {"role": "user", "content": message},
            ],
            default,
        )
        intent = data.get("intent")
        if intent not in _VALID_INTENTS:
            intent = "direction_guide"
        return {"intent": intent, "direction": data.get("direction"), "position": data.get("position")}

    def _handle_lead(self, direction: str, position: str | None, message: str, source: str) -> tuple[str, bool]:
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

    def _handle_faq(self, message: str, intent: str) -> str:
        faq_table = FAQ_ENROLLMENT if intent == "enrollment_faq" else FAQ_STUDY
        answer = match_faq(message, faq_table)
        if answer is not None:
            return answer
        result = self._llm.chat(
            [
                {"role": "system", "content": _FAQ_SYSTEM_PROMPT},
                {"role": "user", "content": message},
            ]
        )
        return result.content

    def _organize_courses(self, courses: list[dict]) -> str:
        result = self._llm.chat(
            [
                {"role": "system", "content": _COURSE_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(courses, ensure_ascii=False)},
            ]
        )
        return result.content

    def _guidance_reply(self, direction: str | None, position: str | None) -> str:
        if direction is None:
            return DIRECTION_PROMPT
        if direction == "其他":
            return NO_DIRECTION_PROMPT
        if direction == "AI" and position is None:
            return AI_POSITION_PROMPT
        if position:
            return f"已了解你的方向：{direction}，岗位：{position}"
        return f"已了解你的方向：{direction}"

    def _call_llm_json(self, messages: list[dict[str, str]], default: dict) -> dict:
        for _ in range(2):
            content = self._llm.chat(messages).content
            try:
                data = json.loads(content)
            except (ValueError, TypeError):
                continue
            if isinstance(data, dict):
                return data
        return default
