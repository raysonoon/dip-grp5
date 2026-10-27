"""Typed query planning and grounding before any food/vendor retrieval."""

import re
import unicodedata
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, model_validator

from app.schemas.chat import ChatHistoryMessage
from app.services.structured_filters import StructuredFilter, extract_structured_filters
from app.services.vendor_matching import CHAT_VENDOR_ALIASES, match_vendor_mentions, normalize_vendor_text, vendor_brand_key

EntityText = Annotated[StrictStr, Field(min_length=1, max_length=100, pattern=r"\S")]


class QueryConstraints(BaseModel):
    model_config = ConfigDict(extra="forbid")

    location: EntityText | None = None
    exclude_location: EntityText | None = None
    halal: StrictBool | None = None
    vegetarian: StrictBool | None = None
    budget: Literal["cheap", "expensive"] | None = None
    exclude_budget: Literal["cheap", "expensive"] | None = None
    exclude_cuisine: EntityText | None = None
    open_hours: Literal["after 20:00", "late", "sunday"] | None = None
    exclude_open_hours: Literal["after 20:00", "late", "sunday"] | None = None
    sort: Literal["rating", "price_asc", "price_desc"] | None = None
    query_kind: Literal["list", "count", "rank"] = "list"
    top_n: Annotated[StrictInt, Field(ge=1, le=100)] | None = None
    excluded_vendor_names: list[EntityText] = Field(default_factory=list, max_length=20)


class ResolvedQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: Literal["food", "vendor", "picker_memory", "general", "clarify"]
    reference: Literal["current", "picker", "conversation", "none"]
    question: Annotated[StrictStr, Field(min_length=1, max_length=2000)]
    food_type: Annotated[StrictStr, Field(min_length=1, max_length=80)] | None = None
    food_mention: EntityText | None = None
    vendor_names: list[EntityText] = Field(default_factory=list, max_length=20)
    constraints: QueryConstraints = Field(default_factory=QueryConstraints)
    evidence: Literal["directory", "reviews"] = "directory"
    review_source: Literal["reddit", "google_review", "internal_review"] | None = None
    language: Literal["English", "Chinese", "other"] = "other"

    @model_validator(mode="after")
    def check_entity_types(self):
        if self.target == "vendor" and (not self.vendor_names or self.food_type or self.reference == "picker"):
            raise ValueError("A vendor query needs vendor names, not a food or picker reference")
        if self.target != "vendor" and self.vendor_names:
            raise ValueError("Only vendor queries may contain vendor names")
        if self.target not in {"food", "picker_memory"} and self.food_type:
            raise ValueError("Food types cannot be attached to other query targets")
        if self.target != "food" and self.food_mention:
            raise ValueError("Only food queries can contain a food mention")
        if self.target == "picker_memory" and self.reference != "picker":
            raise ValueError("Picker memory must reference the current picker state")
        return self


class QueryGroundingError(ValueError):
    pass


def _entity_key(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value.casefold())
    return " ".join("".join(
        char if char.isalnum() else " "
        for char in folded if not unicodedata.combining(char) and char not in "'’"
    ).split())


def _has_entity_span(name: str, text: str) -> bool:
    name, text = _entity_key(name), _entity_key(text)
    return bool(name and re.search(rf"(?<![a-z0-9]){re.escape(name)}(?![a-z0-9])", text))


def ground_query(
    query: ResolvedQuery,
    *,
    question: str,
    history: list[ChatHistoryMessage],
    food_pick: str | None,
    vendors: list[tuple[int, str]],
) -> ResolvedQuery:
    """Accept entities from original input/context, never from a rewritten sentence."""
    query = query.model_copy(deep=True)
    if query.reference == "picker":
        if query.target not in {"food", "picker_memory", "clarify"}:
            raise QueryGroundingError("Picker state describes a food, not a vendor")
        if food_pick is None:
            if query.food_type is not None:
                raise QueryGroundingError("There is no current picker result")
        elif query.food_type and _entity_key(query.food_type) != _entity_key(food_pick):
            raise QueryGroundingError("A stale or invented picker result cannot replace current state")
        if query.target in {"food", "picker_memory"}:
            query.food_type = food_pick

    original_context = question
    if query.reference == "conversation":
        original_context += "\n" + "\n".join(message.content for message in history[-10:])
    if query.target == "food" and query.food_type and query.reference != "picker":
        if not _has_entity_span(query.food_mention or query.food_type, original_context):
            raise QueryGroundingError("Food needs a mention in the original input or referenced conversation")
    current_matches = {vendor_id for vendor_id, name in match_vendor_mentions(question, vendors)
                       if _has_entity_span(name, question)}
    excluded_ids = {vendor_id for name in query.constraints.excluded_vendor_names
                    for vendor_id, _ in match_vendor_mentions(name, vendors)}
    if query.target == "food" and current_matches - excluded_ids:
        # A new explicitly named business cannot silently become a dish query.
        raise QueryGroundingError("Explicit vendors require a vendor query or an explicit exclusion")

    for name in [*query.vendor_names, *query.constraints.excluded_vendor_names]:
        matched_ids = {vendor_id for vendor_id, _ in match_vendor_mentions(name, vendors)}
        context_ids = {vendor_id for vendor_id, _ in match_vendor_mentions(original_context, vendors)}
        if matched_ids:
            alias_target = CHAT_VENDOR_ALIASES.get(normalize_vendor_text(name))
            if not any(vendor_brand_key(alias_target or name) == vendor_brand_key(official)
                       for vendor_id, official in vendors if vendor_id in matched_ids):
                raise QueryGroundingError("A vendor name cannot include a surrounding question or instruction")
            if not matched_ids.intersection(context_ids):
                raise QueryGroundingError("Vendor was not mentioned in the original question or referenced conversation")
        elif not _has_entity_span(name, question):
            raise QueryGroundingError("Unknown vendor names must be literal spans in the current question")
        elif len(name.split()) > 6 or re.search(r"[?？\n\r]|\b(?:please|recommend|where|find|could|should)\b", name, re.I):
            raise QueryGroundingError("A question or instruction is not a vendor name")
        if food_pick and _entity_key(name) == _entity_key(food_pick) and not matched_ids:
            raise QueryGroundingError("A picked dish is not a vendor name")
    if query.food_type and re.search(r"[?？\n\r]|\b(?:please|recommend|where|could|should)\b", query.food_type, re.I):
        raise QueryGroundingError("A rewritten question is not a food type")
    return query


def resolved_filters(query: ResolvedQuery, original_question: str) -> StructuredFilter:
    """Preserve deterministic explicit constraints, fill remaining fields semantically."""
    values = query.constraints.model_dump(exclude={"excluded_vendor_names"})
    filters = StructuredFilter(**values)
    explicit = extract_structured_filters(original_question)
    for field in values:
        value = getattr(explicit, field)
        if value is not None and (field != "query_kind" or value != "list"):
            setattr(filters, field, value)
    return filters
