from shared.infrastructure.config import Settings


def test_defaults():
    s = Settings(_env_file=None)
    assert s.llm_provider == "fake"
    assert s.database_url == "sqlite:///./data/app.db"


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    s = Settings(_env_file=None)
    assert s.llm_provider == "deepseek"
    assert s.deepseek_api_key == "sk-test"
