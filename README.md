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
   uvicorn app.main:app --reload
   ```
5. Frontend:
   ```bash
   cd frontend
   pnpm install
   pnpm dev
   ```

## License
MIT
