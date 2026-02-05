"""add agreement_uuid field to counterparty_1c

Revision ID: add_agreement_uuid
Revises: add_payment_deferral_days
Create Date: 2026-02-05 00:30:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_agreement_uuid'
down_revision = 'add_payment_deferral_days'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Добавляем поле agreement_uuid в таблицу counterparty_1c
    op.add_column('counterparty_1c', sa.Column('agreement_uuid', sa.String(36), nullable=True))


def downgrade() -> None:
    # Удаляем поле agreement_uuid из таблицы counterparty_1c
    op.drop_column('counterparty_1c', 'agreement_uuid')
