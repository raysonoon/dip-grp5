import argparse

from app.core.config import settings
from app.db.session import SessionLocal
from app.services.embedding import GoogleEmbedder
from app.services.ingest import reindex


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reindex internal and Google reviews into knowledge_chunks"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help=(
            "Maximum number of documents to embed this run. Use a small value "
            "to stay within the free-tier embed quota and resume later."
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-embed already-indexed chunks (default is to skip them).",
    )
    args = parser.parse_args()

    api_key = (
        settings.gemini_api_key.get_secret_value()
        if settings.gemini_api_key is not None
        else None
    )
    embedder = GoogleEmbedder(api_key=api_key)

    with SessionLocal() as session:
        embedded, already_indexed = reindex(
            session,
            embedder,
            force=args.force,
            limit=args.limit,
        )

    print(
        "Knowledge base reindex: "
        f"embedded={embedded}, already_indexed={already_indexed}"
        + ("" if args.limit is None else f" (limit={args.limit})")
        + (" (force)" if args.force else "")
    )


if __name__ == "__main__":
    main()