from __future__ import annotations

import asyncio
import logging
import multiprocessing
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from multiprocessing.connection import Connection
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.metrics import (
    kb_documents_processing,
    kb_ingest_duration_seconds,
    kb_ingest_total,
)
from backend.models import KbDocument, KbDocumentStatus, KbFileType
from chatbot_ai.ingest import IngestResult, delete_document_async
from chatbot_ai.ingest.parse import FileType
from chatbot_ai.settings import AISettings

logger = logging.getLogger(__name__)

IngestFunction = Callable[[int, str, FileType, AISettings], IngestResult]
DeletePoints = Callable[[int, AISettings], Awaitable[None]]
AI_NOT_CONFIGURED = "The AI service is not configured (AI settings are missing)."


@dataclass(frozen=True)
class JobSucceeded:
    result: IngestResult


@dataclass(frozen=True)
class JobFailed:
    message: str


JobOutcome = JobSucceeded | JobFailed


@dataclass(frozen=True)
class ChildRun:
    outcome: JobOutcome
    pid: int | None
    exitcode: int | None


@dataclass(frozen=True)
class JobRecord:
    document_id: int
    outcome: JobOutcome
    child_pid: int | None = None
    child_exitcode: int | None = None


def _child_main(ingest: IngestFunction, document_id: int, path: str, file_type: FileType, settings: AISettings, conn: Connection) -> None:
    try:
        conn.send(JobSucceeded(ingest(document_id, path, file_type, settings)))
    except Exception as error:  # noqa: BLE001 - every failure becomes the document's error_message
        conn.send(JobFailed(str(error) or type(error).__name__))
    finally:
        conn.close()


async def run_in_child(
    ingest: IngestFunction, document_id: int, path: str, file_type: FileType, settings: AISettings, timeout_s: float
) -> ChildRun:
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(target=_child_main, args=(ingest, document_id, path, file_type, settings, sender), daemon=True)
    process.start()
    sender.close()
    try:
        await asyncio.to_thread(process.join, timeout_s)
        if process.is_alive():
            process.kill()
            await asyncio.to_thread(process.join)
            return ChildRun(JobFailed(f"Ingestion timed out after {timeout_s:g} s"), process.pid, process.exitcode)
        if receiver.poll():
            outcome: JobOutcome = receiver.recv()
            return ChildRun(outcome, process.pid, process.exitcode)
        return ChildRun(JobFailed(f"Ingestion process exited with code {process.exitcode}"), process.pid, process.exitcode)
    finally:
        receiver.close()
        if process.is_alive():
            process.kill()


def ingest_file_type(file_type: KbFileType) -> FileType:
    match file_type:
        case KbFileType.pdf:
            return "pdf"
        case KbFileType.docx:
            return "docx"
        case KbFileType.txt:
            return "txt"


COMPLETED_JOBS_KEPT = 100
CHILD_START_FAILED = "The ingestion job could not start. Upload the document again."


class KbJobRunner:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        ai_settings: AISettings | None,
        ingest: IngestFunction,
        delete_points: DeletePoints = delete_document_async,
    ) -> None:
        self._session_factory = session_factory
        self._ai_settings = ai_settings
        self.ingest_function = ingest
        self.delete_points = delete_points
        self._queue: asyncio.Queue[int] = asyncio.Queue()
        self._worker: asyncio.Task[None] | None = None
        self.completed: deque[JobRecord] = deque(maxlen=COMPLETED_JOBS_KEPT)

    @property
    def ai_settings(self) -> AISettings | None:
        return self._ai_settings

    async def start(self) -> None:
        async with self._session_factory() as db:
            await db.execute(
                update(KbDocument)
                .where(KbDocument.status == KbDocumentStatus.processing)
                .values(status=KbDocumentStatus.uploaded)
            )
            await db.commit()
            pending = (
                await db.execute(
                    select(KbDocument.id).where(KbDocument.status == KbDocumentStatus.uploaded).order_by(KbDocument.id)
                )
            ).scalars()
            for document_id in pending:
                self.enqueue(document_id)
        self._worker = asyncio.create_task(self._work())

    async def stop(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
            await asyncio.gather(self._worker, return_exceptions=True)
            self._worker = None

    def enqueue(self, document_id: int) -> None:
        self._queue.put_nowait(document_id)

    async def join(self) -> None:
        await self._queue.join()

    async def _work(self) -> None:
        while True:
            document_id = await self._queue.get()
            try:
                await self.process(document_id)
            except Exception:
                logger.exception("KB job for document %s crashed", document_id)
            finally:
                self._queue.task_done()

    async def _set_status(self, document_id: int, status: KbDocumentStatus, error: str | None) -> bool:
        async with self._session_factory() as db:
            document = await db.get(KbDocument, document_id)
            if document is None:
                return False
            document.status = status
            document.error_message = error
            await db.commit()
            return True

    async def process(self, document_id: int) -> None:
        async with self._session_factory() as db:
            document = await db.get(KbDocument, document_id)
            if document is None or document.status != KbDocumentStatus.uploaded:
                return
            path, file_type = document.storage_path, ingest_file_type(document.file_type)
            document.status = KbDocumentStatus.processing
            document.error_message = None
            await db.commit()
        kb_documents_processing.inc()
        started = time.monotonic()

        settings = self._ai_settings
        try:
            if settings is None:
                record = JobRecord(document_id, JobFailed(AI_NOT_CONFIGURED))
            elif not Path(path).is_file():
                record = JobRecord(document_id, JobFailed("The uploaded file is missing from storage."))
            else:
                run = await run_in_child(self.ingest_function, document_id, path, file_type, settings, settings.ingest_timeout_s)
                record = JobRecord(document_id, run.outcome, run.pid, run.exitcode)
        except Exception:
            # G5: a job that cannot run still leaves the document in a final state
            logger.exception("KB job for document %s could not run", document_id)
            record = JobRecord(document_id, JobFailed(CHILD_START_FAILED))
        finally:
            kb_documents_processing.dec()
        self.completed.append(record)
        outcome = record.outcome
        kb_ingest_duration_seconds.observe(time.monotonic() - started)
        kb_ingest_total.labels(outcome="ok" if isinstance(outcome, JobSucceeded) else "failed").inc()

        if isinstance(outcome, JobSucceeded):
            still_there = await self._set_status(document_id, KbDocumentStatus.ready, None)
            if not still_there and settings is not None:
                await self.delete_points(document_id, settings)
        else:
            await self._set_status(document_id, KbDocumentStatus.failed, outcome.message)
