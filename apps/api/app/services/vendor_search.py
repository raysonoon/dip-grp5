from dataclasses import dataclass
import re
import unicodedata

from sqlalchemy import and_, case, func, literal, literal_column, or_
from sqlalchemy.dialects.postgresql import REGCONFIG
from sqlalchemy.orm import Session

from app.models import Vendor


_SPACE_RE = re.compile(r"\s+")
_PUNCTUATION_RE = re.compile(r"[^\w]+", flags=re.UNICODE)
_FUZZY_SIMILARITY_THRESHOLD = 0.4

_PHRASE_ALIASES = {
    "northspine": "north spine",
    "southspine": "south spine",
    "thehive": "the hive",
    "kopitiam": "food court",
    "coffeehouse": "coffee shop",
    "veggie": "vegetarian",
    "veggies": "vegetarian",
    "veg": "vegetarian",
    "canteen one": "canteen 1",
    "canteen two": "canteen 2",
    "canteen four": "canteen 4",
    "canteen nine": "canteen 9",
    "canteen eleven": "canteen 11",
    "canteen fourteen": "canteen 14",
    "canteen sixteen": "canteen 16",
}

_CATEGORY_ALIASES = {
    "western food": ("western",),
    "westernfood": ("western",),
}

_LOCATION_ALIASES = {
    "north spine": ("north spine",),
    "south spine": ("south spine",),
    "the hive": ("the hive", "hive"),
    "north hill": ("north hill",),
    "pioneer": ("pioneer",),
    "nie": ("nie",),
    "canteen 1": ("canteen 1", "canteen one"),
    "canteen 2": ("canteen 2", "food court 2"),
    "canteen 4": ("canteen 4",),
    "canteen 9": ("canteen 9",),
    "canteen 11": ("canteen 11",),
    "canteen 14": ("canteen 14",),
    "canteen 16": ("canteen 16",),
}

_FILLER_TOKENS = {
    "around",
    "at",
    "find",
    "for",
    "in",
    "me",
    "near",
    "please",
    "show",
}


@dataclass(frozen=True)
class ParsedVendorSearch:
    normalized_text: str
    lexical_text: str
    halal: bool | None = None
    vegetarian: bool | None = None
    location_terms: tuple[str, ...] = ()
    category_terms: tuple[str, ...] = ()


@dataclass(frozen=True)
class VendorSearchPlan:
    parsed: ParsedVendorSearch
    filters: tuple[object, ...]
    order_by: tuple[object, ...]


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = _PUNCTUATION_RE.sub(" ", normalized)
    return _SPACE_RE.sub(" ", normalized).strip()


def _replace_phrase(text: str, source: str, target: str) -> str:
    return re.sub(rf"(?<!\w){re.escape(source)}(?!\w)", target, text)


def _remove_phrase(text: str, phrase: str) -> str:
    return _SPACE_RE.sub(
        " ",
        re.sub(rf"(?<!\w){re.escape(phrase)}(?!\w)", " ", text),
    ).strip()


