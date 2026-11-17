from collections.abc import Generator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from shared.infrastructure.config import get_settings

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def create_engine_and_session_factory(url: str) -> tuple[Engine, sessionmaker[Session]]:
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine = create_engine(url, connect_args=connect_args)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    return engine, factory


def _ensure_initialized() -> None:
    global _engine, _session_factory
    if _engine is None:
        _engine, _session_factory = create_engine_and_session_factory(
            get_settings().database_url
        )


def get_session() -> Generator[Session, None, None]:
    _ensure_initialized()
    session = _session_factory()
    try:
        yield session
    finally:
        session.close()
