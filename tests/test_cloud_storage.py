"""Tests for geodatarev.cloud_storage."""

import struct
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from geodatarev.cloud_storage import (
    AzureBlobStorageProvider,
    CloudObject,
    CloudStorageProvider,
    S3StorageProvider,
    get_provider,
    is_cloud_uri,
    parse_cloud_uri,
)
from geodatarev.scanner import DirectoryScanner


# ---------------------------------------------------------------------------
# URI parsing
# ---------------------------------------------------------------------------


class TestParseCloudUri:
    def test_s3_full(self):
        scheme, bucket, prefix = parse_cloud_uri("s3://my-bucket/some/prefix")
        assert scheme == "s3"
        assert bucket == "my-bucket"
        assert prefix == "some/prefix"

    def test_s3_no_prefix(self):
        scheme, bucket, prefix = parse_cloud_uri("s3://my-bucket")
        assert scheme == "s3"
        assert bucket == "my-bucket"
        assert prefix == ""

    def test_s3_trailing_slash(self):
        scheme, bucket, prefix = parse_cloud_uri("s3://bucket/dir/")
        assert prefix == "dir/"

    def test_az_full(self):
        scheme, bucket, prefix = parse_cloud_uri("az://container/path/to/data")
        assert scheme == "az"
        assert bucket == "container"
        assert prefix == "path/to/data"

    def test_az_no_prefix(self):
        scheme, bucket, prefix = parse_cloud_uri("az://container")
        assert scheme == "az"
        assert bucket == "container"
        assert prefix == ""

    def test_invalid_scheme(self):
        with pytest.raises(ValueError, match="Unsupported cloud URI"):
            parse_cloud_uri("gs://bucket/prefix")

    def test_local_path_raises(self):
        with pytest.raises(ValueError):
            parse_cloud_uri("/home/user/data")


class TestIsCloudUri:
    def test_s3(self):
        assert is_cloud_uri("s3://bucket/key") is True

    def test_az(self):
        assert is_cloud_uri("az://container/blob") is True

    def test_local(self):
        assert is_cloud_uri("/home/user/data") is False

    def test_relative(self):
        assert is_cloud_uri("data/files") is False


# ---------------------------------------------------------------------------
# CloudObject
# ---------------------------------------------------------------------------


class TestCloudObject:
    def test_name(self):
        obj = CloudObject(key="surveys/2024/data.grd", size=4096)
        assert obj.name == "data.grd"

    def test_suffix(self):
        obj = CloudObject(key="path/to/file.ERS")
        assert obj.suffix == ".ers"

    def test_suffix_no_ext(self):
        obj = CloudObject(key="README")
        assert obj.suffix == ""


# ---------------------------------------------------------------------------
# get_provider factory
# ---------------------------------------------------------------------------


class TestGetProvider:
    def test_s3(self):
        provider = get_provider("s3", client=MagicMock())
        assert isinstance(provider, S3StorageProvider)

    def test_az(self):
        provider = get_provider("az", client=MagicMock())
        assert isinstance(provider, AzureBlobStorageProvider)

    def test_unknown(self):
        with pytest.raises(ValueError, match="Unsupported"):
            get_provider("gcs")


# ---------------------------------------------------------------------------
# S3StorageProvider (mocked)
# ---------------------------------------------------------------------------


