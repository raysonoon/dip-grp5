class TextChunker:
    """Splits source text into retrievable chunks.

    Review text is short, so it is kept as a single chunk. Longer external
    content (e.g. Reddit posts) can later be split by overriding ``chunk``.
    """

    def chunk(self, text: str) -> list[str]:
        normalized = text.strip()
        if not normalized:
            return []
        return [normalized]