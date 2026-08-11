# Sourcely · backend

Servicio FastAPI que se ocupa de la autenticación, la ingesta de documentos, la generación aumentada por recuperación y el *endpoint* de consulta en *streaming*.

## Stack

- **FastAPI** + **Uvicorn** (*async*)
- **SQLAlchemy 2** *async* + **asyncpg**
- Migraciones con **Alembic**
- **pgvector** (Postgres en Supabase) para búsqueda por similitud
- **Gemini** `text-embedding-001` (768 dim) para *embeddings*
- **Groq** `llama-3.3-70b-versatile` para la generación de respuestas
- **faster-whisper** para transcripción de audio (`whisper.cpp* por debajo)
- **Supabase Storage** para los PDF y ficheros de audio originales
- **JWT** (HS256) en una cookie `HttpOnly`, `SameSite=Lax`

## Setup

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS / Linux:
# source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
# Rellenar DATABASE_URL, JWT_SECRET, GEMINI_API_KEY, GROQ_API_KEY y SUPABASE_*.

alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

Swagger UI: `http://127.0.0.1:8000/docs`.

## Layout

```
app/
  api/         Routers de FastAPI (auth, documents, query)
  core/        Config, seguridad, deps
  db/          Engine, sesión, Base
  models/      Modelos de SQLAlchemy (User, Document, Chunk)
  schemas/     DTOs de Pydantic
  services/    Ingesta, embeddings, retrieval, llm, transcripción, storage
  tasks/       Jobs de indexado en segundo plano
alembic/       Migraciones
tests/         Suites de pytest unitarias y de integración
```

## Tests

```bash
pytest                                # tests unitarios, sin servicios externos
RUN_INTEGRATION=1 pytest tests/integration/   # ataca a Gemini + Groq + Supabase reales
```

73 tests unitarios cubren autenticación, subida de documentos, troceado, indexado, transcripción de audio, *query*, *streaming* y conversaciones.

## Convenciones

- *Async* por todas partes. SQLAlchemy 2 *async*, *driver* `asyncpg`, `httpx` para HTTP saliente y los clientes *async* de los SDK de Groq y Gemini.
- Un modelo ORM por archivo bajo `app/models/`, reexportados en `__init__.py` para que Alembic los vea en autogenerate.
- Lógica de negocio en `app/services/`, **nunca** en el router.
- Los trabajos en segundo plano usan `BackgroundTasks` de FastAPI con un motor *sync* dedicado (`psycopg`) para evitar colisiones con el *event loop*.
- Los *prompts* RAG fijan al LLM al contexto entregado y prohíben inventar. Las fuentes se citan como `[1] [2]` numerando.
