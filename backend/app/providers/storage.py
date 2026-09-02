from __future__ import annotations

import asyncio
import os
import uuid
from pathlib import Path, PurePosixPath
from typing import Any

from app.providers.interfaces import StorageError


def _validate_key(key: str) -> PurePosixPath:
    path = PurePosixPath(key)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise StorageError("Invalid storage key")
    return path


class LocalObjectStorage:
    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    def _path(self, key: str) -> Path:
        relative = _validate_key(key)
        path = (self._root / Path(*relative.parts)).resolve()
        if path != self._root and self._root not in path.parents:
            raise StorageError("Storage key escapes configured root")
        return path

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        del content_type
        path = self._path(key)

        def write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(
                f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
            )
            temporary.write_bytes(data)
            os.replace(temporary, path)

        try:
            await asyncio.to_thread(write)
        except OSError as exc:
            raise StorageError("Unable to write object to local storage") from exc

    async def get(self, key: str) -> bytes:
        path = self._path(key)
        try:
            return await asyncio.to_thread(path.read_bytes)
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
    ) -> None:
        self._bucket = bucket
        self._client_options: dict[str, Any] = {
            "endpoint_url": endpoint_url,
            "region_name": region,
            "aws_access_key_id": access_key_id,
            "aws_secret_access_key": secret_access_key,
            "use_ssl": use_ssl,
        }

    def _session(self) -> Any:
        try:
            import aioboto3
        except ImportError as exc:
            raise StorageError("aioboto3 is required for S3 storage") from exc
        return aioboto3.Session()

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        _validate_key(key)
        try:
            async with self._session().client("s3", **self._client_options) as client:
                await client.put_object(
                    Bucket=self._bucket,
                    Key=key,
                    Body=data,
                    ContentType=content_type,
                )
        except StorageError:
            raise
        except Exception as exc:
            raise StorageError("Unable to write object to S3 storage") from exc

    async def get(self, key: str) -> bytes:
        _validate_key(key)
        try:
            async with self._session().client("s3", **self._client_options) as client:
                response = await client.get_object(Bucket=self._bucket, Key=key)
                async with response["Body"] as body:
                    return bytes(await body.read())
        except StorageError:
            raise
        except Exception as exc:
            raise StorageError("Unable to read object from S3 storage") from exc

    async def delete(self, key: str) -> None:
        _validate_key(key)
        try:
            async with self._session().client("s3", **self._client_options) as client:
                await client.delete_object(Bucket=self._bucket, Key=key)
        except StorageError:
            raise
        except Exception as exc:
            raise StorageError("Unable to delete object from S3 storage") from exc
