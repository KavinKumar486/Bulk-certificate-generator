import os
from pathlib import Path
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.config import settings
from app.db import Base, get_db
import app.models  # noqa: F401
from app.main import app


@pytest.fixture(scope="function")
def temp_storage(tmp_path, monkeypatch):
    storage_path = tmp_path / "storage"
    storage_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "STORAGE_DIR", storage_path)
    return storage_path


@pytest.fixture(scope="function")
def temp_db(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    db_url = f"sqlite:///{db_file.as_posix()}"
    monkeypatch.setattr(settings, "DATABASE_URL", db_url)

    test_engine = create_engine(db_url, connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    import app.db as app_db_module
    monkeypatch.setattr(app_db_module, "engine", test_engine)
    monkeypatch.setattr(app_db_module, "SessionLocal", TestingSessionLocal)

    Base.metadata.create_all(bind=test_engine)

    yield test_engine

    Base.metadata.drop_all(bind=test_engine)
    test_engine.dispose()


@pytest.fixture(scope="function")
def db_session(temp_db):
    import app.db as app_db_module
    session = app_db_module.SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="function")
def client(temp_db, temp_storage):
    import app.db as app_db_module

    def override_get_db():
        session = app_db_module.SessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers():
    return {"X-API-Key": settings.API_KEY}
