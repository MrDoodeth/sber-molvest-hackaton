from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from app.providers.interfaces import DocumentParsingError, ParsedChunk


class DoclingHybridParser:
    def __init__(
        self,
        max_tokens: int = 800,
        model_path: str | Path = "/opt/models/bge-m3",
        artifacts_path: str | Path | None = None,
    ) -> None:
        self._max_tokens = max_tokens
        self._model_path = Path(model_path)
        self._artifacts_path = Path(artifacts_path) if artifacts_path else None
        self._converter: Any | None = None
        self._chunker: Any | None = None
        self._load_lock = asyncio.Lock()

    async def _load(self) -> tuple[Any, Any]:
        if self._converter is not None and self._chunker is not None:
            return self._converter, self._chunker
        async with self._load_lock:
            if self._converter is not None and self._chunker is not None:
                return self._converter, self._chunker

            def load() -> tuple[Any, Any]:
                try:
                    from docling.chunking import HybridChunker
                    from docling.datamodel.base_models import InputFormat
                    from docling.datamodel.pipeline_options import PdfPipelineOptions
                    from docling.document_converter import (
                        DocumentConverter,
                        PdfFormatOption,
                    )
                    from docling_core.transforms.chunker.tokenizer.huggingface import (
                        HuggingFaceTokenizer,
                    )
                    from transformers import AutoTokenizer
                except ImportError as exc:
                    raise DocumentParsingError(
                        "Docling and transformers are required for permanent ingestion"
                    ) from exc
                format_options = None
                if self._artifacts_path is not None:
                    if not self._artifacts_path.is_dir():
                        raise DocumentParsingError(
                            f"Docling artifacts are missing: {self._artifacts_path}"
                        )
                    format_options = {
                        InputFormat.PDF: PdfFormatOption(
                            pipeline_options=PdfPipelineOptions(
                                artifacts_path=self._artifacts_path
                            )
                        )
                    }
                tokenizer = HuggingFaceTokenizer(
                    tokenizer=AutoTokenizer.from_pretrained(
                        str(self._model_path), local_files_only=True
                    ),
                    max_tokens=self._max_tokens,
                )
                converter = DocumentConverter(format_options=format_options)
                if format_options is not None:
                    converter.initialize_pipeline(InputFormat.PDF)
                return converter, HybridChunker(
                    tokenizer=tokenizer,
                    merge_peers=True,
                )

            self._converter, self._chunker = await asyncio.to_thread(load)
            return self._converter, self._chunker

    async def warmup(self) -> None:
        """Load the configured PDF pipeline before the app becomes ready."""
        await self._load()

    async def parse(self, path: Path) -> list[ParsedChunk]:
        converter, chunker = await self._load()

        def convert() -> list[ParsedChunk]:
            try:
                document = converter.convert(path).document
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
                    parsed.append(
                        ParsedChunk(text=text, heading_path=headings, page=page)
                    )
                if not parsed:
                    raise DocumentParsingError("Docling produced no text chunks")
                return parsed
            except DocumentParsingError:
                raise
            except Exception as exc:
                raise DocumentParsingError(
                    "Docling parsing or chunking failed"
                ) from exc

        return await asyncio.to_thread(convert)
