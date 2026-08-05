from __future__ import annotations

import io

import pytest
from httpx import AsyncClient

# Minimal valid PDF (just enough magic + EOF)
PDF_BYTES = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<<>>\nendobj\nxref\n0 1\n0000000000 65535 f\ntrailer\n<<>>\nstartxref\n0\n%%EOF\n"
NOT_PDF_BYTES = b"this is not a pdf at all"


async def _register_and_login(client: AsyncClient, email: str) -> None:
    r = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "supersecret"},
    )
    assert r.status_code == 201
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "supersecret"},
    )
    assert r.status_code == 200


def _png_bytes() -> bytes:
    # PNG magic bytes
    return b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


@pytest.mark.asyncio
async def test_upload_pdf_success(client: AsyncClient):
    await _register_and_login(client, "alice@example.com")
    r = await client.post(
        "/api/v1/documents/upload",
        files={"file": ("doc.pdf", PDF_BYTES, "application/pdf")},
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["filename"] == "doc.pdf"
    assert data["size_bytes"] == len(PDF_BYTES)
    assert data["status"] in ("uploaded", "processing", "ready")


@pytest.mark.asyncio
async def test_upload_rejects_wrong_content_type(client: AsyncClient):
    await _register_and_login(client, "bob@example.com")
    r = await client.post(
        "/api/v1/documents/upload",
        files={"file": ("doc.pdf", PDF_BYTES, "text/plain")},
    )
    assert r.status_code == 415


@pytest.mark.asyncio
async def test_upload_rejects_non_pdf_bytes(client: AsyncClient):
    await _register_and_login(client, "carol@example.com")
    r = await client.post(
        "/api/v1/documents/upload",
        files={"file": ("doc.pdf", NOT_PDF_BYTES, "application/pdf")},
    )
    assert r.status_code == 415


@pytest.mark.asyncio
async def test_upload_rejects_png_with_pdf_mime(client: AsyncClient):
    await _register_and_login(client, "dave@example.com")
    r = await client.post(
        "/api/v1/documents/upload",
        files={"file": ("image.png", _png_bytes(), "application/pdf")},
    )
    assert r.status_code == 415


@pytest.mark.asyncio
async def test_upload_rejects_too_large(client: AsyncClient):
    await _register_and_login(client, "eve@example.com")
    big = b"%PDF-" + b"a" * (21 * 1024 * 1024)  # 21 MB
    r = await client.post(
        "/api/v1/documents/upload",
        files={"file": ("big.pdf", big, "application/pdf")},
    )
    assert r.status_code == 413


@pytest.mark.asyncio
async def test_upload_requires_auth(client: AsyncClient):
    r = await client.post(
        "/api/v1/documents/upload",
        files={"file": ("doc.pdf", PDF_BYTES, "application/pdf")},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_list_documents_scoped_to_user(client: AsyncClient):
    # Two users, each uploads, neither sees the other's docs
    await _register_and_login(client, "frank@example.com")
    r1 = await client.post(
        "/api/v1/documents/upload",
        files={"file": ("a.pdf", PDF_BYTES, "application/pdf")},
    )
    assert r1.status_code == 201

    await client.post("/api/v1/auth/logout")

    await _register_and_login(client, "gina@example.com")
    r2 = await client.post(
        "/api/v1/documents/upload",
        files={"file": ("b.pdf", PDF_BYTES, "application/pdf")},
    )
    assert r2.status_code == 201

    mine = await client.get("/api/v1/documents")
    assert mine.status_code == 200
    items = mine.json()
    assert len(items) == 1
    assert items[0]["filename"] == "b.pdf"


@pytest.mark.asyncio
async def test_get_document_other_user_returns_404(client: AsyncClient):
    await _register_and_login(client, "harry@example.com")
    r = await client.post(
        "/api/v1/documents/upload",
        files={"file": ("private.pdf", PDF_BYTES, "application/pdf")},
    )
    assert r.status_code == 201
    doc_id = r.json()["id"]

    await client.post("/api/v1/auth/logout")
    await _register_and_login(client, "ivy@example.com")
    r2 = await client.get(f"/api/v1/documents/{doc_id}")
    assert r2.status_code == 404


@pytest.mark.asyncio
async def test_get_document_returns_signed_url(client: AsyncClient):
    await _register_and_login(client, "jane@example.com")
    r = await client.post(
        "/api/v1/documents/upload",
        files={"file": ("x.pdf", PDF_BYTES, "application/pdf")},
    )
    assert r.status_code == 201
    doc_id = r.json()["id"]
    r2 = await client.get(f"/api/v1/documents/{doc_id}")
    assert r2.status_code == 200
    body = r2.json()
    assert body["signed_url"] is not None
    assert body["signed_url"].startswith("https://fake.test/")


@pytest.mark.asyncio
async def test_delete_document(client: AsyncClient):
    await _register_and_login(client, "kate@example.com")
    r = await client.post(
        "/api/v1/documents/upload",
        files={"file": ("del.pdf", PDF_BYTES, "application/pdf")},
    )
    assert r.status_code == 201
    doc_id = r.json()["id"]
    r2 = await client.delete(f"/api/v1/documents/{doc_id}")
    assert r2.status_code == 204
    r3 = await client.get(f"/api/v1/documents/{doc_id}")
    assert r3.status_code == 404


@pytest.mark.asyncio
async def test_delete_other_users_document_returns_404(client: AsyncClient):
    await _register_and_login(client, "liam@example.com")
    r = await client.post(
        "/api/v1/documents/upload",
        files={"file": ("mine.pdf", PDF_BYTES, "application/pdf")},
    )
    assert r.status_code == 201
    doc_id = r.json()["id"]

    await client.post("/api/v1/auth/logout")
    await _register_and_login(client, "mia@example.com")
    r2 = await client.delete(f"/api/v1/documents/{doc_id}")
    assert r2.status_code == 404


@pytest.mark.asyncio
async def test_list_documents_requires_auth(client: AsyncClient):
    r = await client.get("/api/v1/documents")
    assert r.status_code == 401
