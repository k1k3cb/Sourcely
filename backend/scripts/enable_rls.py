"""Enable Row-Level Security on all Sourcely tables.

Idempotent; safe to run multiple times.
"""
import os
import pathlib
import sys

import psycopg


# Load .env from the backend directory so this script works without
# needing to export every variable.
ENV_PATH = pathlib.Path(__file__).resolve().parents[1] / ".env"
if ENV_PATH.exists():
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _url() -> str:
    url = os.environ.get("SUPABASE_POOLER_URL")
    if url:
        return url
    db = os.environ.get("DATABASE_URL", "")
    if db:
        # Convert asyncpg driver to plain postgresql for the sync connector.
        return db.replace("postgresql+asyncpg://", "postgresql://", 1)
    print("ERROR: Set SUPABASE_POOLER_URL or DATABASE_URL in backend/.env", file=sys.stderr)
    sys.exit(1)


TABLES = ["users", "documents", "chunks", "conversations", "messages"]


def enable_rls_and_policies() -> None:
    url = _url()
    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            for table in TABLES:
                cur.execute(
                    f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY;"
                )
                print(f"  enabled RLS on {table}")

            for table in TABLES:
                cur.execute(
                    "SELECT policyname FROM pg_policies "
                    "WHERE schemaname='public' AND tablename=%s",
                    (table,),
                )
                for (pname,) in cur.fetchall():
                    cur.execute(
                        f"DROP POLICY IF EXISTS {pname} ON public.{table};"
                    )

            cur.execute(
                """
                CREATE POLICY users_self ON public.users
                FOR ALL TO authenticated
                USING (id = (SELECT auth.uid()))
                WITH CHECK (id = (SELECT auth.uid()));
                """
            )
            cur.execute(
                """
                CREATE POLICY documents_owner ON public.documents
                FOR ALL TO authenticated
                USING (user_id = (SELECT auth.uid()))
                WITH CHECK (user_id = (SELECT auth.uid()));
                """
            )
            cur.execute(
                """
                CREATE POLICY chunks_owner ON public.chunks
                FOR ALL TO authenticated
                USING (
                    EXISTS (
                        SELECT 1 FROM public.documents d
                        WHERE d.id = chunks.document_id
                          AND d.user_id = (SELECT auth.uid())
                    )
                )
                WITH CHECK (
                    EXISTS (
                        SELECT 1 FROM public.documents d
                        WHERE d.id = chunks.document_id
                          AND d.user_id = (SELECT auth.uid())
                    )
                );
                """
            )
            cur.execute(
                """
                CREATE POLICY conversations_owner ON public.conversations
                FOR ALL TO authenticated
                USING (user_id = (SELECT auth.uid()))
                WITH CHECK (user_id = (SELECT auth.uid()));
                """
            )
            cur.execute(
                """
                CREATE POLICY messages_owner ON public.messages
                FOR ALL TO authenticated
                USING (
                    EXISTS (
                        SELECT 1 FROM public.conversations c
                        WHERE c.id = messages.conversation_id
                          AND c.user_id = (SELECT auth.uid())
                    )
                )
                WITH CHECK (
                    EXISTS (
                        SELECT 1 FROM public.conversations c
                        WHERE c.id = messages.conversation_id
                          AND c.user_id = (SELECT auth.uid())
                    )
                );
                """
            )
            print("  policies created")
            conn.commit()


if __name__ == "__main__":
    enable_rls_and_policies()
    print("RLS enabled and policies applied.")
