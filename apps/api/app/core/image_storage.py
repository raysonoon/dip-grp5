from pathlib import Path, PurePosixPath


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
