from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from backend.app import create_app
from backend.config import Settings
from backend.kb_jobs import AI_NOT_CONFIGURED, IngestFunction, KbJobRunner
from chatbot_ai.ingest import NO_TEXT_MESSAGE
from chatbot_ai.ingest.index import collection_name, document_filter, make_qdrant
from chatbot_ai.settings import AISettings
from testkit.ai_settings import settings_for
from testkit.fake_openai import run_fake_openai
from testkit.kb_ingest import JOB_LOG, hanging_ingest, quick_ingest, scanned_ingest

TEST_DB_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://chatbot:chatbot@localhost:5432/chatbot")
LIMIT = 4096
PDF = b"%PDF-1.4 fake body for upload tests"


@dataclass
class KbHarness:
    app: FastAPI
    admin: AsyncClient
    storage: Path
    deletes: list[tuple[int, bool]] = field(default_factory=list)

    @property
    def runner(self) -> KbJobRunner:
        runner: KbJobRunner = self.app.state.kb_runner
        return runner

    async def upload(self, filename: str, body: bytes) -> dict[str, object]:
        response = await self.admin.post("/admin/kb-documents", params={"filename": filename}, content=body)
        assert response.status_code == 201, response.text
        payload: dict[str, object] = response.json()
        return payload

    async def listed(self) -> dict[str, dict[str, object]]:
        items = (await self.admin.get("/admin/kb-documents")).json()["items"]
        return {str(item["filename"]): item for item in items}

    def stored_files(self) -> list[str]:
        return sorted(p.name for p in self.storage.iterdir() if p.name != JOB_LOG) if self.storage.exists() else []


@asynccontextmanager
async def kb_harness(
    storage: Path, ai_settings: AISettings | None, ingest: IngestFunction = quick_ingest, create_admin_account: bool = True
) -> AsyncIterator[KbHarness]:
    from scripts.create_admin import create_admin

    if create_admin_account:
        create_admin(TEST_DB_URL, "admin1", "adminpass1", "Admin One", "TestCity")
    settings = Settings(database_url=TEST_DB_URL, kb_storage_dir=str(storage), kb_max_upload_bytes=LIMIT)  # type: ignore[call-arg]
    app = create_app(settings, ai_settings=ai_settings, ingest_function=ingest, ai_from_env=False)
    async with app.router.lifespan_context(app), AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as admin:
        await admin.post("/auth/login", json={"username": "admin1", "password": "adminpass1"})
        harness = KbHarness(app=app, admin=admin, storage=storage)

        async def record_delete(document_id: int, settings: AISettings) -> None:
            row_exists = (await admin.get("/admin/kb-documents")).json()["total"] > 0
            harness.deletes.append((document_id, row_exists))

        harness.runner.delete_points = record_delete
        yield harness


@pytest.fixture()
def ai_settings() -> Iterator[AISettings]:
    yield settings_for("http://127.0.0.1:9/v1", ai_embedding_model="kb-route-tests", ingest_timeout_s=60)


@pytest.fixture()
async def kb(_migrate_fresh: None, tmp_path: Path, ai_settings: AISettings) -> AsyncIterator[KbHarness]:
    async with kb_harness(tmp_path / "kb", ai_settings) as harness:
        yield harness


@pytest.mark.anyio()
async def test_G1_only_pdf_txt_and_docx_are_accepted(kb: KbHarness) -> None:
    for name in ("slides.pptx", "notes", "image.png"):
        response = await kb.admin.post("/admin/kb-documents", params={"filename": name}, content=b"data")
        assert response.status_code == 415
        assert response.json()["detail"]["error"]["code"] == "unsupported_type"
    assert kb.stored_files() == []
    assert (await kb.admin.get("/admin/kb-documents")).json()["total"] == 0


@pytest.mark.anyio()
async def test_G2_a_declared_size_over_the_limit_is_rejected(kb: KbHarness) -> None:
    response = await kb.admin.post("/admin/kb-documents", params={"filename": "big.pdf"}, content=b"x" * (LIMIT + 1))
    assert response.status_code == 413
    assert response.json()["detail"]["error"]["code"] == "file_too_large"
    assert kb.stored_files() == []


