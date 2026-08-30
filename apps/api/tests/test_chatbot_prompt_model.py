from collections import Counter

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.chatbot_question_data import CHATBOT_QUESTION_ROWS
from app.db.seed import seed_chatbot_questions
from app.models import ChatbotPrompt


def test_chatbot_prompt_stores_intent_mapping(session: Session) -> None:
    prompt = ChatbotPrompt(
        intent_key=" Vendor_Recommendation ",
        question_scope=" Questions asking which food stall to visit. ",
        prompt_template=" Recommend vendors for: {user_question} ",
    )
    session.add(prompt)
    session.commit()
    session.refresh(prompt)

    assert prompt.intent_key == "vendor_recommendation"
    assert prompt.question_scope == "Questions asking which food stall to visit."
    assert prompt.prompt_template == "Recommend vendors for: {user_question}"
    assert prompt.is_active is True
    assert prompt.created_at is not None
    assert prompt.updated_at is not None


def test_chatbot_prompt_intent_key_is_unique(session: Session) -> None:
    session.add(
        ChatbotPrompt(
            intent_key="vendor_recommendation",
            question_scope="Vendor recommendation questions",
            prompt_template="First template: {user_question}",
        )
    )
    session.commit()

    session.add(
        ChatbotPrompt(
            intent_key="VENDOR_RECOMMENDATION",
            question_scope="Duplicate intent",
            prompt_template="Second template: {user_question}",
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_chatbot_question_can_be_stored_without_prompt(
    session: Session,
) -> None:
    question = ChatbotPrompt(
        intent_key="Q001",
        question_scope="Dietary requirements",
        question_text="Where can I find halal food?",
        search_type="SQL",
        source_file="DIP AI chatbot questions.xlsx",
        prompt_template=None,
    )
    session.add(question)
    session.commit()
    session.refresh(question)

    assert question.intent_key == "q001"
    assert question.question_text == "Where can I find halal food?"
    assert question.search_type == "SQL"
    assert question.prompt_template is None


def test_chatbot_question_seed_imports_both_workbooks_once(
    session: Session,
) -> None:
    created, updated = seed_chatbot_questions(session)
    rows = list(
        session.scalars(
            select(ChatbotPrompt).order_by(ChatbotPrompt.intent_key)
        )
    )

    assert created == 59
    assert updated == 0
    assert len(CHATBOT_QUESTION_ROWS) == 59
    assert len(rows) == 59
    assert Counter(row.search_type for row in rows) == {
        "SQL": 29,
        "Vector": 17,
        "SQL + Vector": 13,
    }
    assert all(row.question_text for row in rows)
    assert all(row.prompt_template is None for row in rows)

    shared = next(row for row in rows if row.intent_key == "q010")
    assert shared.source_file == (
        "DIP AI chatbot questions.xlsx; DIP Chatbot Schema.xlsx"
    )

    created_again, updated_again = seed_chatbot_questions(session)
    assert created_again == 0
    assert updated_again == 0
    assert session.query(ChatbotPrompt).count() == 59


@pytest.mark.parametrize(
    "field",
    ["question_scope", "question_text", "source_file", "prompt_template"],
)
def test_chatbot_prompt_rejects_blank_required_text(
    session: Session,
    field: str,
) -> None:
    values = {
        "intent_key": f"blank_{field}",
        "question_scope": "Question category",
        "question_text": "Example question?",
        "search_type": "SQL",
        "source_file": "source.xlsx",
        "prompt_template": "Template",
    }
    values[field] = "   "

    with pytest.raises(ValueError, match=f"{field} cannot be empty"):
        ChatbotPrompt(**values)


def test_chatbot_question_rejects_unknown_search_type() -> None:
    with pytest.raises(ValueError, match="search_type must be one of"):
        ChatbotPrompt(
            intent_key="bad_search_type",
            question_scope="Question category",
            question_text="Example question?",
            search_type="Keyword",
            prompt_template=None,
        )
