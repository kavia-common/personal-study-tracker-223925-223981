# Personal Study Tracker

This repository contains the Backend API (FastAPI) for the Personal Study Tracker MVP.

## Features
- User registration and login with JWT authentication
- Create, list, update, and delete study sessions (topic, minutes, date)
- Leaderboard for top users by total study minutes (all-time and last 30 days)
- OpenAPI docs at /docs

## Setup

1) Create a `.env` from `.env.example` and fill values (do not commit secrets):
```
cp .env.example .env
```

Required keys:
- BACKEND_DB_URL (e.g., postgresql+psycopg2://user:password@host:5432/dbname)
- BACKEND_JWT_SECRET
- BACKEND_JWT_EXPIRE_MINUTES (optional, default 120)
- REACT_APP_FRONTEND_URL (for CORS, default http://localhost:3000)

2) Install dependencies:
```
pip install -r BackendAPI/requirements.txt
```

3) Run the API:
```
uvicorn src.api.main:app --host 0.0.0.0 --port 3001 --reload
```

If `BACKEND_DB_URL` is not set, a local SQLite `dev.db` will be used for quick start only (non-production).

## API Summary

- GET `/` Health
- POST `/auth/register` { email, password } -> User
- POST `/auth/login` { email, password } -> { access_token, token_type }
- GET `/me` -> User (Authorization: Bearer)
- POST `/sessions` { topic, minutes, session_date } -> Session (Bearer)
- GET `/sessions?page=1&size=20&topic=&start_date=&end_date=` -> SessionsListResponse (Bearer)
- PUT `/sessions/{id}` -> Session (Bearer)
- DELETE `/sessions/{id}` -> 204 (Bearer)
- GET `/leaderboard?top=10` -> { all_time: [], last_30_days: [] }

Use the `Authorization: Bearer <token>` header for authenticated routes.

## Environment variables for Frontend
The frontend should use one of these to configure API base:
- `REACT_APP_API_BASE`
- `REACT_APP_BACKEND_URL`

Example: `REACT_APP_API_BASE=http://localhost:3001`

## Notes
- No secrets are hardcoded.
- Input validation and error handling implemented with Pydantic and HTTPException.
- For production, configure a managed PostgreSQL and set `BACKEND_DB_URL` appropriately.
