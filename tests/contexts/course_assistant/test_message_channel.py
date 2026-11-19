from contexts.course_assistant.infrastructure.message_channel import StubMessageChannel


def test_send_returns_message_id_and_records():
    ch = StubMessageChannel()
    msg_id = ch.send("s1", "提醒学习")
    assert msg_id.startswith("msg_")
    assert ch.sent == [{"messageId": msg_id, "studentId": "s1", "content": "提醒学习"}]