def parse_vendor_search_query(raw_query: str | None) -> ParsedVendorSearch:
    normalized = _normalize_text(raw_query or "")
    for source, target in sorted(
        _PHRASE_ALIASES.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        normalized = _replace_phrase(normalized, source, target)

    working = normalized
    halal = None
    vegetarian = None

    category_terms: tuple[str, ...] = ()
    for phrase, aliases in sorted(
        _CATEGORY_ALIASES.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        if re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", working):
            category_terms = aliases
            working = _remove_phrase(working, phrase)
            break

    if re.search(r"(?<!\w)halal(?!\w)", working):
        halal = True
        working = _remove_phrase(working, "halal")
    if re.search(r"(?<!\w)vegetarian(?!\w)", working):
        vegetarian = True
        working = _remove_phrase(working, "vegetarian")

    location_terms: tuple[str, ...] = ()
    for phrase, aliases in sorted(
        _LOCATION_ALIASES.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        if re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", working):
            location_terms = aliases
            working = _remove_phrase(working, phrase)
            break

    tokens = working.split()
    if len(tokens) > 1:
        tokens = [token for token in tokens if token not in _FILLER_TOKENS]

    return ParsedVendorSearch(
        normalized_text=normalized,
        lexical_text=" ".join(tokens),
        halal=halal,
        vegetarian=vegetarian,
        location_terms=location_terms,
        category_terms=category_terms,
    )


def _structured_filters(parsed: ParsedVendorSearch) -> list[object]:
    filters: list[object] = []
    if parsed.halal is not None:
        filters.append(Vendor.halal.is_(parsed.halal))
    if parsed.vegetarian is not None:
        filters.append(Vendor.vegetarian.is_(parsed.vegetarian))
    if parsed.category_terms:
        filters.append(
            or_(
                *(
                    Vendor.category.ilike(f"%{term}%")
                    for term in parsed.category_terms
                )
            )
        )
    if parsed.location_terms:
        location_matches = []
        for term in parsed.location_terms:
            pattern = f"%{term}%"
            location_matches.extend(
                (
                    Vendor.name.ilike(pattern),
                    Vendor.location.ilike(pattern),
                    Vendor.unit_code.ilike(pattern),
                )
            )
        filters.append(or_(*location_matches))
    return filters


def _portable_search_plan(
    parsed: ParsedVendorSearch,
    filters: list[object],
) -> VendorSearchPlan:
    if not parsed.lexical_text:
        quality = func.coalesce(
            Vendor.average_rating,
            Vendor.average_google_rating,
            0,
        )
        order_by = (quality.desc(),) if filters else ()
        return VendorSearchPlan(parsed, tuple(filters), order_by)

    fields = (
        Vendor.name,
        Vendor.category,
        Vendor.location,
        Vendor.unit_code,
    )
    for token in parsed.lexical_text.split():
        pattern = f"%{token}%"
        filters.append(or_(*(field.ilike(pattern) for field in fields)))

    normalized_name = func.lower(func.trim(Vendor.name))
    exact_name = case(
        (normalized_name == parsed.lexical_text, 1),
        else_=0,
    )
    prefix_name = case(
        (normalized_name.like(f"{parsed.lexical_text}%"), 1),
        else_=0,
    )
    return VendorSearchPlan(
        parsed,
        tuple(filters),
        (exact_name.desc(), prefix_name.desc()),
    )


def build_vendor_search_plan(
    session: Session,
    raw_query: str | None,
) -> VendorSearchPlan:
    parsed = parse_vendor_search_query(raw_query)
    filters = _structured_filters(parsed)
    bind = session.get_bind()
    if bind.dialect.name != "postgresql":
        return _portable_search_plan(parsed, filters)

    if not parsed.lexical_text:
        return _portable_search_plan(parsed, filters)

    config = literal_column("'simple'").cast(REGCONFIG)
    ts_query = func.websearch_to_tsquery(config, parsed.lexical_text)
    document_vector = func.to_tsvector(config, Vendor.search_document)
    name_vector = func.to_tsvector(
        config,
        func.coalesce(Vendor.name, ""),
    )
    category_vector = func.to_tsvector(
        config,
        func.coalesce(Vendor.category, ""),
    )
    location_vector = func.to_tsvector(
        config,
        func.coalesce(Vendor.location, ""),
    )
    fuzzy_document = func.lower(
        func.trim(
            func.concat_ws(
                " ",
                func.coalesce(Vendor.name, ""),
                func.coalesce(Vendor.category, ""),
            )
        )
    )

    normalized_name = func.lower(func.trim(Vendor.name))
    exact_name = case(
        (normalized_name == parsed.lexical_text, 1.0),
        else_=0.0,
    )
    prefix_name = case(
        (normalized_name.like(f"{parsed.lexical_text}%"), 1.0),
        else_=0.0,
    )
    fuzzy_score = func.greatest(
        func.similarity(normalized_name, parsed.lexical_text),
        func.word_similarity(
            literal(parsed.lexical_text),
            fuzzy_document,
        ),
    )
    full_text_match = document_vector.op("@@")(ts_query)
    fuzzy_match = and_(
        *(
            func.word_similarity(
                literal(token),
                fuzzy_document,
            )
            >= _FUZZY_SIMILARITY_THRESHOLD
            for token in parsed.lexical_text.split()
        )
    )
    filters.append(
        or_(
            exact_name == 1.0,
            prefix_name == 1.0,
            full_text_match,
            fuzzy_match,
        )
    )

    search_score = (
        exact_name * 100.0
        + prefix_name * 40.0
        + func.ts_rank_cd(name_vector, ts_query) * 24.0
        + func.ts_rank_cd(category_vector, ts_query) * 12.0
        + func.ts_rank_cd(location_vector, ts_query) * 6.0
        + func.ts_rank_cd(document_vector, ts_query) * 2.0
        + fuzzy_score * 15.0
    )
    quality = func.coalesce(
        Vendor.average_rating,
        Vendor.average_google_rating,
        0,
    )
    return VendorSearchPlan(
        parsed,
        tuple(filters),
        (search_score.desc(), quality.desc()),
    )
