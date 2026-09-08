from fastapi import HTTPException, UploadFile, status


MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024


def detect_image_type(contents: bytes) -> tuple[str, str] | None:
    """Detect JPEG/PNG by magic bytes; return ``(mime_type, extension)``."""
    if contents.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", ".jpg"
    if contents.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", ".png"
    return None


async def read_image_upload(file: UploadFile) -> tuple[bytes, str, str]:
    """Read and validate an uploaded image, returning its bytes and type."""
    try:
        contents = await file.read(MAX_IMAGE_SIZE_BYTES + 1)
    finally:
        await file.close()

    if not contents:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Image file cannot be empty",
        )
    if len(contents) > MAX_IMAGE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Image file must not exceed 5 MB",
        )

    detected_type = detect_image_type(contents)
    if detected_type is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only JPEG and PNG images are supported",
        )
    mime_type, extension = detected_type
    if file.content_type not in {mime_type, "application/octet-stream"}:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Uploaded content does not match its media type",
        )
    return contents, mime_type, extension