@pytest.mark.anyio()
async def test_G2_a_streamed_body_over_the_limit_is_aborted_and_the_partial_file_removed(kb: KbHarness) -> None:
    async def body() -> AsyncIterator[bytes]:
        for _ in range(10):
            yield b"y" * 1024

    response = await kb.admin.post("/admin/kb-documents", params={"filename": "big.txt"}, content=body())
    assert response.status_code == 413
    assert response.json()["detail"]["error"]["message"] == "The file is larger than 4 KB."
    assert kb.stored_files() == []
    assert (await kb.admin.get("/admin/kb-documents")).json()["total"] == 0


@pytest.mark.anyio()
async def test_G2_G11_the_real_size_is_stored_and_the_file_sits_on_the_kb_volume(kb: KbHarness, db_engine: Engine) -> None:
    document = await kb.upload("handbook.pdf", PDF)
    assert document["file_size_bytes"] == len(PDF)
    with db_engine.connect() as conn:
        storage_path = conn.execute(text("SELECT storage_path FROM kb_document")).scalar_one()
    assert Path(storage_path).parent == kb.storage
    assert Path(storage_path).read_bytes() == PDF


@pytest.mark.anyio()
async def test_G3_the_same_content_is_rejected_as_a_duplicate(kb: KbHarness) -> None:
    await kb.upload("handbook.pdf", PDF)
    files_before = kb.stored_files()
    response = await kb.admin.post("/admin/kb-documents", params={"filename": "copy.pdf"}, content=PDF)
    assert response.status_code == 409
    assert response.json()["detail"]["error"]["code"] == "duplicate_document"
    assert kb.stored_files() == files_before
    assert (await kb.admin.get("/admin/kb-documents")).json()["total"] == 1


@pytest.mark.anyio()
async def test_G5_upload_returns_immediately_as_uploaded_and_the_job_makes_it_ready(kb: KbHarness) -> None:
    document = await kb.upload("handbook.pdf", PDF)
    assert document["status"] == "uploaded"
    assert document["uploaded_by"] == "admin1"
    await kb.runner.join()
    assert (await kb.listed())["handbook.pdf"]["status"] == "ready"


@pytest.mark.anyio()
async def test_G5_a_failed_job_stores_the_error_message(_migrate_fresh: None, tmp_path: Path, ai_settings: AISettings) -> None:
    async with kb_harness(tmp_path / "kb", ai_settings, scanned_ingest) as harness:
        await harness.upload("scan.pdf", PDF)
        await harness.runner.join()
        listed = (await harness.listed())["scan.pdf"]
        assert listed["status"] == "failed"
        assert listed["error_message"] == NO_TEXT_MESSAGE


@pytest.mark.anyio()
async def test_G5_without_ai_settings_the_job_fails_with_a_clear_message(_migrate_fresh: None, tmp_path: Path) -> None:
    async with kb_harness(tmp_path / "kb", None) as harness:
        await harness.upload("handbook.pdf", PDF)
        await harness.runner.join()
        listed = (await harness.listed())["handbook.pdf"]
        assert (listed["status"], listed["error_message"]) == ("failed", AI_NOT_CONFIGURED)


@pytest.mark.anyio()
async def test_G5_I12_jobs_run_one_at_a_time_in_order(kb: KbHarness) -> None:
    ids = [int(str((await kb.upload(f"doc{i}.txt", f"document number {i}".encode()))["id"])) for i in range(3)]
    await kb.runner.join()
    log = (kb.storage / JOB_LOG).read_text(encoding="utf-8").split()
    assert log == [word for document_id in ids for word in ("start", str(document_id), "end", str(document_id))]
    assert all(item["status"] == "ready" for item in (await kb.listed()).values())


