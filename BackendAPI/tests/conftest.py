import typing as t
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

# Import app and models from the application
# We use direct imports because tests live inside BackendAPI/tests
from src.api.main import app, Base, User, StudySession, get_db, hash_password


def get_sqlite_memory_engine():
    """
    Create a SQLite in-memory engine with shared cache so multiple connections
    (sessions) see the same in-memory DB during a test session.
    """
    # Use file-based in-memory with shared cache to allow multiple connections
    # across the same process. URI mode enables shared cache.
    db_url = "sqlite+pysqlite:///file::memory:?cache=shared&uri=true"
    engine = create_engine(db_url, future=True)
    return engine


@pytest.fixture(scope="session")
def test_engine():
    """
    Create the test engine once per test session.
    """
    engine = get_sqlite_memory_engine()
    # Create tables for tests
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def SessionTesting(test_engine):
    """
    Return a sessionmaker bound to the test engine.
    """
    return sessionmaker(bind=test_engine, autoflush=False, autocommit=False, future=True)


@pytest.fixture(autouse=True)
def _override_db_dependency(SessionTesting):
    """
    Automatically override the application's get_db dependency to use the
    SQLite in-memory session for the duration of each test.

    This ensures tests never touch the production DATABASE_URL.
    """
    def get_test_db() -> t.Iterator[Session]:
        db = SessionTesting()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = get_test_db
    # Ensure tables exist (init_db uses global engine but here our override supplies sessions for routes)
    yield
    # Cleanup override after each test to avoid leakage
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture()
def client():
    """
    Provide a TestClient bound to our FastAPI app.
    """
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def create_user(SessionTesting):
    """
    Helper factory to create a user directly in the DB for tests.
    Returns the created User ORM object.
    """
    def _create_user(email: str, password: str = "Passw0rd!"):
        with SessionTesting() as db:
            user = User(email=email.lower(), password_hash=hash_password(password))
            db.add(user)
            db.commit()
            db.refresh(user)
            return user
    return _create_user


@pytest.fixture()
def auth_headers(client):
    """
    Factory that registers a user and returns Authorization headers for them.
    """
    def _auth_headers(email: str = "alice@example.com", password: str = "Passw0rd!"):
        # Register
        r = client.post("/auth/register", json={"email": email, "password": password})
        # If already exists, ignore; else ensure OK
        if r.status_code not in (200, 400):
            raise AssertionError(f"Unexpected status from register: {r.status_code} {r.text}")
        # Login
        lr = client.post("/auth/login", json={"email": email, "password": password})
        assert lr.status_code == 200, lr.text
        token = lr.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}
    return _auth_headers


@pytest.fixture()
def seed_sessions(SessionTesting, create_user):
    """
    Seed multiple users and sessions to power leaderboard and listing tests.
    Returns dict with users and their sessions.
    """
    def _seed():
        today = date.today()
        u1 = create_user("u1@example.com")
        u2 = create_user("u2@example.com")
        u3 = create_user("u3@example.com")

        with SessionTesting() as db:
            # u1: 30 + 45 (all-time), and one recent within 30 days
            s1 = StudySession(user_id=u1.id, topic="Math", minutes=30, session_date=today - timedelta(days=40))
            s2 = StudySession(user_id=u1.id, topic="Science", minutes=45, session_date=today - timedelta(days=5))
            # u2: 60 (recent), 15 (recent)
            s3 = StudySession(user_id=u2.id, topic="Math", minutes=60, session_date=today - timedelta(days=10))
            s4 = StudySession(user_id=u2.id, topic="History", minutes=15, session_date=today - timedelta(days=2))
            # u3: 10 (old, beyond 30 days)
            s5 = StudySession(user_id=u3.id, topic="Art", minutes=10, session_date=today - timedelta(days=45))

            db.add_all([s1, s2, s3, s4, s5])
            db.commit()
            return {"u1": u1, "u2": u2, "u3": u3}
    return _seed
