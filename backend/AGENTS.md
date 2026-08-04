# AGENTS.md — Backend

## Commands
- Install: `pip install -r requirements.txt`
- Run dev: `uvicorn app.main:app --reload`
- Create migration: `alembic revision --autogenerate -m "msg"`
- Apply migrations: `alembic upgrade head`
- Health check: `GET /health`

## Conventions
- Async-first (SQLAlchemy 2 async, asyncpg, httpx, openai async client).
- `Settings` is loaded via `get_settings()` (cached). Never read env vars directly.
- SQLAlchemy models live in `app/models/`, one file per model, re-exported in `__init__.py` so Alembic autogenerate sees them.
- Pydantic schemas in `app/schemas/`, separate from ORM models.
- API routers in `app/api/`, mounted under `/api/v1/...` in `main.py`.
- Business logic in `app/services/`, not in routers.
- Background tasks (FastAPI `BackgroundTasks`) live in `app/tasks/`.

## pgvector
- All vector columns are `vector(768)` (locked in).
- HNSW index with `vector_cosine_ops` for similarity search.
- Similarity = `1 - (embedding <=> query)`.
- Every chunk stores `embedding_model` so we can migrate models later.

## Auth
- JWT signed with `JWT_SECRET`, `HS256`, expires in `JWT_EXPIRES_MINUTES`.
- Cookie name: `token`, `HttpOnly`, `SameSite=Lax`, `Secure` in production.
- `get_current_user` dependency in `app/core/security.py`.

## Tests
- `pytest tests/` from the backend directory.
- Use httpx + ASGITransport against the FastAPI app, no need for a running server.