class TestS3StorageProvider:
    def _make_provider(self):
        client = MagicMock()
        return S3StorageProvider(client=client), client

    def test_list_objects(self):
        provider, client = self._make_provider()
        paginator = MagicMock()
        client.get_paginator.return_value = paginator
        paginator.paginate.return_value = [
            {
                "Contents": [
                    {"Key": "data/file1.grd", "Size": 1024},
                    {"Key": "data/file2.ers", "Size": 2048},
                    {"Key": "data/readme.txt", "Size": 100},
                ]
            }
        ]
        objects = provider.list_objects("bucket", "data/")
        assert len(objects) == 3
        assert objects[0].key == "data/file1.grd"
        assert objects[0].size == 1024

    def test_list_objects_with_extension_filter(self):
        provider, client = self._make_provider()
        paginator = MagicMock()
        client.get_paginator.return_value = paginator
        paginator.paginate.return_value = [
            {
                "Contents": [
                    {"Key": "data/file1.grd", "Size": 1024},
                    {"Key": "data/file2.ers", "Size": 2048},
                    {"Key": "data/readme.txt", "Size": 100},
                ]
            }
        ]
        objects = provider.list_objects("bucket", "data/", extensions={".grd"})
        assert len(objects) == 1
        assert objects[0].suffix == ".grd"

    def test_list_objects_skips_directories(self):
        provider, client = self._make_provider()
        paginator = MagicMock()
        client.get_paginator.return_value = paginator
        paginator.paginate.return_value = [
            {
                "Contents": [
                    {"Key": "data/", "Size": 0},
                    {"Key": "data/file.grd", "Size": 512},
                ]
            }
        ]
        objects = provider.list_objects("bucket", "data/")
        assert len(objects) == 1

    def test_list_objects_non_recursive(self):
        provider, client = self._make_provider()
        paginator = MagicMock()
        client.get_paginator.return_value = paginator
        paginator.paginate.return_value = [
            {
                "Contents": [
                    {"Key": "data/file.grd", "Size": 512},
                ]
            }
        ]
        provider.list_objects("bucket", "data/", recursive=False)
        call_kwargs = paginator.paginate.call_args[1]
        assert call_kwargs["Delimiter"] == "/"

    def test_download(self, tmp_path):
        provider, client = self._make_provider()
        dest = tmp_path / "downloaded.grd"
        result = provider.download("bucket", "data/file.grd", dest)
        client.download_file.assert_called_once_with("bucket", "data/file.grd", str(dest))
        assert result == dest

    def test_list_objects_empty_page(self):
        provider, client = self._make_provider()
        paginator = MagicMock()
        client.get_paginator.return_value = paginator
        paginator.paginate.return_value = [{}]
        objects = provider.list_objects("bucket", "data/")
        assert objects == []


# ---------------------------------------------------------------------------
# AzureBlobStorageProvider (mocked)
# ---------------------------------------------------------------------------


class TestAzureBlobStorageProvider:
    def _make_provider(self):
        client = MagicMock()
        return AzureBlobStorageProvider(client=client), client

    def test_list_objects(self):
        provider, client = self._make_provider()
        container_client = MagicMock()
        client.get_container_client.return_value = container_client

        blob1 = MagicMock()
        blob1.name = "data/file1.grd"
        blob1.size = 1024
        blob2 = MagicMock()
        blob2.name = "data/file2.ers"
        blob2.size = 2048

        container_client.list_blobs.return_value = [blob1, blob2]

        objects = provider.list_objects("container", "data/")
        assert len(objects) == 2

    def test_list_objects_with_extension_filter(self):
        provider, client = self._make_provider()
        container_client = MagicMock()
        client.get_container_client.return_value = container_client

        blob1 = MagicMock()
        blob1.name = "data/file1.grd"
        blob1.size = 1024
        blob2 = MagicMock()
        blob2.name = "data/file2.ers"
        blob2.size = 2048

        container_client.list_blobs.return_value = [blob1, blob2]

        objects = provider.list_objects("container", "data/", extensions={".grd"})
        assert len(objects) == 1
        assert objects[0].suffix == ".grd"

    def test_list_objects_non_recursive(self):
        provider, client = self._make_provider()
        container_client = MagicMock()
        client.get_container_client.return_value = container_client
        container_client.walk_blobs.return_value = []

        provider.list_objects("container", "data/", recursive=False)
        container_client.walk_blobs.assert_called_once()

    def test_download(self, tmp_path):
        provider, client = self._make_provider()
        container_client = MagicMock()
        blob_client = MagicMock()
        client.get_blob_client.return_value = blob_client
        download_stream = MagicMock()
        download_stream.readall.return_value = b"\x00" * 100
        blob_client.download_blob.return_value = download_stream

        dest = tmp_path / "downloaded.grd"
        result = provider.download("container", "data/file.grd", dest)
        assert result == dest
        assert dest.read_bytes() == b"\x00" * 100


# ---------------------------------------------------------------------------
# DirectoryScanner cloud integration
# ---------------------------------------------------------------------------


