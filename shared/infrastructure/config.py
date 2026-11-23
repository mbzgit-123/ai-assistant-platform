from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "ai-assistant-platform"
    env: str = "dev"
    database_url: str = "sqlite:///./data/app.db"
    llm_provider: Literal["deepseek", "fake"] = "fake"
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    llm_timeout_seconds: int = 60
    llm_max_retries: int = 1

    embedding_model: str = "BAAI/bge-m3"
    milvus_uri: str = ""
    retrieval_mode: Literal["dense", "hybrid"] = "dense"
    sales_faq_top_k: int = 4

    subject_api_url: str = "https://www.mbz-edu.cn/eduservice/subject/getAllSubject"
    course_list_api_url: str = (
        "https://www.mbz-edu.cn/eduservice/coursefront/getFrontCourseList/1/12/undefined"
    )

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
