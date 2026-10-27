import pytest
from pydantic import ValidationError

from app.schemas.chat import ChatHistoryMessage
from app.services.query_resolution import (
    QueryConstraints, QueryGroundingError, ResolvedQuery, ground_query, resolved_filters,
)


VENDORS = [(1, "Chateraise"), (2, "The Crowded Bowl"), (3, "McDonald's"), (4, "Boost Juice Bars")]


def ground(plan, question, *, food_pick="Salad", history=None):
    return ground_query(plan, question=question, history=history or [], food_pick=food_pick, vendors=VENDORS)


@pytest.mark.parametrize("overrides", [
    {"target": "vendor", "vendor_names": []},
    {"target": "vendor", "vendor_names": ["Chateraise"], "food_type": "Salad"},
    {"target": "vendor", "vendor_names": ["Chateraise"], "reference": "picker"},
    {"target": "food", "vendor_names": ["Chateraise"]},
    {"target": "general", "food_type": "Salad"},
    {"target": "picker_memory", "reference": "current"},
    {"target": "SQL"},
    {"unexpected": "instruction"},
    {"constraints": {"halal": "true"}},
    {"constraints": {"top_n": True}},
    {"constraints": {"top_n": 101}},
    {"constraints": {"vendor_names": ["Chateraise"]}},
    {"vendor_names": ["   "]},
])
def test_query_contract_rejects_mixed_entities_and_invalid_fields(overrides):
    with pytest.raises(ValidationError):
        ResolvedQuery.model_validate({"target": "food", "reference": "current", "question": "Where?", **overrides})


@pytest.mark.parametrize("name", [
    "Where is Chateraise?", "Salad in NTU? Please recommend 1–2 places", "the food I just picked",
])
def test_rewritten_sentences_cannot_become_vendor_names(name):
    plan = ResolvedQuery(target="vendor", reference="current", question="Where is it?", vendor_names=[name])
    with pytest.raises(QueryGroundingError):
        ground(plan, "where can i find the food i jus picked")


@pytest.mark.parametrize("name,question", [
    ("McDonalds", "Where is McDonald's?"),
    ("Boost Juice Bars", "Is boost juice open?"),
    ("boost juice", "Where is boost juice?"),
    ("Chateraise", "Chateraise 在哪里？"),
])
def test_grounded_canonical_vendor_names_and_aliases_are_allowed(name, question):
    plan = ResolvedQuery(target="vendor", reference="current", question=question, vendor_names=[name])
    assert ground(plan, question).vendor_names == [name]


def test_unmentioned_business_is_rejected_even_if_it_exists_in_directory():
    plan = ResolvedQuery(target="vendor", reference="current", question="Where is Chateraise?", vendor_names=["Chateraise"])
    with pytest.raises(QueryGroundingError):
        ground(plan, "Where can I get it?")


def test_vendor_pronoun_can_use_referenced_conversation():
    history = [ChatHistoryMessage(role="assistant", content="Try Chateraise at North Spine.")]
    plan = ResolvedQuery(target="vendor", reference="conversation", question="When does Chateraise open?", vendor_names=["Chateraise"])
    assert ground(plan, "When does it open?", history=history).vendor_names == ["Chateraise"]


def test_unknown_business_must_come_from_current_question():
    plan = ResolvedQuery(target="vendor", reference="current", question="Where is Moonlight Kitchen?", vendor_names=["Moonlight Kitchen"])
    assert ground(plan, "Where is Moonlight Kitchen?").vendor_names == ["Moonlight Kitchen"]
    with pytest.raises(QueryGroundingError):
        ground(plan, "Where can I get it?")


def test_actual_picker_state_overrides_earlier_draw_but_not_a_stale_plan():
    history = [ChatHistoryMessage(role="assistant", content="You previously rolled Salad.")]
    plan = ResolvedQuery(target="food", reference="picker", question="Where?", food_type=None)
    assert ground(plan, "Anywhere for that?", food_pick="Pizza", history=history).food_type == "Pizza"
    assert plan.food_type is None
    with pytest.raises(QueryGroundingError):
        ground(plan.model_copy(update={"food_type": "Salad"}), "Anywhere for that?", food_pick="Pizza", history=history)


def test_current_food_is_grounded_and_supports_translation_without_using_a_phrase_list():
    plan = ResolvedQuery(target="food", reference="current", question="Where can I get pizza?", food_type="Pizza", food_mention="披萨")
    assert ground(plan, "今天想吃披萨，有地方吗？").food_type == "Pizza"
    with pytest.raises(QueryGroundingError):
        ground(plan, "Where is Chateraise?")
    stale = plan.model_copy(update={"food_type": "Salad", "food_mention": None})
    with pytest.raises(QueryGroundingError):
        ground(stale, "I want pizza instead")


def test_pick_cannot_be_reinterpreted_as_an_unknown_business():
    plan = ResolvedQuery(target="vendor", reference="current", question="Where is Salad?", vendor_names=["Salad"])
    with pytest.raises(QueryGroundingError):
        ground(plan, "Where can I find Salad?")


def test_excluded_businesses_are_grounded_and_do_not_change_food_into_vendor_target():
    plan = ResolvedQuery(target="food", reference="current", question="Where is salad except The Crowded Bowl?", food_type="Salad",
                         constraints=QueryConstraints(excluded_vendor_names=["The Crowded Bowl"]))
    assert ground(plan, plan.question).target == "food"
    with pytest.raises(QueryGroundingError):
        ground(plan, "Where is salad?")


def test_explicit_constraints_are_preserved_and_chinese_constraints_are_supported():
    plan = ResolvedQuery(target="food", reference="picker", question="Where?",
                         constraints=QueryConstraints(location="South Spine", vegetarian=False))
    filters = resolved_filters(plan, "Only vegetarian places near North Spine please")
    assert filters.location == "North Spine"
    assert filters.vegetarian is True
    chinese = plan.model_copy(update={"constraints": QueryConstraints(location="North Spine", vegetarian=True, query_kind="count")})
    filters = resolved_filters(chinese, "北区有几家素食的？")
    assert (filters.location, filters.vegetarian, filters.query_kind) == ("North Spine", True, "count")
