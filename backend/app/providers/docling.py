from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import local
from typing import Any

from app.providers.interfaces import DocumentParsingError, ParsedChunk

WorkerKey = tuple[int, str, str | None]
_worker_state = local()


def _load_components(
    max_tokens: int, model_path: str, artifacts_path: str | None
) -> tuple[Any, Any]:
    try:
        from docling.chunking import HybridChunker
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling_core.transforms.chunker.tokenizer.huggingface import (
            HuggingFaceTokenizer,
        )
        from transformers import AutoTokenizer
    except ImportError as exc:
        raise DocumentParsingError(
            "Docling and transformers are required for permanent ingestion"
        ) from exc
    format_options = None
    if artifacts_path is not None:
        artifacts = Path(artifacts_path)
        if not artifacts.is_dir():
            raise DocumentParsingError(f"Docling artifacts are missing: {artifacts}")
        format_options = {
            InputFormat.PDF: PdfFormatOption(
                pipeline_options=PdfPipelineOptions(artifacts_path=artifacts)
            )
        }
    tokenizer = HuggingFaceTokenizer(
        tokenizer=AutoTokenizer.from_pretrained(model_path, local_files_only=True),
        max_tokens=max_tokens,
    )
    converter = DocumentConverter(format_options=format_options)
    if format_options is not None:
        converter.initialize_pipeline(InputFormat.PDF)
    return converter, HybridChunker(tokenizer=tokenizer, merge_peers=True)


def _worker_parser(
    max_tokens: int, model_path: str, artifacts_path: str | None
) -> tuple[Any, Any]:
    key = (max_tokens, model_path, artifacts_path)
    components = getattr(_worker_state, "components", None)
    if components is None:
        components = {}
        _worker_state.components = components
    if key not in components:
        components[key] = _load_components(*key)
    return components[key]


def _parse_in_worker(
    path: str, max_tokens: int, model_path: str, artifacts_path: str | None
) -> list[ParsedChunk]:
    converter, chunker = _worker_parser(max_tokens, model_path, artifacts_path)
    try:
        document = converter.convert(Path(path)).document
        parsed: list[ParsedChunk] = []
        for chunk in chunker.chunk(dl_doc=document):
            text = str(chunker.contextualize(chunk)).strip()
            if not text:
                continue
            meta = getattr(chunk, "meta", None)
            headings = [
                str(item)
                for item in (getattr(meta, "headings", None) or [])
                if str(item).strip()
            ]
            page: int | None = None
            for item in getattr(meta, "doc_items", None) or []:
                provenance = getattr(item, "prov", None) or []
                if provenance:
                    raw_page = getattr(provenance[0], "page_no", None)
                    if raw_page is not None:
                        page = int(raw_page)
                        break
            parsed.append(ParsedChunk(text=text, heading_path=headings, page=page))
        if not parsed:
            raise DocumentParsingError("Docling produced no text chunks")
        return parsed
    except DocumentParsingError:
        raise
    except Exception as exc:
        raise DocumentParsingError("Docling parsing or chunking failed") from exc


def _warmup_worker(
    max_tokens: int, model_path: str, artifacts_path: str | None
) -> None:
    _worker_parser(max_tokens, model_path, artifacts_path)


class DoclingHybridParser:
    def __init__(
        self,
        max_tokens: int = 800,
        model_path: str | Path = "/opt/models/bge-m3",
        artifacts_path: str | Path | None = None,
        workers: int = 1,
    ) -> None:
        self._max_tokens = max_tokens
        self._model_path = Path(model_path)
        self._artifacts_path = Path(artifacts_path) if artifacts_path else None
        self._executor = ThreadPoolExecutor(
            max_workers=workers,
            thread_name_prefix="docling",
        )

    def _worker_args(self) -> tuple[int, str, str | None]:
        return (
            self._max_tokens,
            str(self._model_path),
            str(self._artifacts_path) if self._artifacts_path else None,
        )

    async def warmup(self) -> None:
        """Load the configured PDF pipeline before the app becomes ready."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(self._executor, _warmup_worker, *self._worker_args())

    async def parse(self, path: Path) -> list[ParsedChunk]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._executor, _parse_in_worker, str(path), *self._worker_args()
        )

    async def close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)
