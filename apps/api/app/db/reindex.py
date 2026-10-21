import argparse

from app.core.config import settings
from app.db.session import SessionLocal
from app.services.embedding import GoogleEmbedder
from app.services.ingest import reindex, reindex_vendor_embeddings


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reindex internal, Google, and Reddit chunks into knowledge_chunks"
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
    parser.add_argument(
        "--source-type",
        type=str,
        default=None,
        help="Only reindex one source type, e.g. reddit.",
    )
    parser.add_argument(
        "--target",
        choices=("vendors", "knowledge-chunks"),
        default=None,
        help=(
            "Choose what to reindex: vendors or knowledge-chunks. "
            "If omitted, reindex both."
        ),
    )
    args = parser.parse_args()

    api_key = (
        settings.gemini_api_key.get_secret_value()
        if settings.gemini_api_key is not None
        else None
    )
    if not api_key:
        print(
            "Knowledge base reindex skipped: GEMINI_API_KEY is not configured"
        )
        return

    embedder = GoogleEmbedder(api_key=api_key)

    with SessionLocal() as session:
        reindex_knowledge = args.target in (None, "knowledge-chunks")

        if reindex_knowledge:
            embedded, already_indexed = reindex(
                session,
                embedder,
                force=args.force,
                limit=args.limit,
                source_type=args.source_type,
            )
        reindex_vendors = args.target in (None, "vendors")
        
        if reindex_vendors:
            vendor_embedded, vendor_already_indexed = reindex_vendor_embeddings(
                session,
                embedder,
                force=args.force,
                limit=args.limit,
            )

    if reindex_knowledge:
        print(
            "Knowledge base reindex: "
            f"embedded={embedded}, already_indexed={already_indexed}"
            + ("" if args.limit is None else f" (limit={args.limit})")
            + (" (force)" if args.force else "")
        )

    if reindex_vendors:
        print(
            "Vendor reindex: "
            f"embedded={vendor_embedded}, "
            f"already_indexed={vendor_already_indexed}"
            + ("" if args.limit is None else f" (limit={args.limit})")
            + (" (force)" if args.force else "")
        )


if __name__ == "__main__":
    main()
