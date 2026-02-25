"""Cloud storage providers for accessing files in AWS S3 and Azure Blob Storage.

Provides a uniform interface for listing and downloading files from cloud
object stores so that :class:`~geodatarev.scanner.DirectoryScanner` can
operate on remote data in the same way it handles local directories.
"""

from __future__ import annotations

import os
import posixpath
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


def parse_cloud_uri(uri: str) -> tuple[str, str, str]:
    """Parse a cloud storage URI into ``(scheme, bucket, prefix)``.

    Supported schemes
    -----------------
    * ``s3://bucket/prefix``
    * ``az://container/prefix``  (Azure Blob Storage)

    Returns
    -------
    tuple[str, str, str]
        ``(scheme, bucket_or_container, prefix)``

    Raises
    ------
    ValueError
        If the URI scheme is not recognised.
    """
    for scheme in ("s3://", "az://"):
        if uri.startswith(scheme):
            rest = uri[len(scheme):]
            parts = rest.split("/", 1)
            bucket = parts[0]
            prefix = parts[1] if len(parts) > 1 else ""
            return scheme.rstrip(":/"), bucket, prefix
    raise ValueError(
        f"Unsupported cloud URI scheme: {uri!r}. Use 's3://' or 'az://'."
    )


def is_cloud_uri(path: str) -> bool:
    """Return *True* if *path* looks like a cloud storage URI."""
    return path.startswith("s3://") or path.startswith("az://")


@dataclass
class CloudObject:
    """Metadata for a single object in cloud storage."""

    key: str
    size: int = 0

    @property
    def name(self) -> str:
        """Basename of the key (like a filename)."""
        return posixpath.basename(self.key)

    @property
    def suffix(self) -> str:
        """File extension (lower-cased), e.g. ``'.grd'``."""
        _, ext = posixpath.splitext(self.key)
        return ext.lower()


# ---------------------------------------------------------------------------
# Provider base class
# ---------------------------------------------------------------------------

class CloudStorageProvider:
    """Abstract base for cloud storage backends."""

    def list_objects(
        self,
        bucket: str,
        prefix: str = "",
        recursive: bool = True,
        extensions: set[str] | None = None,
    ) -> list[CloudObject]:
        """List objects under *prefix* in *bucket*.

        Parameters
        ----------
        bucket : str
            Bucket or container name.
        prefix : str
            Key prefix (folder path).
        recursive : bool
            Whether to list recursively.
        extensions : set[str] or None
            If given, only include objects whose suffix is in the set.

        Returns
        -------
        list[CloudObject]
        """
        raise NotImplementedError

    def download(self, bucket: str, key: str, dest: str | Path) -> Path:
        """Download an object to a local path.

        Parameters
        ----------
        bucket : str
            Bucket or container name.
        key : str
            Full object key.
        dest : str or Path
            Local destination file path.

        Returns
        -------
        Path
            The local path of the downloaded file.
        """
        raise NotImplementedError


# ---------------------------------------------------------------------------
# AWS S3
# ---------------------------------------------------------------------------

class S3StorageProvider(CloudStorageProvider):
    """AWS S3 storage provider.

    Parameters
    ----------
    client :
        An optional pre-configured ``boto3`` S3 client.  When *None*,
        a default client is created via ``boto3.client('s3')``.
    """

    def __init__(self, client=None):
        if client is not None:
            self._client = client
        else:
            import boto3
            self._client = boto3.client("s3")

    def list_objects(
        self,
        bucket: str,
        prefix: str = "",
        recursive: bool = True,
        extensions: set[str] | None = None,
    ) -> list[CloudObject]:
        paginator = self._client.get_paginator("list_objects_v2")
        params: dict = {"Bucket": bucket, "Prefix": prefix}
        if not recursive:
            params["Delimiter"] = "/"

        objects: list[CloudObject] = []
        for page in paginator.paginate(**params):
            for item in page.get("Contents", []):
                key: str = item["Key"]
                if key.endswith("/"):
                    continue
                obj = CloudObject(key=key, size=item.get("Size", 0))
                if extensions is not None and obj.suffix not in extensions:
                    continue
                objects.append(obj)
        objects.sort(key=lambda o: o.key)
        return objects

    def download(self, bucket: str, key: str, dest: str | Path) -> Path:
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        self._client.download_file(bucket, key, str(dest))
        return dest


# ---------------------------------------------------------------------------
# Azure Blob Storage
# ---------------------------------------------------------------------------

class AzureBlobStorageProvider(CloudStorageProvider):
    """Azure Blob Storage provider.

    Parameters
    ----------
    client :
        An optional pre-configured ``BlobServiceClient``.  When *None*,
        a default client is created from the ``AZURE_STORAGE_CONNECTION_STRING``
        environment variable.
    """

    def __init__(self, client=None):
        if client is not None:
            self._client = client
        else:
            from azure.storage.blob import BlobServiceClient
            conn_str = os.environ.get("AZURE_STORAGE_CONNECTION_STRING", "")
            self._client = BlobServiceClient.from_connection_string(conn_str)

    def list_objects(
        self,
        bucket: str,
        prefix: str = "",
        recursive: bool = True,
        extensions: set[str] | None = None,
    ) -> list[CloudObject]:
        container_client = self._client.get_container_client(bucket)

        if recursive:
            blobs = container_client.list_blobs(name_starts_with=prefix or None)
        else:
            blobs = container_client.walk_blobs(
                name_starts_with=prefix or None, delimiter="/"
            )

        objects: list[CloudObject] = []
        for blob in blobs:
            # walk_blobs may yield BlobPrefix items; skip those
            if not hasattr(blob, "size"):
                continue
            key: str = blob.name
            if key.endswith("/"):
                continue
            obj = CloudObject(key=key, size=blob.size or 0)
            if extensions is not None and obj.suffix not in extensions:
                continue
            objects.append(obj)
        objects.sort(key=lambda o: o.key)
        return objects

    def download(self, bucket: str, key: str, dest: str | Path) -> Path:
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        blob_client = self._client.get_blob_client(container=bucket, blob=key)
        with open(dest, "wb") as fh:
            stream = blob_client.download_blob()
            fh.write(stream.readall())
        return dest


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_provider(scheme: str, client=None) -> CloudStorageProvider:
    """Return a :class:`CloudStorageProvider` for the given URI scheme.

    Parameters
    ----------
    scheme : str
        ``"s3"`` or ``"az"``.
    client :
        An optional pre-configured cloud client to pass to the provider.

    Returns
    -------
    CloudStorageProvider

    Raises
    ------
    ValueError
        If *scheme* is not supported.
    """
    if scheme == "s3":
        return S3StorageProvider(client=client)
    if scheme == "az":
        return AzureBlobStorageProvider(client=client)
    raise ValueError(f"Unsupported cloud storage scheme: {scheme!r}")
