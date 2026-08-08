from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base, get_session
from app.main import app


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """Use an isolated on-disk SQLite database for every API test."""

    test_dir = Path("data/test-runs")
    test_dir.mkdir(parents=True, exist_ok=True)
    database_path = test_dir / f"{uuid4().hex}.db"
    engine = create_engine(f"sqlite:///{database_path.as_posix()}", connect_args={"check_same_thread": False})
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    def override_session() -> Generator[Session, None, None]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_session] = override_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    for suffix in ("", "-journal", "-shm", "-wal"):
        database_path.with_name(f"{database_path.name}{suffix}").unlink(missing_ok=True)
