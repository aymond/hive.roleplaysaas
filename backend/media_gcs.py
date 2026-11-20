from __future__ import annotations

import os
from pathlib import Path

from .logger import logger

GCS_MEDIA_BUCKET = os.getenv("GCS_MEDIA_BUCKET", "").strip()


def is_gcs_enabled() -> bool:
    return bool(os.getenv("GCS_MEDIA_BUCKET", "").strip())


def upload_media_pair(
    uid: str,
    filename: str,
    png_bytes: bytes,
    meta_filename: str,
    meta_bytes: bytes,
) -> tuple[str, str] | None:
    """
    Uploads a generated PNG and its JSON metadata sidecar to the private GCS bucket
    under `users/{uid}/generated/...` and returns authenticated `/api/media/...` URLs.
    """
    bucket_name = os.getenv("GCS_MEDIA_BUCKET", "").strip()
    if not bucket_name:
        return None
    try:
        from google.cloud import storage as gcs  # type: ignore[import-not-found]

        client = gcs.Client()
        bucket = client.bucket(bucket_name)

        safe_name = Path(filename).name
        safe_meta = Path(meta_filename).name
        png_blob = bucket.blob(f"users/{uid}/generated/{safe_name}")
        png_blob.upload_from_string(png_bytes, content_type="image/png")

        meta_blob = bucket.blob(f"users/{uid}/generated/{safe_meta}")
        meta_blob.upload_from_string(meta_bytes, content_type="application/json")

        return f"/api/media/{safe_name}", f"/api/media/{safe_meta}"
    except Exception as exc:
        logger.warning("⚠️ GCS      | Failed to upload media for uid=%s: %s", uid, exc)
        return None


def download_user_media(uid: str, filename: str) -> tuple[bytes, str] | None:
    """
    Downloads a user-scoped object `users/{uid}/generated/{filename}` from the private GCS bucket.
    """
    bucket_name = os.getenv("GCS_MEDIA_BUCKET", "").strip()
    if not bucket_name:
        return None
    safe_name = Path(filename).name
    if not safe_name or safe_name != filename:
        return None
    try:
        from google.cloud import storage as gcs  # type: ignore[import-not-found]

        client = gcs.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(f"users/{uid}/generated/{safe_name}")
        if not blob.exists():
            return None
        content_type = "application/json" if safe_name.endswith(".json") else "image/png"
        return blob.download_as_bytes(), content_type
    except Exception as exc:
        logger.warning("⚠️ GCS      | Failed to download %s for uid=%s: %s", safe_name, uid, exc)
        return None


def delete_user_media_prefix(uid: str) -> int:
    """Deletes all GCS media objects under `users/{uid}/` (Art. 17 DSGVO erasure)."""
    bucket_name = os.getenv("GCS_MEDIA_BUCKET", "").strip()
    if not bucket_name or not uid:
        return 0
    try:
        from google.cloud import storage as gcs  # type: ignore[import-not-found]

        client = gcs.Client()
        bucket = client.bucket(bucket_name)
        deleted = 0
        for blob in bucket.list_blobs(prefix=f"users/{uid}/"):
            blob.delete()
            deleted += 1
        return deleted
    except Exception as exc:
        logger.warning("⚠️ GCS      | Failed to purge media for uid=%s: %s", uid, exc)
        return 0