class TestDirectoryScannerCloud:
    """Test that DirectoryScanner integrates with cloud providers."""

    def _surfer6_bytes(self):
        """Build minimal Surfer 6 binary grid bytes."""
        nx, ny = 3, 2
        xlo, xhi = 0.0, 10.0
        ylo, yhi = 0.0, 5.0
        zlo, zhi = -1.0, 1.0
        header = b"DSBB" + struct.pack("<HH6d", nx, ny, xlo, xhi, ylo, yhi, zlo, zhi)
        values = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6]
        payload = struct.pack(f"<{len(values)}f", *values)
        return header + payload

    def test_scan_cloud_s3(self, tmp_path):
        """Scan an S3 URI using a mock provider."""
        data = self._surfer6_bytes()

        # Write a real file so scan_file works on it
        local_file = tmp_path / "sample.grd"
        local_file.write_bytes(data)

        provider = MagicMock(spec=CloudStorageProvider)
        provider.list_objects.return_value = [
            CloudObject(key="surveys/sample.grd", size=len(data)),
        ]

        def fake_download(bucket, key, dest):
            dest = Path(dest)
            dest.write_bytes(data)
            return dest

        provider.download.side_effect = fake_download

        scanner = DirectoryScanner(cloud_provider=provider)
        reports = scanner.scan_cloud("s3://my-bucket/surveys/")

        assert len(reports) == 1
        assert reports[0].path == "s3://my-bucket/surveys/sample.grd"
        assert reports[0].size == len(data)
        assert "Surfer 6 Binary Grid" in reports[0].identified_formats

    def test_scan_directory_delegates_to_cloud(self, tmp_path):
        """scan_directory with a cloud URI should delegate to scan_cloud."""
        provider = MagicMock(spec=CloudStorageProvider)
        provider.list_objects.return_value = []

        scanner = DirectoryScanner(cloud_provider=provider)
        reports = scanner.scan_directory("s3://bucket/prefix/")

        assert reports == []
        provider.list_objects.assert_called_once()

    def test_scan_cloud_empty_file_skipped(self):
        """Empty cloud objects should be flagged without download."""
        provider = MagicMock(spec=CloudStorageProvider)
        provider.list_objects.return_value = [
            CloudObject(key="empty.grd", size=0),
        ]

        scanner = DirectoryScanner(cloud_provider=provider)
        reports = scanner.scan_cloud("s3://bucket/")

        assert len(reports) == 1
        assert "Empty file" in reports[0].errors
        provider.download.assert_not_called()

    def test_scan_cloud_with_extension_filter(self):
        """Extension filter should be passed to the provider."""
        provider = MagicMock(spec=CloudStorageProvider)
        provider.list_objects.return_value = []

        scanner = DirectoryScanner(cloud_provider=provider, extensions={".grd"})
        scanner.scan_cloud("az://container/data/")

        _, kwargs = provider.list_objects.call_args
        assert kwargs["extensions"] == {".grd"}

    def test_scan_cloud_download_error(self):
        """Download errors should be caught and recorded."""
        provider = MagicMock(spec=CloudStorageProvider)
        provider.list_objects.return_value = [
            CloudObject(key="broken.grd", size=100),
        ]
        provider.download.side_effect = Exception("Network error")

        scanner = DirectoryScanner(cloud_provider=provider)
        reports = scanner.scan_cloud("s3://bucket/")

        assert len(reports) == 1
        assert any("Cloud download/analysis error" in e for e in reports[0].errors)

    def test_scan_cloud_az_uri(self, tmp_path):
        """Scan an Azure URI using a mock provider."""
        data = b"\x00" * 100

        provider = MagicMock(spec=CloudStorageProvider)
        provider.list_objects.return_value = [
            CloudObject(key="data/file.bin", size=100),
        ]

        def fake_download(bucket, key, dest):
            dest = Path(dest)
            dest.write_bytes(data)
            return dest

        provider.download.side_effect = fake_download

        scanner = DirectoryScanner(cloud_provider=provider)
        reports = scanner.scan_cloud("az://mycontainer/data/")

        assert len(reports) == 1
        assert reports[0].path == "az://mycontainer/data/file.bin"
