from unittest.mock import patch

from contexts.teaching_assistant.interface import dependencies as deps


def test_ensure_indexed_reads_chapters_once():
    deps._indexed = False
    calls = []

    class _FakeRepo:
        def __init__(self, session):
            self._session = session

        def list_chapters(self):
            calls.append(1)
            return []

    with patch.object(deps, "TeachingRepository", _FakeRepo):
        deps._ensure_indexed(object())
        deps._ensure_indexed(object())

    assert len(calls) == 1
