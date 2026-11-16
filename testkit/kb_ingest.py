from __future__ import annotations

import os
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
    (Path(file_path).parent / f"pid-{document_id}.txt").write_text(str(os.getpid()), encoding="utf-8")
    threading.Event().wait()
    raise AssertionError("unreachable")


RUNNING_MARKER = "running.marker"


def _wait_for(path: Path) -> None:
    pause = threading.Event()
    while not path.exists():
        pause.wait(0.02)


def blocking_ingest(document_id: int, file_path: str, file_type: FileType, settings: AISettings) -> IngestResult:
    folder = Path(file_path).parent
    marker = folder / RUNNING_MARKER
    if marker.exists():
        raise RuntimeError("two ingest jobs ran at the same time")
    marker.write_text(str(document_id), encoding="utf-8")
    (folder / f"pid-{document_id}.txt").write_text(str(os.getpid()), encoding="utf-8")
    _wait_for(folder / f"release-{document_id}")
    marker.unlink()
    return IngestResult(chunk_count=1, table_chunks=0, timings=IngestTimings(parse=0.0, chunk=0.0, embed=0.0, upsert=0.0))
