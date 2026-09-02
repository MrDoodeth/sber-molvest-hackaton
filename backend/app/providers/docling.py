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
    ) -> None:
        self._max_tokens = max_tokens
        self._model_path = Path(model_path)
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
                    from docling.document_converter import DocumentConverter
                    from docling_core.transforms.chunker.tokenizer.huggingface import (
                        HuggingFaceTokenizer,
                    )
                    from transformers import AutoTokenizer
                except ImportError as exc:
                    raise DocumentParsingError(
                        "Docling and transformers are required for permanent ingestion"
                    ) from exc
                tokenizer = HuggingFaceTokenizer(
                    tokenizer=AutoTokenizer.from_pretrained(
                        str(self._model_path), local_files_only=True
                    ),
                    max_tokens=self._max_tokens,
                )
                return DocumentConverter(), HybridChunker(
                    tokenizer=tokenizer,
                    merge_peers=True,
                )

            self._converter, self._chunker = await asyncio.to_thread(load)
            return self._converter, self._chunker

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
