import os
from datetime import datetime, timedelta, date
from typing import List, Optional

from fastapi import FastAPI, Depends, HTTPException, status, Query, Path
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Response
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, EmailStr, Field, PositiveInt, constr
from sqlalchemy import create_engine, String, Integer, Date, func, ForeignKey, select, desc, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker, Session
from passlib.context import CryptContext
import jwt
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration via environment variables
APP_TITLE = "Personal Study Tracker API"
APP_DESC = "Backend API providing authentication, study session management, and leaderboard for the Personal Study Tracker."
APP_VERSION = "0.1.0"

# Database config (no secrets hardcoded)
# Priority: DATABASE_URL -> BACKEND_DB_URL (legacy) -> SQLite dev fallback
DB_URL = os.getenv("DATABASE_URL") or os.getenv("BACKEND_DB_URL")
if not DB_URL:
    # Provide a safe default message if missing; do not hardcode secrets
    # For local dev, users should define DATABASE_URL like: postgresql+psycopg2://user:password@host:port/dbname
    # When running in the multi-container environment, map Database container env to this variable.
    DB_URL = "sqlite:///./dev.db"  # Non-production fallback for quick start if Postgres not configured

# Security/JWT config
JWT_SECRET = os.getenv("BACKEND_JWT_SECRET", "dev-insecure-secret-change")  # for demo only; document env in .env.example
JWT_ALG = os.getenv("BACKEND_JWT_ALG", "HS256")
JWT_EXPIRE_MINUTES = int(os.getenv("BACKEND_JWT_EXPIRE_MINUTES", "120"))

# CORS configuration - use REACT_APP_FRONTEND_URL if provided
# We also include common localhost variants to reduce dev friction.
frontend_origin = os.getenv("REACT_APP_FRONTEND_URL", "http://localhost:3000")
allow_origins = list({
    frontend_origin,
    "http://localhost:3000",
    "http://127.0.0.1:3000",
})
# Common CORS allowances for modern SPAs
allow_methods = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
allow_headers = ["Authorization", "Content-Type", "X-Requested-With", "Accept", "Origin"]
expose_headers = ["Content-Length", "Content-Type"]
allow_credentials = False  # keep false unless cookie-based flows are required

