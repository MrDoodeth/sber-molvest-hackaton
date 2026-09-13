from __future__ import annotations

import asyncio
import os
import shutil
import uuid
from collections.abc import AsyncIterator
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO

from app.providers.interfaces import StorageError


def _validate_key(key: str) -> PurePosixPath:
    path = PurePosixPath(key)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise StorageError("Invalid storage key")
    return path


class LocalObjectStorage:
    def __init__(self, root: Path, timeout_seconds: float = 60.0) -> None:
        self._root = root.resolve()
        self._timeout_seconds = timeout_seconds

    def _path(self, key: str) -> Path:
        relative = _validate_key(key)
        path = (self._root / Path(*relative.parts)).resolve()
        if path != self._root and self._root not in path.parents:
            raise StorageError("Storage key escapes configured root")
        return path

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        from io import BytesIO

        await self.put_file(key, BytesIO(data), content_type)

    async def put_file(self, key: str, source: BinaryIO, content_type: str) -> None:
        del content_type
        path = self._path(key)

        def write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(
                f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
            )
            source.seek(0)
            with temporary.open("wb") as destination:
                shutil.copyfileobj(source, destination, length=1024 * 1024)
            os.replace(temporary, path)

        try:
            async with asyncio.timeout(self._timeout_seconds):
                await asyncio.to_thread(write)
        except OSError as exc:
            raise StorageError("Unable to write object to local storage") from exc

    async def get(self, key: str) -> bytes:
        path = self._path(key)
        try:
            async with asyncio.timeout(self._timeout_seconds):
                return await asyncio.to_thread(path.read_bytes)
        except FileNotFoundError as exc:
            raise StorageError("Object not found in local storage") from exc
        except OSError as exc:
            raise StorageError("Unable to read object from local storage") from exc

    async def iter_bytes(
        self, key: str, chunk_size: int = 1024 * 1024
    ) -> AsyncIterator[bytes]:
        path = self._path(key)
        try:
            with path.open("rb") as source:
                while chunk := await asyncio.to_thread(source.read, chunk_size):
                    yield chunk
        except FileNotFoundError as exc:
            raise StorageError("Object not found in local storage") from exc
        except OSError as exc:
            raise StorageError("Unable to read object from local storage") from exc

    async def delete(self, key: str) -> None:
        path = self._path(key)

        def remove() -> None:
            try:
                path.unlink()
            except FileNotFoundError:
                return
            parent = path.parent
            while parent != self._root:
                try:
                    parent.rmdir()
                except OSError:
                    break
                parent = parent.parent

        try:
            async with asyncio.timeout(self._timeout_seconds):
                await asyncio.to_thread(remove)
        except OSError as exc:
            raise StorageError("Unable to delete object from local storage") from exc


class S3ObjectStorage:
    def __init__(
        self,
        *,
        bucket: str,
        endpoint_url: str | None,
        region: str,
        access_key_id: str,
        secret_access_key: str,
        use_ssl: bool,
        operation_timeout_seconds: float = 60.0,
        connect_timeout_seconds: float = 10.0,
        read_timeout_seconds: float = 60.0,
    ) -> None:
        from botocore.config import Config

        self._bucket = bucket
        self._operation_timeout_seconds = operation_timeout_seconds
        self._client_options: dict[str, Any] = {
            "endpoint_url": endpoint_url,
            "region_name": region,
            "aws_access_key_id": access_key_id,
            "aws_secret_access_key": secret_access_key,
            "use_ssl": use_ssl,
            "config": Config(
                connect_timeout=connect_timeout_seconds,
                read_timeout=read_timeout_seconds,
            ),
        }

    def _session(self) -> Any:
        try:
            import aioboto3
        except ImportError as exc:
            raise StorageError("aioboto3 is required for S3 storage") from exc
        return aioboto3.Session()

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        from io import BytesIO

        await self.put_file(key, BytesIO(data), content_type)

    async def put_file(self, key: str, source: BinaryIO, content_type: str) -> None:
        _validate_key(key)
        try:
            async with asyncio.timeout(self._operation_timeout_seconds):
                async with self._session().client(
                    "s3", **self._client_options
                ) as client:
                    source.seek(0)
                    await client.upload_fileobj(
                        source,
                        self._bucket,
                        key,
                        ExtraArgs={"ContentType": content_type},
                    )
        except StorageError:
            raise
        except Exception as exc:
            raise StorageError("Unable to write object to S3 storage") from exc

    async def get(self, key: str) -> bytes:
        _validate_key(key)
        try:
            async with asyncio.timeout(self._operation_timeout_seconds):
                async with self._session().client(
                    "s3", **self._client_options
                ) as client:
                    response = await client.get_object(Bucket=self._bucket, Key=key)
                    async with response["Body"] as body:
                        return bytes(await body.read())
        except StorageError:
            raise
        except Exception as exc:
            raise StorageError("Unable to read object from S3 storage") from exc

    async def iter_bytes(
        self, key: str, chunk_size: int = 1024 * 1024
    ) -> AsyncIterator[bytes]:
        _validate_key(key)
        try:
            async with asyncio.timeout(self._operation_timeout_seconds):
                async with self._session().client(
                    "s3", **self._client_options
                ) as client:
                    response = await client.get_object(Bucket=self._bucket, Key=key)
                    async with response["Body"] as body:
                        while chunk := await body.read(chunk_size):
                            yield bytes(chunk)
        except StorageError:
            raise
        except Exception as exc:
            raise StorageError("Unable to read object from S3 storage") from exc

    async def delete(self, key: str) -> None:
        _validate_key(key)
        try:
            async with asyncio.timeout(self._operation_timeout_seconds):
                async with self._session().client(
                    "s3", **self._client_options
                ) as client:
                    await client.delete_object(Bucket=self._bucket, Key=key)
        except StorageError:
            raise
        except Exception as exc:
            raise StorageError("Unable to delete object from S3 storage") from exc
