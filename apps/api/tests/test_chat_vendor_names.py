import pytest

from app.models import Vendor
from app.schemas.chat import ChatSource
from app.services.answer_vendor_names import VendorAnswerNames
from app.services.chat import ChatGeneration, ChatService
from app.services.retrieval import FakeKnowledgeStore
from app.services.vendor_matching import CHAT_VENDOR_ALIASES, VENDOR_ALIASES, match_vendor_mentions


class Embedder:
    def embed(self, questions):
        return [[1.0, 0.0] for _ in questions]


def test_ticket_alias_is_domain_metadata_without_matching_the_bare_location():
    vendors = [(771, "Nanyang Crescent Food Court"), (992, "Quad Cafe (SBS)")]
    assert VENDOR_ALIASES["saraca canteen"] == "Nanyang Crescent Food Court"
    assert "saraca" not in CHAT_VENDOR_ALIASES
    assert match_vendor_mentions("Saraca canteen and Quad Cafe", vendors) == vendors
    assert match_vendor_mentions("I am near Saraca", vendors) == []
    answer = VendorAnswerNames(vendors).rewrite("Try **Saraca canteen** [1] or **Quad Cafe** [2].")
    assert answer == "Try **Nanyang Crescent Food Court** [1] or **Quad Cafe (SBS)** [2]."


def test_unknown_directory_names_work_without_new_aliases_or_vendor_ids():
    names = VendorAnswerNames([(9871, "Aurora Bento (West Annex)"), (6205, "The Lunar Ladle")])
    assert names.rewrite("Try **Aurora Bento** or Lunar Ladle.") == (
        "Try **Aurora Bento (West Annex)** or The Lunar Ladle."
    )


def test_only_context_vendors_can_be_expanded_and_ambiguous_branches_stay_unchanged():
    catalog = [
        (91, "Orbit Bowl (North Wing)"),
        (92, "Orbit Bowl (South Wing)"),
        (93, "Aurora Bento (West Annex)"),
    ]
    names = VendorAnswerNames([catalog[0]], catalog=catalog)
    original = "Orbit Bowl or Aurora Bento? Orbit Bowl (North Wing) is in the context."
    assert names.rewrite(original) == original
    assert VendorAnswerNames([]).rewrite("Try Quad Cafe.") == "Try Quad Cafe."


@pytest.mark.parametrize("answer", [
    "Try Quad Cafe (SBS).",
    "Try **Quad Cafe (SBS)** [1].",
    "Try Quad Cafe (SBS), then Quad Cafe.",
])
def test_complete_names_are_not_expanded_twice(answer):
    names = VendorAnswerNames([(9, "Quad Cafe (SBS)")])
    expected = answer if answer != "Try Quad Cafe (SBS), then Quad Cafe." else (
        "Try Quad Cafe (SBS), then Quad Cafe (SBS)."
    )
    assert names.rewrite(answer) == expected
    assert names.rewrite(expected) == expected


def test_unicode_spelling_and_existing_punctuation_are_preserved():
    names = VendorAnswerNames([(4, "Geláre"), (9, "Quad Cafe (SBS)")])
    assert names.rewrite("**GELARE**, then Quad Café (sbs)!") == (
        "**Geláre**, then Quad Cafe (SBS)!"
    )


def test_decomposed_final_accent_is_replaced_without_duplicate_combining_marks():
    names = VendorAnswerNames([(101, "Nova Café")])
    answer = "Try **Nova Cafe\u0301**."
    assert names.rewrite(answer) == "Try **Nova Café**."
    assert "".join(names.stream(iter(answer))) == "Try **Nova Café**."


@pytest.mark.parametrize("answer", ["Quad Cafe. (SBS) is open.", "Quad Cafe -- SBS is open."])
def test_sentence_punctuation_does_not_get_swallowed_as_name_formatting(answer):
    names = VendorAnswerNames([(9, "Quad Cafe (SBS)")])
    assert names.rewrite(answer) == answer
    assert "".join(names.stream(iter(answer))) == answer


def test_word_boundaries_markup_code_and_link_destinations_are_safe():
    names = VendorAnswerNames([(9871, "Aurora Bento (West Annex)")])
    answer = (
        "Aurora Bentoish is different. Try **Aurora Bento** [1]. "
        "Keep `Aurora Bento`, *Aurora* Bento, and https://example.com/Aurora-Bento intact. "
        "[Menu](../Aurora-Bento) and ```Aurora Bento``` are code/links."
    )
    assert names.rewrite(answer) == answer.replace(
        "**Aurora Bento**", "**Aurora Bento (West Annex)**"
    )


@pytest.mark.parametrize("destination", [
    "https://example.com/(march)/Quad-Cafe",
    "../(march)/Quad-Cafe",
    r"../march\)/Quad-Cafe",
])
def test_balanced_and_escaped_markdown_link_destinations_never_change(destination):
    names = VendorAnswerNames([(9, "Quad Cafe (SBS)")])
    answer = f"[Menu]({destination}) then **Quad Cafe**."
    expected = f"[Menu]({destination}) then **Quad Cafe (SBS)**."
    assert names.rewrite(answer) == expected
    assert "".join(names.stream(iter(answer))) == expected
    for boundary in range(len(answer) + 1):
        assert "".join(names.stream([answer[:boundary], answer[boundary:]])) == expected


