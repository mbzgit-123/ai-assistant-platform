from contexts.teaching_assistant.infrastructure.handoff import StubHandoff


def test_create_handoff_returns_ticket_id():
    h = StubHandoff()
    ticket = h.create_handoff("什么是循环结构", "s_1")
    assert ticket.startswith("ticket_")
