"""create chatbot prompts

Revision ID: f4a6b8c0d2e3
Revises: e2c4b6a8d0f1
Create Date: 2026-08-31

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "f4a6b8c0d2e3"
down_revision: Union[str, Sequence[str], None] = "e2c4b6a8d0f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "chatbot_prompts",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("intent_key", sa.String(length=100), nullable=False),
        sa.Column("question_scope", sa.Text(), nullable=False),
        sa.Column("prompt_template", sa.Text(), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(trim(intent_key)) > 0",
            name=op.f("ck_chatbot_prompts_intent_key_not_blank"),
        ),
        sa.CheckConstraint(
            "length(trim(question_scope)) > 0",
            name=op.f("ck_chatbot_prompts_question_scope_not_blank"),
        ),
        sa.CheckConstraint(
            "length(trim(prompt_template)) > 0",
            name=op.f("ck_chatbot_prompts_prompt_template_not_blank"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chatbot_prompts")),
        sa.UniqueConstraint(
            "intent_key",
            name=op.f("uq_chatbot_prompts_intent_key"),
        ),
    )


def downgrade() -> None:
    op.drop_table("chatbot_prompts")
