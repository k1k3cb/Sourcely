# AGENTS.md — Backend

## Commands
- Install: `pip install -r requirements.txt`
- Run dev: `uvicorn app.main:app --reload`
- Create migration: `alembic revision --autogenerate -m "msg"`
- Apply migrations: `alembic upgrade head`
- Health check: `GET /health`
- Run unit tests: `pytest -q`
- Run integration (smoke) tests: `RUN_INTEGRATION=1 SUPABASE_POOLER_URL=... pytest tests/integration/`

## Conventions
- Async-first (SQLAlchemy 2 async, asyncpg, httpx, openai async client).
- `Settings` is loaded via `get_settings()` (cached). Never read env vars directly.
- SQLAlchemy models live in `app/models/`, one file per model, re-exported in `__init__.py` so Alembic autogenerate sees them.
- Pydantic schemas in `app/schemas/`, separate from ORM models.
- API routers in `app/api/`, mounted under `/api/v1/...` in `main.py`.
- Business logic in `app/services/`, not in routers.
- Background tasks (FastAPI `BackgroundTasks`) live in `app/tasks/`. They use a dedicated **sync** engine (psycopg) because mixing event loops with BackgroundTasks is fragile.

## Embeddings
- Provider is `gemini-embedding-001` (768-dim, free tier 1500 req/day).
- Set `EMBEDDINGS_PROVIDER=gemini` and `GEMINI_API_KEY` in `.env`.
- Alternative providers: `openai` (text-embedding-3-small@768) and `ollama` (nomic-embed-text, etc.).
- `task_type=RETRIEVAL_DOCUMENT` is used at index time; queries will use `RETRIEVAL_QUERY` in Etapa 4.

## LLM
- Provider: Groq (`llama-3.3-70b-versatile`). Set `GROQ_API_KEY` in `.env`.
- The service is a thin async wrapper over the Groq HTTP API
  (httpx streaming) because the official `groq` SDK is sync-only.
- The system prompt instructs the model to cite sources as
  `[doc:<filename> page=<n>]` and to refuse answers that aren't in the
  retrieved context.

## Streaming
- `POST /api/v1/query/stream` returns `text/event-stream` with three
  event types: `token` (delta text), `sources` (list of retrieved
  chunks), and `done`. Errors come as `event: error`.
- Frontend consumes the stream with `fetch` + `ReadableStream`. See
  `frontend/lib/api.ts` for the `streamQuery` async generator.

## Conversations
- `Conversation` and `Message` models. Messages have `role`, `content`,
  and `sources_json` (serialized as JSON; the in-stream payload
  uses `Source` typed refs).
- `POST /api/v1/conversations/{id}/messages` persists the user turn
  up front, streams the LLM response, and persists the assistant
  turn at the end. The conversation `title` auto-updates from the
  first user message.
- All conversation routes scope by `user_id`; cross-user access
  returns 404.

## pgvector
- All vector columns are `vector(768)` (locked in).
- HNSW index with `vector_cosine_ops` for similarity search.
- Similarity = `1 - (embedding <=> query)`.
- Every chunk stores `embedding_model` so we can migrate models later.

## Retrieval
- Endpoint `POST /api/v1/query` calls `app.services.retrieval.retrieve()`.
- The query ALWAYS joins `chunks` to `documents` and filters by
  `documents.user_id = :user_id`. There is no code path that queries
  chunks without this filter.
- The query vector is passed as a string formatted for pgvector:
  `'[v1,v2,...]'`. SQLAlchemy doesn't auto-bind `list<float>` to the
  vector type, so we format it ourselves.
- The query embedding uses `task_type=RETRIEVAL_QUERY` (Gemini) for
  better recall; the index used `RETRIEVAL_DOCUMENT`.

## Storage
- PDFs and audio/video files go to Supabase Storage via
  `app/services/storage.py`.
- Bucket is private; clients download via signed URLs.
- Tests use `InMemoryStorage` (set in `tests/conftest.py`).

## Auth
- JWT signed with `JWT_SECRET`, `HS256`, expires in `JWT_EXPIRES_MINUTES`.
- Cookie name: `token`, `HttpOnly`, `SameSite=Lax`, `Secure` in production.
- `get_current_user` dependency in `app/core/security.py`.

## Documents
- MIME is checked via Content-Type header AND magic bytes (PDF, MP3,
  WAV, M4A, OGG, FLAC, MP4, WebM, MOV).
- Max size: PDFs 20 MB, audio/video 200 MB.
- Status transitions: `uploaded -> processing -> ready | failed`.
- All ownership filters live in route handlers, not the model.

## Audio / Video
- `app/services/transcription.py` uses `faster-whisper` (CPU-friendly).
  Requires `ffmpeg` on PATH (faster-whisper's decoder relies on it).
- `Document.duration_seconds` is filled for audio/video documents;
  `Document.page_count` stays NULL.
- `Chunk.start_seconds` / `Chunk.end_seconds` are filled for audio/video
  chunks; `Chunk.page_start` / `Chunk.page_end` stay NULL. The
  retrieval SQL pulls both sets; the frontend picks based on which
  is non-null.
- Configurable via `WHISPER_MODEL` (default `small`), `WHISPER_DEVICE`
  (default `cpu`), `WHISPER_COMPUTE_TYPE` (default `int8`).

## Tests
- `pytest tests/` from the backend directory.
- Unit tests use httpx + ASGITransport against the FastAPI app and
  SQLite in-memory. They do not need a running server.
- 73 unit tests cover auth, documents, chunking, indexing, audio,
  query, streaming, conversations.

## Integration (smoke) tests
- `tests/integration/test_live_providers.py` exercises the real
  external services (Gemini, Groq, Supabase). Skipped by default.
- To run: set `RUN_INTEGRATION=1` and provide `SUPABASE_POOLER_URL`.
- Cost per run: ~$0.0001 in Gemini + a few free-tier Groq tokens.
- Do not run in a tight loop. Use before deploys or in CI with secrets.

## Row-Level Security (RLS)
- All five tables have RLS enabled with policies scoped by `user_id`
  (chunks/messages scope through their parent documents/conversations).
- The backend uses the `service_role` key, which bypasses RLS by
  default in Postgres. The policies document intent and protect against
  a misconfigured client connecting directly via the anon key.
- Apply the policies with `python scripts/enable_rls.py`. The script
  is idempotent and reads `DATABASE_URL` from `backend/.env`.