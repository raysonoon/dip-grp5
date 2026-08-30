"""store chatbot questions before prompt authoring

Revision ID: g5b7c9d1e3f4
Revises: f4a6b8c0d2e3
Create Date: 2026-08-31

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "g5b7c9d1e3f4"
down_revision: Union[str, Sequence[str], None] = "f4a6b8c0d2e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "chatbot_prompts",
        sa.Column("question_text", sa.Text(), nullable=True),
    )
    op.add_column(
        "chatbot_prompts",
        sa.Column("search_type", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "chatbot_prompts",
        sa.Column("source_file", sa.String(length=255), nullable=True),
    )
    op.alter_column(
        "chatbot_prompts",
        "prompt_template",
        existing_type=sa.Text(),
        nullable=True,
    )
    op.drop_constraint(
        op.f("ck_chatbot_prompts_prompt_template_not_blank"),
        "chatbot_prompts",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_chatbot_prompts_prompt_template_not_blank"),
        "chatbot_prompts",
        "prompt_template IS NULL OR length(trim(prompt_template)) > 0",
    )
    op.create_check_constraint(
        op.f("ck_chatbot_prompts_question_text_not_blank"),
        "chatbot_prompts",
        "question_text IS NULL OR length(trim(question_text)) > 0",
    )
    op.create_check_constraint(
        op.f("ck_chatbot_prompts_search_type_allowed"),
        "chatbot_prompts",
        "search_type IS NULL OR "
        "search_type IN ('SQL', 'Vector', 'SQL + Vector')",
    )
    op.create_check_constraint(
        op.f("ck_chatbot_prompts_source_file_not_blank"),
        "chatbot_prompts",
        "source_file IS NULL OR length(trim(source_file)) > 0",
    )
    op.create_check_constraint(
        op.f("ck_chatbot_prompts_question_has_search_type"),
        "chatbot_prompts",
        "question_text IS NULL OR search_type IS NOT NULL",
    )
    op.create_check_constraint(
        op.f("ck_chatbot_prompts_question_or_prompt_present"),
        "chatbot_prompts",
        "question_text IS NOT NULL OR prompt_template IS NOT NULL",
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM chatbot_prompts "
            "WHERE prompt_template IS NULL"
        )
    )
    op.drop_constraint(
        op.f("ck_chatbot_prompts_question_or_prompt_present"),
        "chatbot_prompts",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_chatbot_prompts_question_has_search_type"),
        "chatbot_prompts",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_chatbot_prompts_search_type_allowed"),
        "chatbot_prompts",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_chatbot_prompts_source_file_not_blank"),
        "chatbot_prompts",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_chatbot_prompts_question_text_not_blank"),
        "chatbot_prompts",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_chatbot_prompts_prompt_template_not_blank"),
        "chatbot_prompts",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_chatbot_prompts_prompt_template_not_blank"),
        "chatbot_prompts",
        "length(trim(prompt_template)) > 0",
    )
    op.alter_column(
        "chatbot_prompts",
        "prompt_template",
        existing_type=sa.Text(),
        nullable=False,
    )
    op.drop_column("chatbot_prompts", "search_type")
    op.drop_column("chatbot_prompts", "source_file")
    op.drop_column("chatbot_prompts", "question_text")
