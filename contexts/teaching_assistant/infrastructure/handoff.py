import uuid


class StubHandoff:
    def create_handoff(self, question: str, student_id: str | None) -> str:
        return "ticket_" + uuid.uuid4().hex[:12]