@pytest.mark.parametrize("reference", ["menu", "Gelare"])
def test_markdown_reference_link_definitions_preserve_relative_paths(reference):
    names = VendorAnswerNames([(4, "Geláre")])
    answer = f"Try **Gelare**.\n\n[{reference}]: ../(march)/Gelare"
    expected = answer.replace("**Gelare**", "**Geláre**")
    assert names.rewrite(answer) == expected
    assert "".join(names.stream(iter(answer))) == expected


def test_longer_catalog_identity_does_not_get_partially_replaced():
    names = VendorAnswerNames(
        [(1, "Aurora Bento")],
        catalog=[(1, "Aurora Bento"), (2, "Aurora Bento Express (Museum)")],
    )
    assert names.rewrite("Aurora Bento Express is another vendor.") == (
        "Aurora Bento Express is another vendor."
    )


@pytest.mark.parametrize("answer", [
    "Try **Quad Cafe** [1] or Saraca canteen [2].",
    "Quad Cafe (SBS) is already canonical, while Quad Cafe is not.",
    "**Gelare** is a different spelling. `Quad Cafe` stays code.",
    "[Menu](https://example.com/Quad-Cafe) then **Quad Cafe**.",
])
def test_streaming_is_independent_of_every_chunk_boundary(answer):
    names = VendorAnswerNames([
        (9, "Quad Cafe (SBS)"), (7, "Nanyang Crescent Food Court"), (4, "Geláre"),
    ])
    expected = names.rewrite(answer)
    for boundary in range(len(answer) + 1):
        assert "".join(names.stream([answer[:boundary], answer[boundary:]])) == expected
    assert "".join(names.stream(iter(answer))) == expected


def test_ordinary_text_does_not_wait_for_the_entire_generation():
    consumed = []

    def chunks():
        consumed.append(1)
        yield "Here are a few options. "
        consumed.append(2)
        yield "Try Quad Cafe."

    stream = VendorAnswerNames([(9, "Quad Cafe (SBS)")]).stream(chunks())
    assert next(stream) == "Here are a few options. "
    assert consumed == [1]
    assert "".join(stream) == "Try Quad Cafe (SBS)."


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize("canonical_name", ["Aurora Bento (West Annex)", "Aurora Bento\n@ West Annex"])
def test_service_uses_actual_database_canonical_identity_after_retrieval(session, streaming, canonical_name):
    vendor = Vendor(name=canonical_name, location="West Annex")
    session.add(vendor)
    session.commit()
    prompts = []
    generation = ChatGeneration(
        prompt="A custom answer template with retrieved facts.",
        sources=[ChatSource(
            source_type="vendor", vendor_id=vendor.id, vendor_name="Old directory label",
        )],
        search_type="SQL", intent=None,
    )

    class PreparedService(ChatService):
        def _prepare_answer(self, question, *, history=None, current_user=None):
            return generation

    def generate(prompt):
        prompts.append(prompt)
        return "Try **Aurora Bento** [1]."

    def generate_stream(prompt):
        prompts.append(prompt)
        yield "Try **Au"
        yield "rora Ben"
        yield "to** [1]."

    service = PreparedService(
        Embedder(), FakeKnowledgeStore(items=[]), session=session,
        generate=generate, generate_stream=generate_stream,
    )
    if streaming:
        events = list(service.stream_answer("What would you suggest?"))
        answer = "".join(data for event, data in events if event == "delta")
        assert events[-1][0] == "sources"
        sources = events[-1][1]
    else:
        response = service.answer("What would you suggest?")
        answer, sources = response.answer, response.sources
    display_name = " ".join(vendor.name.split())
    assert answer == f"Try **{display_name}** [1]."
    assert sources[0].vendor_id == vendor.id
    assert sources[0].vendor_name == display_name
    assert "A custom answer template with retrieved facts." in prompts[0]
    # The Foodie voice is applied once via system_instruction, not duplicated
    # into the prompt text.
    assert "Singlish" not in prompts[0]
    assert "bulleted or numbered" not in prompts[0]
    assert display_name in prompts[0]
    assert "food picker" not in prompts[0].lower()


def test_direct_answers_and_conflicting_source_names_remain_safe():
    class PreparedService(ChatService):
        def _prepare_answer(self, *args, **kwargs):
            generation = ChatGeneration(
                prompt="", sources=[
                    ChatSource(source_type="vendor", vendor_id=1, vendor_name="Orbit Bowl (North)"),
                    ChatSource(source_type="vendor", vendor_id=1, vendor_name="Orbit Bowl (South)"),
                ], search_type="SQL", intent=None, direct_answer="Try Orbit Bowl.",
            )
            return generation

    service = PreparedService(Embedder(), FakeKnowledgeStore(items=[]))
    assert service.answer("Hello").answer == "Try Orbit Bowl."
