"""add payment_deferral_days field

Revision ID: add_payment_deferral_days
Revises: add_all_services_field
Create Date: 2026-02-05 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_payment_deferral_days'
down_revision = 'add_all_services_field'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Добавляем поле payment_deferral_days в таблицу contract_data
    op.add_column('contract_data', sa.Column('payment_deferral_days', sa.Integer(), nullable=True))


def downgrade() -> None:
    # Удаляем поле payment_deferral_days из таблицы contract_data
    op.drop_column('contract_data', 'payment_deferral_days')