@pytest.mark.anyio()
async def test_I12_a_slow_parser_is_killed_at_the_timeout(_migrate_fresh: None, tmp_path: Path) -> None:
    settings = settings_for("http://127.0.0.1:9/v1", ai_embedding_model="kb-route-tests", ingest_timeout_s=3)
    async with kb_harness(tmp_path / "kb", settings, hanging_ingest) as harness:
        await harness.upload("slow.pdf", PDF)
        await asyncio.wait_for(harness.runner.join(), timeout=60)
        listed = (await harness.listed())["slow.pdf"]
        assert listed["status"] == "failed"
        assert listed["error_message"] == "Ingestion timed out after 3 s"


@pytest.mark.anyio()
async def test_G6_retry_and_reindex_set_uploaded_and_rerun(kb: KbHarness) -> None:
    kb.runner.ingest_function = scanned_ingest
    document = await kb.upload("handbook.pdf", PDF)
    await kb.runner.join()
    assert (await kb.listed())["handbook.pdf"]["status"] == "failed"

    kb.runner.ingest_function = quick_ingest
    retried = await kb.admin.post(f"/admin/kb-documents/{document['id']}/reindex")
    assert retried.status_code == 200
    assert (retried.json()["status"], retried.json()["error_message"]) == ("uploaded", None)
    await kb.runner.join()
    assert (await kb.listed())["handbook.pdf"]["status"] == "ready"

    reindexed = await kb.admin.post(f"/admin/kb-documents/{document['id']}/reindex")
    assert reindexed.json()["status"] == "uploaded"
    await kb.runner.join()
    assert [doc_id for doc_id, _ in kb.runner.completed] == [document["id"]] * 3


@pytest.mark.anyio()
async def test_G7_startup_resets_processing_rows_and_reruns_them(_migrate_fresh: None, tmp_path: Path, ai_settings: AISettings, db_engine: Engine) -> None:
    storage = tmp_path / "kb"
    storage.mkdir()
    from scripts.create_admin import create_admin

    create_admin(TEST_DB_URL, "admin1", "adminpass1", "Admin One", "TestCity")
    with db_engine.begin() as conn:
        admin_id = conn.execute(text("SELECT id FROM account WHERE username = 'admin1'")).scalar_one()
        for name, status in (("stuck.txt", "processing"), ("queued.txt", "uploaded"), ("done.txt", "ready")):
            path = storage / name
            path.write_text(f"content of {name}", encoding="utf-8")
            conn.execute(
                text(
                    "INSERT INTO kb_document (filename, file_type, file_size_bytes, storage_path, content_hash, status, uploaded_by) "
                    "VALUES (:n, 'txt', 10, :p, :h, :s, :a)"
                ),
                {"n": name, "p": str(path), "h": uuid.uuid4().hex, "s": status, "a": admin_id},
            )
    with db_engine.connect() as conn:
        rerun_ids = conn.execute(
            text("SELECT id FROM kb_document WHERE filename IN ('stuck.txt', 'queued.txt') ORDER BY id")
        ).scalars().all()
    async with kb_harness(storage, ai_settings, create_admin_account=False) as harness:
        await harness.runner.join()
        statuses = {name: item["status"] for name, item in (await harness.listed()).items()}
        assert statuses == {"stuck.txt": "ready", "queued.txt": "ready", "done.txt": "ready"}
        assert [document_id for document_id, _ in harness.runner.completed] == list(rerun_ids)


@pytest.mark.anyio()
async def test_G9_delete_removes_points_then_the_file_then_the_row(kb: KbHarness, db_engine: Engine) -> None:
    document = await kb.upload("handbook.pdf", PDF)
    await kb.runner.join()
    with db_engine.connect() as conn:
        storage_path = Path(conn.execute(text("SELECT storage_path FROM kb_document")).scalar_one())

    response = await kb.admin.delete(f"/admin/kb-documents/{document['id']}")
    assert response.status_code == 204
    assert kb.deletes == [(document["id"], True)]
    assert not storage_path.exists()
    assert (await kb.admin.get("/admin/kb-documents")).json()["total"] == 0


