"""File storage for uploads (NID photos, agreements, avatars, ...). STORAGE_BACKEND selects the backend:

  local (default)  files under UPLOAD_DIR, exactly as before
  s3               any S3-compatible service (AWS S3, Cloudflare R2, MinIO, Backblaze B2...): private bucket, optional server-side encryption,
                   downloads through our authenticated endpoints, by streaming (default) or a short-lived presigned URL redirect

Keys are relative paths like "agencies/3/ab12.pdf". Callers never build filesystem paths themselves.

S3 env: S3_BUCKET, S3_ENDPOINT_URL (empty for AWS), S3_REGION (auto for R2), S3_ACCESS_KEY_ID, S3_SECRET_ACCESS_KEY, S3_PREFIX (optional),
S3_SSE (AES256 | aws:kms | empty), S3_SSE_KMS_KEY_ID, S3_ADDRESSING=path|virtual, STORAGE_DOWNLOAD=proxy|redirect, S3_URL_TTL=60 (seconds).
boto3 is imported only when the s3 backend is used (pip install boto3).
"""
from __future__ import annotations

import io
import mimetypes
import os
import threading
from abc import ABC, abstractmethod
from pathlib import Path, PurePosixPath

from fastapi import HTTPException
from fastapi.responses import FileResponse, RedirectResponse, Response

from .. import config


def clean_key(key: str) -> str:
    p = PurePosixPath(str(key).replace("\\", "/"))
    if not key or p.is_absolute() or ".." in p.parts or str(p) in (".", ""):
        raise ValueError("Bad storage key")
    return str(p)


class Storage(ABC):
    name = ""

    @abstractmethod
    def put(self, key: str, data: bytes, content_type: str = "") -> None: ...

    @abstractmethod
    def get(self, key: str) -> bytes:
        """Raises FileNotFoundError."""

    @abstractmethod
    def exists(self, key: str) -> bool: ...

    @abstractmethod
    def delete(self, key: str) -> None:
        """Missing files are fine."""

    @abstractmethod
    def serve(self, key: str, media_type: str, filename: str | None = None, headers: dict | None = None) -> Response:
        """The HTTP response for a download. Call only after the caller's own permission checks. 404 when the file is missing."""

    def iter_keys(self, prefix: str = "") -> list[str]:
        return []


class LocalStorage(Storage):
    name = "local"

    def __init__(self, root: Path):
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        return self.root / clean_key(key)

    def put(self, key, data, content_type=""):
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def get(self, key):
        p = self._path(key)
        if not p.is_file():
            raise FileNotFoundError(key)
        return p.read_bytes()

    def exists(self, key):
        return self._path(key).is_file()

    def delete(self, key):
        self._path(key).unlink(missing_ok=True)

    def serve(self, key, media_type, filename=None, headers=None):
        p = self._path(key)
        if not p.is_file():
            raise HTTPException(404, "Not found")
        return FileResponse(p, media_type=media_type, filename=filename, headers=headers)

    def iter_keys(self, prefix=""):
        if not self.root.exists():
            return []
        return sorted(str(f.relative_to(self.root).as_posix()) for f in self.root.rglob("*") if f.is_file() and f.relative_to(self.root).as_posix().startswith(prefix))


