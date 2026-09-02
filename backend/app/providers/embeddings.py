from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from app.core.config import (
    EMBEDDING_CONTEXT_LIMIT,
    EMBEDDING_DIMENSION,
)
from app.providers.interfaces import EmbeddingError, HybridEmbedding


class BgeM3EmbeddingProvider:
    def __init__(
        self,
        device: str = "cpu",
        batch_size: int = 8,
        model_path: str | Path = "/opt/models/bge-m3",
    ) -> None:
        self._device = device
        self._model_path = Path(model_path)
        self._batch_size = batch_size
        self._model: Any | None = None
        self._model_lock = asyncio.Lock()
        self._inference_lock = asyncio.Lock()

    async def _get_model(self) -> Any:
        if self._model is not None:
            return self._model
        async with self._model_lock:
            if self._model is not None:
                return self._model

            def load() -> Any:
                try:
                    from FlagEmbedding import BGEM3FlagModel
                except ImportError as exc:
                    raise EmbeddingError(
                        "FlagEmbedding is required for BAAI/bge-m3"
                    ) from exc
                if not self._model_path.is_dir():
                    raise EmbeddingError(
                        f"Локальная модель BAAI/bge-m3 не найдена: {self._model_path}"
                    )
                return BGEM3FlagModel(
                    str(self._model_path),
                    devices=self._device,
                    use_fp16=self._device != "cpu",
                )

            self._model = await asyncio.to_thread(load)
            return self._model

    async def warmup(self) -> None:
        """Load and execute the local model before the app accepts requests."""
        await self.embed_documents(["Проверка готовности локальной модели BGE-M3."])

    async def embed_documents(self, texts: list[str]) -> list[HybridEmbedding]:
        if not texts:
            return []
        model = await self._get_model()

        def encode() -> list[HybridEmbedding]:
            try:
                output = model.encode(
                    texts,
                    batch_size=self._batch_size,
                    max_length=EMBEDDING_CONTEXT_LIMIT,
                    return_dense=True,
                    return_sparse=True,
                    return_colbert_vecs=False,
                )
                dense_vectors = output["dense_vecs"]
                lexical_weights = output["lexical_weights"]
                result: list[HybridEmbedding] = []
                for dense, sparse in zip(dense_vectors, lexical_weights, strict=True):
                    dense_list = [float(value) for value in dense.tolist()]
                    if len(dense_list) != EMBEDDING_DIMENSION:
                        raise EmbeddingError(
                            f"BGE-M3 returned {len(dense_list)} dense dimensions"
                        )
                    sparse_items = sorted(
                        (int(token_id), float(weight))
                        for token_id, weight in sparse.items()
                        if float(weight) != 0.0
                    )
                    result.append(
                        HybridEmbedding(
                            dense=dense_list,
                            sparse_indices=[item[0] for item in sparse_items],
                            sparse_values=[item[1] for item in sparse_items],
                        )
                    )
                return result
            except EmbeddingError:
                raise
            except Exception as exc:
                raise EmbeddingError("BAAI/bge-m3 encoding failed") from exc

        async with self._inference_lock:
            return await asyncio.to_thread(encode)

    async def embed_query(self, text: str) -> HybridEmbedding:
        return (await self.embed_documents([text]))[0]
