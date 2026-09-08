from pathlib import Path, PurePosixPath
from typing import Protocol


UPLOADS_ROOT = Path(__file__).resolve().parents[2] / "uploads"
IMAGE_MEDIA_TYPES = {
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".png": "image/png",
}


def resolve_image_path(
    relative_url: str,
    *,
    collection: str,
    owner_id: int,
) -> tuple[Path, str]:
    """Resolve one stored media URL inside its owner-specific upload folder."""
    expected_prefix = f"/media/{collection}/{owner_id}/"
    if "\\" in relative_url or not relative_url.startswith(expected_prefix):
        raise ValueError("image URL is outside the expected media folder")

    filename = relative_url.removeprefix(expected_prefix)
    relative_filename = PurePosixPath(filename)
    if (
        not filename
        or len(relative_filename.parts) != 1
        or filename in {".", ".."}
    ):
        raise ValueError("image URL must identify one file")

    media_type = IMAGE_MEDIA_TYPES.get(relative_filename.suffix.casefold())
    if media_type is None:
        raise ValueError("unsupported image file type")

    owner_directory = (UPLOADS_ROOT / collection / str(owner_id)).resolve()
    image_path = (owner_directory / filename).resolve()
    if image_path.parent != owner_directory:
        raise ValueError("image URL escapes the expected media folder")

    return image_path, media_type


class StorageBackend(Protocol):
    """Backend-agnostic media storage.

    ``reference`` is the stable ``image_url`` value stored on the image row.
    Phase 2 swaps ``LocalStorage`` for an R2/S3 implementation behind this
    protocol without changing call sites.
    """

    def resolve(
        self,
        reference: str,
        *,
        collection: str,
        owner_id: int,
    ) -> tuple[Path, str]:
        """Resolve a stored reference to a local path and media type."""
        ...

    def save(
        self,
        *,
        collection: str,
        owner_id: int,
        reference: str,
        data: bytes,
    ) -> None:
        """Persist ``data`` at ``reference``."""
        ...

    def delete(
        self,
        *,
        collection: str,
        owner_id: int,
        reference: str,
    ) -> None:
        """Remove the stored object at ``reference`` if it exists."""
        ...


class LocalStorage:
    """Default filesystem-backed storage under ``UPLOADS_ROOT``."""

    def resolve(
        self,
        reference: str,
        *,
        collection: str,
        owner_id: int,
    ) -> tuple[Path, str]:
        return resolve_image_path(
            reference,
            collection=collection,
            owner_id=owner_id,
        )

    def save(
        self,
        *,
        collection: str,
        owner_id: int,
        reference: str,
        data: bytes,
    ) -> None:
        path, _ = self.resolve(
            collection=collection,
            owner_id=owner_id,
            reference=reference,
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def delete(
        self,
        *,
        collection: str,
        owner_id: int,
        reference: str,
    ) -> None:
        path, _ = self.resolve(
            collection=collection,
            owner_id=owner_id,
            reference=reference,
        )
        path.unlink(missing_ok=True)
        try:
            path.parent.rmdir()
        except OSError:
            pass


_local_storage = LocalStorage()


def get_storage() -> StorageBackend:
    return _local_storage