@pytest.mark.anyio()
async def test_G9_when_qdrant_fails_the_row_and_file_are_kept(kb: KbHarness) -> None:
    async def broken(document_id: int, settings: AISettings) -> None:
        raise ConnectionError("qdrant down")

    kb.runner.delete_points = broken
    document = await kb.upload("handbook.pdf", PDF)
    response = await kb.admin.delete(f"/admin/kb-documents/{document['id']}")
    assert response.status_code == 503
    assert response.json()["detail"]["error"]["code"] == "kb_index_unavailable"
    assert (await kb.admin.get("/admin/kb-documents")).json()["total"] == 1
    assert len(kb.stored_files()) == 1


@pytest.mark.anyio()
async def test_G10_replacing_a_document_is_delete_then_upload(kb: KbHarness) -> None:
    document = await kb.upload("handbook.pdf", PDF)
    assert (await kb.admin.delete(f"/admin/kb-documents/{document['id']}")).status_code == 204
    again = await kb.upload("handbook.pdf", PDF)
    assert again["id"] != document["id"]


@pytest.mark.anyio()
async def test_B7_uploaded_by_is_the_admin_and_users_cannot_manage_documents(kb: KbHarness, db_engine: Engine) -> None:
    await kb.upload("handbook.pdf", PDF)
    with db_engine.connect() as conn:
        role = conn.execute(text("SELECT a.role FROM kb_document d JOIN account a ON a.id = d.uploaded_by")).scalar_one()
    assert role == "admin"
    async with AsyncClient(transport=ASGITransport(app=kb.app), base_url="https://test") as user:
        await user.post("/auth/signup", json={"username": "user1", "password": "userpass1"})
        await user.post("/auth/login", json={"username": "user1", "password": "userpass1"})
        assert (await user.get("/admin/kb-documents")).status_code == 403
        assert (await user.post("/admin/kb-documents", params={"filename": "x.pdf"}, content=PDF)).status_code == 403


@pytest.mark.anyio()
async def test_listing_is_paginated_and_reports_the_upload_limit(kb: KbHarness) -> None:
    for i in range(3):
        await kb.upload(f"doc{i}.txt", f"text {i}".encode())
    page = (await kb.admin.get("/admin/kb-documents", params={"limit": 2, "offset": 0})).json()
    assert (page["total"], len(page["items"]), page["max_upload_bytes"]) == (3, 2, LIMIT)
    rest = (await kb.admin.get("/admin/kb-documents", params={"limit": 2, "offset": 2})).json()
    assert len(rest["items"]) == 1
    assert {i["filename"] for i in page["items"] + rest["items"]} == {"doc0.txt", "doc1.txt", "doc2.txt"}


@pytest.mark.anyio()
async def test_G4_G6_a_real_ingest_runs_in_a_child_process_and_fills_qdrant(_migrate_fresh: None, tmp_path: Path) -> None:
    from chatbot_ai.ingest import ingest

    with run_fake_openai() as fake:
        settings = settings_for(fake.base_url, ai_embedding_model=f"test-{uuid.uuid4().hex[:10]}")
        try:
            async with kb_harness(tmp_path / "kb", settings, ingest) as harness:
                document = await harness.upload("rules.txt", b"Claims must be filed within 90 days.\n\nAppeals take 15 days.")
                await harness.runner.join()
                assert (await harness.listed())["rules.txt"]["status"] == "ready"
                assert len(fake.embedding_requests) == 1
                client = make_qdrant(settings)
                records, _ = await client.scroll(collection_name(settings), scroll_filter=document_filter(int(str(document["id"]))), with_payload=True)
                assert [r.payload["content"] for r in records if r.payload] == ["Claims must be filed within 90 days.\n\nAppeals take 15 days."]
                await client.close()
        finally:
            client = make_qdrant(settings)
            if await client.collection_exists(collection_name(settings)):
                await client.delete_collection(collection_name(settings))
            await client.close()