class S3Storage(Storage):
    name = "s3"

    def __init__(self, bucket: str, client=None, prefix: str = "", sse: str = "", sse_kms_key_id: str = "", download: str = "proxy", url_ttl: int = 60):
        if not bucket:
            raise RuntimeError("S3_BUCKET is not set")
        self.bucket, self.prefix, self.sse, self.kms, self.download, self.ttl = bucket, prefix.strip("/"), sse, sse_kms_key_id, download, url_ttl
        self.client = client or self._make_client()

    @staticmethod
    def _make_client():
        try:
            import boto3
            from botocore.config import Config
        except ImportError as e:
            raise RuntimeError("STORAGE_BACKEND=s3 needs boto3 (pip install boto3)") from e
        e = os.getenv
        return boto3.client("s3", endpoint_url=e("S3_ENDPOINT_URL") or None, region_name=e("S3_REGION") or None,
                            aws_access_key_id=e("S3_ACCESS_KEY_ID") or None, aws_secret_access_key=e("S3_SECRET_ACCESS_KEY") or None,
                            config=Config(signature_version="s3v4", s3={"addressing_style": e("S3_ADDRESSING", "path")}, retries={"max_attempts": 4, "mode": "standard"},
                                          connect_timeout=5, read_timeout=30))

    def _k(self, key: str) -> str:
        k = clean_key(key)
        return f"{self.prefix}/{k}" if self.prefix else k

    @staticmethod
    def _missing(e: Exception) -> bool:
        code = str(getattr(e, "response", {}).get("Error", {}).get("Code", ""))
        return code in ("404", "NoSuchKey", "NotFound")

    def put(self, key, data, content_type=""):
        args = {"Bucket": self.bucket, "Key": self._k(key), "Body": data, "ContentType": content_type or mimetypes.guess_type(key)[0] or "application/octet-stream"}
        if self.sse:
            args["ServerSideEncryption"] = self.sse
            if self.sse == "aws:kms" and self.kms:
                args["SSEKMSKeyId"] = self.kms
        self.client.put_object(**args)

    def get(self, key):
        try:
            return self.client.get_object(Bucket=self.bucket, Key=self._k(key))["Body"].read()
        except Exception as e:
            if self._missing(e):
                raise FileNotFoundError(key) from None
            raise

    def exists(self, key):
        try:
            self.client.head_object(Bucket=self.bucket, Key=self._k(key))
            return True
        except Exception as e:
            if self._missing(e):
                return False
            raise

    def delete(self, key):
        self.client.delete_object(Bucket=self.bucket, Key=self._k(key))

    def presigned_url(self, key: str, media_type: str = "", filename: str | None = None, ttl: int | None = None) -> str:
        params = {"Bucket": self.bucket, "Key": self._k(key)}
        if media_type:
            params["ResponseContentType"] = media_type
        if filename:
            params["ResponseContentDisposition"] = 'attachment; filename="%s"' % filename.replace('"', "")
        return self.client.generate_presigned_url("get_object", Params=params, ExpiresIn=ttl or self.ttl)

    def serve(self, key, media_type, filename=None, headers=None):
        if not self.exists(key):
            raise HTTPException(404, "Not found")
        if self.download == "redirect":
            return RedirectResponse(self.presigned_url(key, media_type, filename), status_code=302, headers={"Cache-Control": "no-store", **(headers or {})})
        h = dict(headers or {})
        if filename:
            h["Content-Disposition"] = 'attachment; filename="%s"' % filename.replace('"', "")
        return Response(self.get(key), media_type=media_type, headers=h)

    def iter_keys(self, prefix=""):
        out, token = [], None
        full = self._k(prefix) if prefix else self.prefix
        while True:
            r = self.client.list_objects_v2(Bucket=self.bucket, Prefix=full, **({"ContinuationToken": token} if token else {}))
            out += [o["Key"][len(self.prefix) + 1:] if self.prefix else o["Key"] for o in r.get("Contents", [])]
            if not r.get("IsTruncated"):
                return sorted(out)
            token = r["NextContinuationToken"]


_cache: dict = {}
_lock = threading.Lock()
OVERRIDE: Storage | None = None   # tests may set this


def get_storage() -> Storage:
    if OVERRIDE is not None:
        return OVERRIDE
    kind = os.getenv("STORAGE_BACKEND", "local").strip().lower()
    sig = (kind, str(config.UPLOAD_DIR), os.getenv("S3_BUCKET"), os.getenv("S3_ENDPOINT_URL"), os.getenv("S3_PREFIX"))
    with _lock:
        if _cache.get("sig") != sig:
            if kind == "s3":
                e = os.getenv
                _cache["obj"] = S3Storage(e("S3_BUCKET", ""), prefix=e("S3_PREFIX", ""), sse=e("S3_SSE", ""), sse_kms_key_id=e("S3_SSE_KMS_KEY_ID", ""),
                                          download=e("STORAGE_DOWNLOAD", "proxy"), url_ttl=int(e("S3_URL_TTL", "60")))
            elif kind == "local":
                _cache["obj"] = LocalStorage(config.UPLOAD_DIR)
            else:
                raise RuntimeError(f"Unknown STORAGE_BACKEND '{kind}'")
            _cache["sig"] = sig
        return _cache["obj"]
