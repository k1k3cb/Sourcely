# Sourcely

RAG document assistant: upload PDFs, ask questions, get cited answers from your own documents.

## Stack
- **Frontend**: Next.js 16 (App Router) + TypeScript + Tailwind
- **Backend**: FastAPI + SQLAlchemy 2 (async) + pgvector
- **DB / Storage**: Supabase (Postgres + pgvector + Storage)
- **Embeddings**: OpenAI `text-embedding-3-small` (dim 768)
- **LLM**: Groq Llama 3.1 70B
- **Deploy**: Vercel (frontend) + Render (backend) — both free tier

## Layout
- `backend/` — FastAPI service. See `backend/README.md` and `backend/AGENTS.md`.
- `frontend/` — Next.js app.

## Local development
1. Create a Supabase project and enable the `vector` extension in the SQL editor.
2. Create a private Storage bucket named `documents`.
3. Copy `backend/.env.example` to `backend/.env` and fill in the values.
4. Backend:
   ```bash
   cd backend
   pip install -r requirements.txt
   alembic upgrade head
   uvicorn app.main:app --reload --port 8000
   ```
   Swagger: <http://127.0.0.1:8000/docs>
5. Frontend:
   ```bash
   cd frontend
   cp .env.local.example .env.local
   pnpm install
   pnpm dev
   ```
   App: <http://127.0.0.1:3000>

If port 8000 is held by a zombie socket on Windows, the backend can
be started on any other port (e.g. `--port 8005`) and the frontend
`NEXT_PUBLIC_API_URL` updated to match.

## License
MIT
