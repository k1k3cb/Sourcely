# backend

FastAPI backend for the RAG document assistant.

## Stack
- FastAPI + Uvicorn
- SQLAlchemy 2 (async) + asyncpg
- Alembic migrations
- pgvector (Supabase)
- OpenAI embeddings (`text-embedding-3-small`, dim 768)
- Groq LLM (`llama-3.1-70b-versatile`)
- Supabase Storage
- JWT auth (httpOnly cookie)

## Setup
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# fill in the values
alembic upgrade head
uvicorn app.main:app --reload
```

## Layout
```
app/
  api/        # FastAPI routers (auth, documents, query)
  core/       # config, security
  db/         # engine, session, Base
  models/     # SQLAlchemy models
  schemas/    # Pydantic schemas
  services/   # business logic (ingestion, embeddings, retrieval)
  tasks/      # background tasks
alembic/      # migrations
tests/
```
