from __future__ import annotations

from typing import Protocol


class StorageBackend(Protocol):
    def upload(self, path: str, data: bytes, mime: str) -> None: ...
    def download(self, path: str) -> bytes: ...
    def delete(self, path: str) -> None: ...
    def signed_url(self, path: str, expires_in: int = 3600) -> str | None: ...


class InMemoryStorage:
    """In-memory storage used for tests."""

    def __init__(self) -> None:
        self._files: dict[str, bytes] = {}

    def upload(self, path: str, data: bytes, mime: str) -> None:
        self._files[path] = data

    def download(self, path: str) -> bytes:
        return self._files[path]

    def delete(self, path: str) -> None:
        self._files.pop(path, None)

    def signed_url(self, path: str, expires_in: int = 3600) -> str | None:
        if path in self._files:
            return f"https://fake.test/signed/{path}?expires={expires_in}"
        return None


class SupabaseStorage:
    """Thin wrapper over the Supabase Storage sync client."""

    def __init__(self, client, bucket: str) -> None:
        self._bucket = client.storage.from_(bucket)

    def upload(self, path: str, data: bytes, mime: str) -> None:
        self._bucket.upload(
            path=path,
            file=data,
            file_options={"content-type": mime, "upsert": "true"},
        )

    def download(self, path: str) -> bytes:
        return self._bucket.download(path)

    def delete(self, path: str) -> None:
        self._bucket.remove([path])

    def signed_url(self, path: str, expires_in: int = 3600) -> str | None:
        try:
            res = self._bucket.create_signed_url(path, expires_in)
        except Exception:  # noqa: BLE001
            return None
        if isinstance(res, dict):
            return res.get("signedURL") or res.get("signed_url")
        return getattr(res, "signed_url", None) or getattr(res, "signedURL", None)


_storage: StorageBackend | None = None


def set_storage(backend: StorageBackend) -> None:
    global _storage
    _storage = backend


def get_storage() -> StorageBackend:
    if _storage is not None:
        return _storage
    from supabase import create_client

    from app.core.config import get_settings

    settings = get_settings()
    if not settings.supabase_service_role_key or settings.supabase_service_role_key.endswith(
        "REPLACE_ME"
    ):
        raise RuntimeError(
            "SUPABASE_SERVICE_ROLE_KEY is not configured. "
            "Get it from Supabase Dashboard → Project Settings → API → service_role (secret)."
        )
    if not settings.supabase_url:
        raise RuntimeError("SUPABASE_URL is not configured.")
    client = create_client(settings.supabase_url, settings.supabase_service_role_key)
    backend = SupabaseStorage(client, settings.supabase_bucket)
    set_storage(backend)
    return backend