# SQLAlchemy setup
engine = create_engine(DB_URL, echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    """Base for SQLAlchemy models."""


# SQLAlchemy Models
class User(Base):
    """User model storing email and password hash."""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    sessions: Mapped[List["StudySession"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class StudySession(Base):
    """Study Session model recording topic, minutes, and date for a user."""
    __tablename__ = "study_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    topic: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    session_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    user: Mapped[User] = relationship(back_populates="sessions")


# Create tables if not present (minimal migration)
def init_db() -> None:
    """Initialize database tables if not present."""
    Base.metadata.create_all(bind=engine)


# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# OAuth2 scheme (we use bearer tokens)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

# FastAPI app
app = FastAPI(
    title=APP_TITLE,
    description=APP_DESC,
    version=APP_VERSION,
    openapi_tags=[
        {"name": "Health", "description": "Health and operational endpoints."},
        {"name": "Auth", "description": "Authentication endpoints for registration and login."},
        {"name": "Sessions", "description": "Manage study sessions."},
        {"name": "Leaderboard", "description": "Leaderboard and aggregates."},
    ],
)

# CORS
# Configure explicit CORS for the WebFrontend (default http://localhost:3000).
# We intentionally keep allow_credentials=False unless a cookie-based auth flow requires it.
app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins or ["http://localhost:3000"],
    allow_credentials=allow_credentials,
    allow_methods=allow_methods,
    allow_headers=allow_headers,
    expose_headers=expose_headers,
)


# Dependency to get DB session
def get_db():
    """Yield a SQLAlchemy session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Utility functions
def hash_password(password: str) -> str:
    """Hash a plaintext password."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a stored hash."""
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(user_id: int, email: str) -> str:
    """Create a JWT access token for a user."""
    expire = datetime.utcnow() + timedelta(minutes=JWT_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "email": email, "exp": expire}
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)
    return token


def decode_token(token: str) -> dict:
    """Decode and validate JWT token."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


# Schemas
class TokenResponse(BaseModel):
    access_token: str = Field(..., description="JWT access token to be used as Bearer token.")
    token_type: str = Field("bearer", description="Token type. Always 'bearer'.")


class UserOut(BaseModel):
    id: int
    email: EmailStr

    class Config:
        from_attributes = True


class RegisterRequest(BaseModel):
    email: EmailStr = Field(..., description="User email address.")
    password: constr(min_length=8, max_length=128) = Field(..., description="Strong password, min 8 chars.")


class LoginRequest(BaseModel):
    email: EmailStr
    password: constr(min_length=8, max_length=128)


class StudySessionCreate(BaseModel):
    topic: constr(min_length=1, max_length=255) = Field(..., description="Topic studied.")
    minutes: PositiveInt = Field(..., description="Duration in minutes (positive integer).")
    session_date: date = Field(..., description="Date of the study session (YYYY-MM-DD).")


class StudySessionOut(BaseModel):
    id: int
    topic: str
    minutes: int
    session_date: date
    created_at: datetime

    class Config:
        from_attributes = True


class SessionsListResponse(BaseModel):
    items: List[StudySessionOut]
    total: int
    page: int
    size: int
    total_minutes: int


class LeaderboardEntry(BaseModel):
    user_id: int
    email: EmailStr
    total_minutes: int


class LeaderboardResponse(BaseModel):
    all_time: List[LeaderboardEntry]
    last_30_days: List[LeaderboardEntry]


# Auth helpers
def get_current_user(db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)) -> User:
    """Resolve current user from Bearer token."""
    payload = decode_token(token)
    user_id = int(payload.get("sub", "0"))
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


# Routes

# Explicit OPTIONS handler for preflight (defensive; Starlette CORSMiddleware usually handles this)
# PUBLIC_INTERFACE
@app.options("/{path:path}", tags=["Health"], summary="Preflight handler", include_in_schema=False)
def preflight_handler(path: str) -> Response:
    """
    Handle browser CORS preflight requests explicitly. This route simply returns 200 OK.
    CORSMiddleware will attach the appropriate CORS headers based on configuration.
    """
    return Response(status_code=200)

# PUBLIC_INTERFACE
@app.get(
    "/",
    tags=["Health"],
    summary="Health Check",
    description="Health check endpoint that validates application liveness and database connectivity."
)
def health_check(db: Session = Depends(get_db)):
    """
    Health check endpoint to verify service is running and database is reachable.

    Parameters:
        None

    Returns:
        JSON object:
            - message: str - 'Healthy' when app is up.
            - db: str - 'ok' if database connectivity and simple query succeed, otherwise raises 503.
    """
    try:
        # Simple DB connectivity check; uses current session.
        db.execute(text("SELECT 1"))
        return {"message": "Healthy", "db": "ok"}
    except Exception as exc:
        # Do not leak details; surface generic error
        raise HTTPException(status_code=503, detail="Database not reachable") from exc


# PUBLIC_INTERFACE
@app.post("/auth/register", response_model=UserOut, tags=["Auth"], summary="Register a new user")
def register_user(payload: RegisterRequest, db: Session = Depends(get_db)) -> UserOut:
    """
    Register a new user with email and password.

    Parameters:
        payload: RegisterRequest - email and password.
    Returns:
        UserOut - created user info.
    """
    existing = db.execute(select(User).where(User.email == payload.email.lower())).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(email=payload.email.lower(), password_hash=hash_password(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)


# PUBLIC_INTERFACE
@app.post("/auth/login", response_model=TokenResponse, tags=["Auth"], summary="Login and retrieve JWT token")
def login_user(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """
    Login with email and password to receive a JWT token.

    Parameters:
        payload: LoginRequest - email and password.
    Returns:
        TokenResponse - bearer token to authenticate further requests.
    """
    user = db.execute(select(User).where(User.email == payload.email.lower())).scalar_one_or_none()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_access_token(user_id=user.id, email=user.email)
    return TokenResponse(access_token=token, token_type="bearer")


# PUBLIC_INTERFACE
@app.get("/me", response_model=UserOut, tags=["Auth"], summary="Get current user")
def me(current_user: User = Depends(get_current_user)) -> UserOut:
    """
    Return the current authenticated user's profile.

    Returns:
        UserOut - user id and email
    """
    return UserOut.model_validate(current_user)


# PUBLIC_INTERFACE
@app.post("/sessions", response_model=StudySessionOut, tags=["Sessions"], summary="Create a study session")
def create_session(payload: StudySessionCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> StudySessionOut:
    """
    Create a new study session for the current user.

    Parameters:
        payload: StudySessionCreate - topic, minutes, session_date
    Returns:
        StudySessionOut - created session
    """
    sess = StudySession(
        user_id=current_user.id,
        topic=payload.topic.strip(),
        minutes=payload.minutes,
        session_date=payload.session_date,
    )
    db.add(sess)
    db.commit()
    db.refresh(sess)
    return StudySessionOut.model_validate(sess)


# PUBLIC_INTERFACE
@app.get("/sessions", response_model=SessionsListResponse, tags=["Sessions"], summary="List my study sessions")
def list_sessions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    page: int = Query(1, ge=1, description="Page number, starting from 1"),
    size: int = Query(20, ge=1, le=100, description="Page size between 1 and 100"),
    topic: Optional[str] = Query(None, description="Optional topic filter (contains)"),
    start_date: Optional[date] = Query(None, description="Filter from this date (inclusive)"),
    end_date: Optional[date] = Query(None, description="Filter until this date (inclusive)"),
) -> SessionsListResponse:
    """
    List study sessions for the current user with pagination and filters.

    Returns:
        SessionsListResponse - items, total, pagination meta, and total_minutes
    """
    query = select(StudySession).where(StudySession.user_id == current_user.id)
    count_query = select(func.count()).where(StudySession.user_id == current_user.id)
    sum_query = select(func.coalesce(func.sum(StudySession.minutes), 0)).where(StudySession.user_id == current_user.id)

    if topic:
        like = f"%{topic.strip()}%"
        query = query.where(StudySession.topic.ilike(like))
        count_query = count_query.where(StudySession.topic.ilike(like))
        sum_query = sum_query.where(StudySession.topic.ilike(like))
    if start_date:
        query = query.where(StudySession.session_date >= start_date)
        count_query = count_query.where(StudySession.session_date >= start_date)
        sum_query = sum_query.where(StudySession.session_date >= start_date)
    if end_date:
        query = query.where(StudySession.session_date <= end_date)
        count_query = count_query.where(StudySession.session_date <= end_date)
        sum_query = sum_query.where(StudySession.session_date <= end_date)

    total = db.execute(count_query).scalar_one()
    total_minutes = int(db.execute(sum_query).scalar_one() or 0)

    query = query.order_by(desc(StudySession.session_date), desc(StudySession.created_at)).offset((page - 1) * size).limit(size)
    rows = db.execute(query).scalars().all()
    items = [StudySessionOut.model_validate(r) for r in rows]
    return SessionsListResponse(items=items, total=total, page=page, size=size, total_minutes=total_minutes)


# PUBLIC_INTERFACE
@app.delete("/sessions/{session_id}", status_code=204, tags=["Sessions"], summary="Delete a study session")
def delete_session(
    session_id: int = Path(..., ge=1, description="ID of the study session"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """
    Delete a user's study session by ID.

    Returns:
        204 No Content on success
    """
    sess = db.get(StudySession, session_id)
    if not sess or sess.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Session not found")
    db.delete(sess)
    db.commit()
    return None


# PUBLIC_INTERFACE
@app.put("/sessions/{session_id}", response_model=StudySessionOut, tags=["Sessions"], summary="Update a study session")
def update_session(
    payload: StudySessionCreate,
    session_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StudySessionOut:
    """
    Update topic, minutes, and date for an existing study session.

    Returns:
        StudySessionOut - updated session
    """
    sess = db.get(StudySession, session_id)
    if not sess or sess.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Session not found")
    sess.topic = payload.topic.strip()
    sess.minutes = payload.minutes
    sess.session_date = payload.session_date
    db.add(sess)
    db.commit()
    db.refresh(sess)
    return StudySessionOut.model_validate(sess)


# PUBLIC_INTERFACE
@app.get("/leaderboard", response_model=LeaderboardResponse, tags=["Leaderboard"], summary="Leaderboard by total minutes")
def leaderboard(
    db: Session = Depends(get_db),
    top: int = Query(10, ge=1, le=100, description="Number of top users to return"),
) -> LeaderboardResponse:
    """
    Return the leaderboard:
    - all_time: top users by total minutes across all sessions
    - last_30_days: top users by total minutes in the last 30 days
    """
    # All time
    # Use INNER JOIN so only users who have at least one study session are included.
    # This ensures an empty database yields an empty leaderboard, matching test expectations.
    all_time_q = (
        select(User.id, User.email, func.coalesce(func.sum(StudySession.minutes), 0).label("total_minutes"))
        .join(StudySession, StudySession.user_id == User.id)  # inner join
        .group_by(User.id)
        .order_by(desc(text("total_minutes")))
        .limit(top)
    )
    all_time_rows = db.execute(all_time_q).all()
    all_time = [
        LeaderboardEntry(user_id=uid, email=email, total_minutes=int(total_minutes or 0))
        for uid, email, total_minutes in all_time_rows
    ]

    # Last 30 days
    since = date.today() - timedelta(days=30)
    last_30_q = (
        select(User.id, User.email, func.coalesce(func.sum(StudySession.minutes), 0).label("total_minutes"))
        .join(StudySession, StudySession.user_id == User.id)
        .where(StudySession.session_date >= since)
        .group_by(User.id)
        .order_by(desc(text("total_minutes")))
        .limit(top)
    )
    last_30_rows = db.execute(last_30_q).all()
    last_30_days = [
        LeaderboardEntry(user_id=uid, email=email, total_minutes=int(total_minutes or 0))
        for uid, email, total_minutes in last_30_rows
    ]

    return LeaderboardResponse(all_time=all_time, last_30_days=last_30_days)


# Initialize DB on import and also at startup to be safe in hot-reload scenarios
init_db()

@app.on_event("startup")
def on_startup() -> None:
    """
    Ensure database tables exist on application startup.
    This is a safety net for environments without migrations enabled.
    Also logs configured CORS settings for troubleshooting.
    """
    init_db()
    # Log CORS configuration (non-sensitive)
    try:
        print(
            "[Startup] CORS configured:",
            {
                "allow_origins": allow_origins,
                "allow_methods": allow_methods,
                "allow_headers": allow_headers,
                "expose_headers": expose_headers,
                "allow_credentials": allow_credentials,
            },
            flush=True,
        )
    except Exception:
        # Avoid failing startup due to logging issues
        pass
