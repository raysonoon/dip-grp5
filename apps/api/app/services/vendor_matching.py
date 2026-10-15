"""Pure helpers for resolving vendor names in chatbot and seed text.

The functions in this module deliberately accept ``(id, name)`` tuples rather
than ORM objects.  This keeps the matching rules reusable by request handling,
database seeds, and unit tests without coupling them to SQLAlchemy.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from difflib import SequenceMatcher
from functools import lru_cache
import re
import unicodedata


VendorEntry = tuple[int, str]


# Common names students use that differ from the official vendor names stored
# in the database.  Keep the values as official names so callers always receive
# the database-facing name rather than the spelling used in a question.
VENDOR_ALIASES: Mapping[str, str] = {
    # Individual vendors
    "hot hideout": "A Hot Hideout",
    "pasta express": "Pasta Express",
    "soup spoon": "The Soup Spoon Union",
    "connect 71": "Connect 71 Cafe (C71)",
    "connect71": "Connect 71 Cafe (C71)",
    "connect cafe": "Connect 71 Cafe (C71)",
    "mad roasters": "Mad Roaster at SHHK",
    "mad roaster": "Mad Roaster at SHHK",
    "thai dynasty": "Thai Dynasty Express",
    "encik tan": "Encik Tan",
    "qq rice": "QQ Rice",
    "mr bean": "Mr Bean",
    "subway": "Subway",
    "popeyes": "Popeyes",
    "boost juice": "Boost Juice Bars",
    "gelare": "Geláre",
    "ananda taj": "Ananda's TAJ Restaurant",
    "anandas taj": "Ananda's TAJ Restaurant",
    "bismillah": "Bismillah Biryani",
    "paiks bibim": "Paik's Bibim",
    "blue ocean": "Blue Ocean Kopi & Toast",
    "coffee faculty": "Coffee Faculty",
    "junes breathe cafe": "June's Breathe Cafe\n@ LKC Medicine",
    "june breathe cafe": "June's Breathe Cafe\n@ LKC Medicine",
    "wok express": "Wok Express",
    # Common NTU food court names
    "koufu": "North Spine Food Court & International Food Court (Koufu)",
    "north spine food court": (
        "North Spine Food Court & International Food Court (Koufu)"
    ),
    "nie canteen": "Food Court @ NIE",
    "nie food court": "Food Court @ NIE",
    "quad cafe": "Quad Cafe (SBS)",
    "south spine": "South Spine Food Court (Foodies' Clan)",
    "north hill canteen": "North Hill Food Court (Colour Box)",
    "north hill food court": "North Hill Food Court (Colour Box)",
    # Canteen shorthand commonly used on Reddit
    "canteen 1": "Food Court 1",
    "can 1": "Food Court 1",
    "canteen 2": "Food Court 2",
    "can 2": "Food Court 2",
    "canteen 4": "Food Court 4",
    "can 4": "Food Court 4",
    "canteen 9": "Food Court 9",
    "can 9": "Food Court 9",
    "canteen 11": "Food Court 11",
    "can 11": "Food Court 11",
    "canteen 14": "Food Court 14",
    "can 14": "Food Court 14",
    "canteen 16": "Food Court 16",
    "can 16": "Food Court 16",
    "north hill fc": "North Hill Food Court (Colour Box)",
    "hall 14": "Food Court 14",
    "hall 11": "Food Court 11",
    "tama": "Nanyang Crescent Food Court",
    "tama canteen": "Nanyang Crescent Food Court",
    "north hill": "North Hill Food Court (Colour Box)",
    # Crespion is commonly used to refer to the Hall 4 food court.
    "crespion": "Food Court 4",
}

# These seed-oriented shorthands are also common location phrases (or easy
# typing mistakes such as "can 1").  Using them for live chat would turn a
# location constraint into an unintended vendor constraint.  The Reddit seed
# still opts into the complete mapping explicitly.
_CHAT_AMBIGUOUS_ALIASES = {
    "north spine food court",
    "nie canteen",
    "nie food court",
    "south spine",
    "north hill canteen",
    "north hill food court",
    "north hill fc",
    "north hill",
    "hall 14",
    "hall 11",
    "canteen 1",
    "canteen 2",
    "canteen 4",
    "canteen 9",
    "canteen 11",
    "canteen 14",
    "canteen 16",
    "can 1",
    "can 2",
    "can 4",
    "can 9",
    "can 11",
    "can 14",
    "can 16",
    "tama",
    "tama canteen",
    "crespion",
}
CHAT_VENDOR_ALIASES: Mapping[str, str] = {
    alias: official_name
    for alias, official_name in VENDOR_ALIASES.items()
    if alias not in _CHAT_AMBIGUOUS_ALIASES
}


_NON_ALPHANUMERIC_RE = re.compile(r"[^a-z0-9]+")
_PARENTHETICAL_RE = re.compile(r"\s*\([^)]*\)")
_LEADING_ARTICLE_RE = re.compile(r"^(?:a|the)\s+")
_CAMPUS_SUFFIX_RES = (
    # Directory and Google names commonly append a campus/location label even
    # though students use only the brand name in chat.
    re.compile(r"\s*@\s*.+$", re.IGNORECASE),
    re.compile(r"\s+at\s+.+$", re.IGNORECASE),
    re.compile(
        r"\s*[-\u2010-\u2015]\s*(?:ntu|nanyang\s+technological\s+university)"
        r"\b.*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"\s+(?:ntu|nanyang\s+technological\s+university)\b.*$",
        re.IGNORECASE,
    ),
)
_GENERIC_DERIVED_VENDOR_FORMS = {
    "cafe",
    "canteen",
    "eat",
    "food court",
    "restaurant",
    "shop",
    "stall",
    "vendor",
}
_APOSTROPHE_CHARACTERS = frozenset(
    "'`\u00b4\u02bb\u02bc\u2018\u2019\u201b\u2032\uff07"
)


def normalize_vendor_text(value: str) -> str:
    """Return a stable ASCII form used by every vendor matching path."""

    # Apostrophes are optional in common merchant spellings (``McDonald's`` /
    # ``McDonalds``), so fold rather than separate them.  Other non-ASCII
    # punctuation must become a separator before ASCII conversion; simply
    # dropping an em dash or ideographic comma would concatenate adjacent
    # vendor names into an unmatchable token.
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    folded: list[str] = []
    for character in decomposed:
        if character in _APOSTROPHE_CHARACTERS:
            continue
        if character.isascii():
            folded.append(character)
        elif unicodedata.category(character).startswith("M"):
            # The ASCII base character from an accented letter has already
            # been appended; discard only its combining mark.
            continue
        else:
            # Unicode dashes, CJK punctuation/words, emoji, and unsupported
            # non-ASCII letters separate rather than join ASCII name tokens.
            folded.append(" ")

    normalized = "".join(folded)
    normalized = _NON_ALPHANUMERIC_RE.sub(" ", normalized)
    return " ".join(normalized.split())


def _vendor_name_forms(name: str) -> tuple[str, ...]:
    """Build official and safe everyday forms for a database vendor name.

    The source directory contains names such as ``Starbucks - NTU`` and
    ``AcaiGuru @ NTU``.  Those location suffixes are presentation metadata,
    not part of the brand users normally type.  Deriving the short form here
    gives every database vendor the same behaviour instead of requiring one
    hard-coded alias per merchant.
    """

    raw_forms: list[tuple[str, bool]] = [
        (name, False),
        (_PARENTHETICAL_RE.sub(" ", name), False),
    ]
    for raw_form, _ in tuple(raw_forms):
        for suffix_re in _CAMPUS_SUFFIX_RES:
            shortened = suffix_re.sub("", raw_form).strip()
            if shortened and shortened != raw_form.strip():
                raw_forms.append((shortened, True))

    forms: list[str] = []

    for raw_form, derived in raw_forms:
        normalized = normalize_vendor_text(raw_form)
        if derived and normalized in _GENERIC_DERIVED_VENDOR_FORMS:
            continue
        if normalized and normalized not in forms:
            forms.append(normalized)

        # Users vary between ``Connect71`` and ``Connect 71`` (and similarly
        # ``7TEA``/``7 TEA``).  Fold only letter/number boundaries rather than
        # all whitespace so unrelated multi-word brands cannot collide.
        compact_alphanumeric = re.sub(
            r"(?<=[a-z])\s+(?=\d)|(?<=\d)\s+(?=[a-z])",
            "",
            normalized,
        )
        if compact_alphanumeric and compact_alphanumeric not in forms:
            forms.append(compact_alphanumeric)

        article_free = _LEADING_ARTICLE_RE.sub("", normalized)
        if article_free and article_free not in forms:
            forms.append(article_free)

    return tuple(forms)


def vendor_brand_key(name: str) -> str:
    """Return the shared brand form used to group branch-labelled rows.

    Vendor directory rows can distinguish branches in a parenthetical or NTU
    location suffix even though a clarification presents them as one brand.
    The shortest safe form already derived for mention matching removes those
    suffixes (and a leading article) consistently.  Using that same form here
    prevents confirmation logic from inventing a second notion of identity.
    """

    forms = _vendor_name_forms(name)
    return min(forms, key=lambda form: (len(form), form)) if forms else ""


def _prepare_vendors(vendors: Iterable[VendorEntry]) -> list[VendorEntry]:
    prepared: list[VendorEntry] = []
    seen_ids: set[int] = set()

    for vendor_id, vendor_name in vendors:
        name = vendor_name.strip()
        if vendor_id in seen_ids or not normalize_vendor_text(name):
            continue
        prepared.append((vendor_id, name))
        seen_ids.add(vendor_id)

    return prepared


def _add_alias_target(
    index: dict[str, dict[int, VendorEntry]],
    alias: str,
    vendor: VendorEntry,
) -> None:
    normalized_alias = normalize_vendor_text(alias)
    if not normalized_alias:
        return
    index.setdefault(normalized_alias, {})[vendor[0]] = vendor


def _find_alias_targets(
    official_name: str,
    vendors: list[VendorEntry],
) -> list[VendorEntry]:
    target = normalize_vendor_text(official_name)
    exact = [
        vendor
        for vendor in vendors
        if target == normalize_vendor_text(vendor[1])
    ]
    if exact:
        return exact

    target_forms = set(_vendor_name_forms(official_name))
    equivalent = [
        vendor
        for vendor in vendors
        if target_forms.intersection(_vendor_name_forms(vendor[1]))
    ]
    if equivalent:
        return equivalent

    # Preserve the old seed's tolerance for a slightly extended DB name.  Use
    # all derived forms so aliases survive harmless directory renames such as
    # ``Boost Juice Bars`` -> ``Boost Juice @ NTU North Spine Plaza``.
    contained = [
        vendor
        for vendor in vendors
        if any(
            target_form in vendor_form or vendor_form in target_form
            for target_form in target_forms
            for vendor_form in _vendor_name_forms(vendor[1])
        )
    ]
    return contained if len(contained) == 1 else []


def _build_alias_index(
    vendors: list[VendorEntry],
    aliases: Mapping[str, str],
) -> dict[str, tuple[VendorEntry, ...]]:
    index: dict[str, dict[int, VendorEntry]] = {}

    for vendor in vendors:
        for form in _vendor_name_forms(vendor[1]):
            _add_alias_target(index, form, vendor)

    for alias, official_name in aliases.items():
        for vendor in _find_alias_targets(official_name, vendors):
            _add_alias_target(index, alias, vendor)

    return {
        alias: tuple(targets.values())
        for alias, targets in index.items()
    }


@lru_cache(maxsize=32)
def _build_default_alias_index(
    vendors: tuple[VendorEntry, ...],
) -> dict[str, tuple[VendorEntry, ...]]:
    return _build_alias_index(list(vendors), CHAT_VENDOR_ALIASES)


def _get_alias_index(
    vendors: list[VendorEntry],
    aliases: Mapping[str, str],
) -> dict[str, tuple[VendorEntry, ...]]:
    if aliases is CHAT_VENDOR_ALIASES:
        return _build_default_alias_index(tuple(vendors))
    return _build_alias_index(vendors, aliases)


def match_vendor_mentions(
    text: str,
    vendors: Iterable[VendorEntry],
    *,
    aliases: Mapping[str, str] = CHAT_VENDOR_ALIASES,
) -> list[VendorEntry]:
    """Return recognized vendors in their order of mention.

    Exact official names, names without parenthetical suffixes, names without a
    leading ``A``/``The``, safe location-suffix-free forms, and the supplied
    aliases are all recognized.  Live chat uses :data:`CHAT_VENDOR_ALIASES` by
    default so location-like seed shorthands do not become unintended vendor
    filters.  One mention may intentionally resolve to multiple database rows
    when a brand has more than one branch.
    """

    normalized_text = normalize_vendor_text(text)
    if not normalized_text:
        return []

    prepared = _prepare_vendors(vendors)
    alias_index = _get_alias_index(prepared, aliases)
    matches: dict[int, tuple[int, int, VendorEntry]] = {}

    # Longer aliases win a same-position tie.  This matters for forms such as
    # "tama canteen"/"tama", while final output still follows the user text.
    for alias in sorted(alias_index, key=len, reverse=True):
        targets = alias_index[alias]
        if not targets:
            continue

        pattern = rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])"
        mention = re.search(pattern, normalized_text)
        if mention is None:
            continue

        for vendor in targets:
            candidate = (mention.start(), -len(alias), vendor)
            current = matches.get(vendor[0])
            if current is None or candidate[:2] < current[:2]:
                matches[vendor[0]] = candidate

    return [
        match[2]
        for match in sorted(
            matches.values(),
            key=lambda item: (item[0], item[1], item[2][0]),
        )
    ]


def _coerce_names(names: str | Iterable[str]) -> list[str]:
    values = [names] if isinstance(names, str) else list(names)
    return [
        value.strip()
        for value in values
        if isinstance(value, str) and value.strip()
    ]


def resolve_vendor_names(
    names: str | Iterable[str],
    vendors: Iterable[VendorEntry],
    *,
    aliases: Mapping[str, str] = CHAT_VENDOR_ALIASES,
) -> tuple[list[VendorEntry], list[str]]:
    """Resolve LLM-produced vendor names and return unresolved inputs too."""

    prepared = _prepare_vendors(vendors)
    alias_index = _get_alias_index(prepared, aliases)
    matches: list[VendorEntry] = []
    unresolved: list[str] = []
    matched_ids: set[int] = set()
    unresolved_keys: set[str] = set()

    for raw_name in _coerce_names(names):
        normalized_name = normalize_vendor_text(raw_name)
        name_matches = list(alias_index.get(normalized_name, ()))

        if not name_matches:
            # LLMs sometimes return a small phrase (for example, "Popeyes at
            # NTU") rather than only the requested name.  A brand mention can
            # legitimately identify multiple branch rows.
            mentioned = match_vendor_mentions(
                raw_name,
                prepared,
                aliases=aliases,
            )
            if len(mentioned) == 1:
                name_matches = mentioned
            elif len(mentioned) > 1:
                name_matches = mentioned

        if name_matches:
            for vendor in name_matches:
                if vendor[0] not in matched_ids:
                    matches.append(vendor)
                    matched_ids.add(vendor[0])
            continue

        if normalized_name not in unresolved_keys:
            unresolved.append(raw_name)
            unresolved_keys.add(normalized_name)

    return matches, unresolved


def _suggestion_threshold(normalized_name: str) -> float:
    compact_length = len(normalized_name.replace(" ", ""))
    if compact_length <= 4:
        # One substituted character in a four-character brand (``7 Tee`` /
        # ``7 Tea``) scores about 0.8.  Keep the threshold above weak generic
        # matches while still allowing a single ordinary typo.
        return 0.78
    if compact_length <= 8:
        return 0.78
    return 0.74


def suggest_vendor_names(
    names: str | Iterable[str],
    vendors: Iterable[VendorEntry],
    limit: int = 3,
    *,
    aliases: Mapping[str, str] = CHAT_VENDOR_ALIASES,
) -> list[str]:
    """Suggest up to ``limit`` credible official names for misspellings.

    Every vendor is scored against both its official forms and known aliases.
    A deliberately conservative length-aware threshold prevents unrelated
    locations or cuisines from producing a misleading "Do you mean …?".
    """

    if limit <= 0:
        return []

    normalized_inputs = [
        normalize_vendor_text(name)
        for name in _coerce_names(names)
    ]
    normalized_inputs = [name for name in normalized_inputs if name]
    if not normalized_inputs:
        return []

    prepared = _prepare_vendors(vendors)
    alias_index = _get_alias_index(prepared, aliases)
    forms_by_vendor: dict[int, set[str]] = {
        vendor_id: set(_vendor_name_forms(vendor_name))
        for vendor_id, vendor_name in prepared
    }

    for alias, targets in alias_index.items():
        for vendor in targets:
            forms_by_vendor[vendor[0]].add(alias)

    scored: list[tuple[float, str, int]] = []
    for vendor_id, vendor_name in prepared:
        best_score = 0.0
        for query in normalized_inputs:
            threshold = _suggestion_threshold(query)
            query_score = max(
                SequenceMatcher(None, query, form).ratio()
                for form in forms_by_vendor[vendor_id]
            )
            if query_score >= threshold:
                best_score = max(best_score, query_score)

        if best_score:
            scored.append((best_score, vendor_name, vendor_id))

    scored.sort(key=lambda item: (-item[0], item[1].casefold(), item[2]))
    suggestions: list[str] = []
    seen_names: set[str] = set()
    for _, vendor_name, _ in scored:
        normalized_name = normalize_vendor_text(vendor_name)
        if normalized_name in seen_names:
            continue
        suggestions.append(vendor_name)
        seen_names.add(normalized_name)
        if len(suggestions) == limit:
            break
    return suggestions
