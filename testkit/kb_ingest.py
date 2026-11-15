from __future__ import annotations

import threading
from pathlib import Path

from chatbot_ai.ingest import IngestResult, IngestTimings, NoExtractableText
from chatbot_ai.ingest.parse import FileType
from chatbot_ai.settings import AISettings

JOB_LOG = "job-log.txt"


def _log(file_path: str, line: str) -> None:
    with (Path(file_path).parent / JOB_LOG).open("a", encoding="utf-8") as log:
        log.write(line + "\n")


def quick_ingest(document_id: int, file_path: str, file_type: FileType, settings: AISettings) -> IngestResult:
    _log(file_path, f"start {document_id}")
    chunks = max(1, len(Path(file_path).read_bytes()) // 100)
    _log(file_path, f"end {document_id}")
    return IngestResult(chunk_count=chunks, table_chunks=0, timings=IngestTimings(parse=0.0, chunk=0.0, embed=0.0, upsert=0.0))


def scanned_ingest(document_id: int, file_path: str, file_type: FileType, settings: AISettings) -> IngestResult:
    raise NoExtractableText()


def hanging_ingest(document_id: int, file_path: str, file_type: FileType, settings: AISettings) -> IngestResult:
    threading.Event().wait()
    raise AssertionError("unreachable")
