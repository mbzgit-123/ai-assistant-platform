import uuid


class StubMessageChannel:
    def __init__(self):
        self.sent: list[dict] = []

    def send(self, student_id: str, content: str) -> str:
        msg_id = "msg_" + uuid.uuid4().hex[:12]
        self.sent.append({"messageId": msg_id, "studentId": student_id, "content": content})
        return msg_id
