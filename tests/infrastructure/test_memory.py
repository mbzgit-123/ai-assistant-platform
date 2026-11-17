from shared.infrastructure.memory.in_memory import InMemoryStore


def test_set_get_delete():
    s = InMemoryStore()
    s.set("k", 1)
    assert s.get("k") == 1
    s.delete("k")
    assert s.get("k", default="d") == "d"


def test_ttl_expiry(monkeypatch):
    s = InMemoryStore()
    s.set("k", 1, ttl_seconds=10)
    assert s.get("k") == 1
    monkeypatch.setattr(
        "shared.infrastructure.memory.in_memory.time.monotonic", lambda: 999999
    )
    assert s.get("k", default="expired") == "expired"
